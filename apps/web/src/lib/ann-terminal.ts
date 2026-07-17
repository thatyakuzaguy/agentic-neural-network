import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

export type TerminalInputMode = "auto" | "chat" | "command";
export type InputClassification =
  | "EMPTY"
  | "BUILTIN_COMMAND"
  | "ANN_SAFE_COMMAND"
  | "CONVERSATION_MESSAGE"
  | "EXPLICIT_SHELL_ATTEMPT"
  | "MALFORMED_INPUT";

export type TerminalEventKind =
  | "status"
  | "assistant"
  | "command"
  | "error"
  | "approval"
  | "pipeline"
  | "system";

type TerminalConversationEvent = {
  kind: TerminalEventKind;
  text: string;
};

export type ConversationSession = {
  conversationId: string;
  activeRequestId: string | null;
  activeProject: string | null;
  activeTask: string | null;
  currentMode: TerminalInputMode;
  recentMessages: { role: "USER" | "ANN" | "SYSTEM" | "COMMAND" | "ERROR" | "APPROVAL" | "PIPELINE"; text: string; at: string }[];
  pendingClarification: string | null;
  pendingApproval: { id: string; pipeline: string; risk: string } | null;
  currentPipeline: string | null;
  currentModel: string;
  lastStructuredResult: Record<string, unknown> | null;
  cancellationState: "idle" | "cancelled";
  startedAt: string;
};

type IntentContract = {
  contract_version: string;
  request_id: string;
  conversation_id: string;
  primary_intent: string;
  recommended_pipeline: string;
  requires_confirmation: boolean;
  requires_human_approval: boolean;
  explicit_constraints: string[];
  forbidden_actions: string[];
  requested_capabilities: string[];
  missing_information: string[];
  status: string;
};

type CapabilityContext = {
  message: string;
  session: ConversationSession;
  contract: IntentContract;
  risk: string;
};

type StartPipelineCapability = {
  status: string;
  approvalRequired: boolean;
  readOnly: false;
  architect_handoff: string;
  workspace_directory: string;
  approval_mode: "supervised";
  api_base: string;
  run_id?: string;
  run_status?: string;
  pending_approvals?: number;
  error?: string;
};

type ConversationModelState = {
  status: string;
  displayName: string;
  backendKind: "real" | "fake" | "unavailable";
  expectedPath: string;
  reason: string;
  modelName: string;
  runtime?: {
    allowRealInference: boolean;
    runtimeType: string;
    pythonExecutableWsl: string;
    modelPathWsl: string;
    maxTokens: number;
    contextTokens: number;
    temperature: number;
    requireGpu: boolean;
    nGpuLayers: number;
    timeoutMs: number;
  };
};

const ROOT = process.env.AEN_ROOT || "D:\\AgenticEngineeringNetwork";
const DEFAULT_WORKSPACE_DIRECTORY = process.env.AEN_DEFAULT_WORKSPACE_DIRECTORY || path.join(ROOT, "generated-projects");
const API_BASE = process.env.AEN_API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const SESSION_MAP = new Map<string, ConversationSession>();

export const SAFE_COMMANDS = [
  "help",
  "status",
  "logs",
  "projects",
  "artifacts",
  "models",
  "runtime",
  "clear",
  "cancel",
  "history",
  "approvals",
  "resume",
  "run",
  "stop",
] as const;

const SAFE_COMMAND_SET = new Set<string>(SAFE_COMMANDS);
const PAGE_COMMANDS = new Set(["dashboard", "projects", "pipeline", "models", "knowledge", "runtime", "artifacts", "logs", "settings"]);
const MODE_COMMANDS = new Set(["chat", "chat on", "chat off", "mode auto", "mode chat", "mode command"]);
const SHELL_ATTEMPT_PATTERNS = [
  /^rm\s+-rf\b/i,
  /^sudo\b/i,
  /^(bash|sh)\s+-c\b/i,
  /^powershell(\.exe)?\b/i,
  /^cmd(\.exe)?\b/i,
  /^curl\s+/i,
  /^wget\s+/i,
  /^pip\s+install\b/i,
  /^npm\s+(install|i)\b/i,
  /^pnpm\s+(install|add)\b/i,
  /^yarn\s+(install|add)\b/i,
  /^python\s+-c\b/i,
  /^del\s+\/f\b/i,
  /^format\s+/i,
  /^shutdown\b/i,
];

export function getOrCreateSession(conversationId?: string | null): ConversationSession {
  const id = conversationId?.trim() || `terminal-${cryptoRandomId()}`;
  const existing = SESSION_MAP.get(id);
  if (existing) return existing;
  const session: ConversationSession = {
    conversationId: id,
    activeRequestId: null,
    activeProject: null,
    activeTask: null,
    currentMode: "auto",
    recentMessages: [],
    pendingClarification: null,
    pendingApproval: null,
    currentPipeline: null,
    currentModel: "none",
    lastStructuredResult: null,
    cancellationState: "idle",
    startedAt: new Date().toISOString(),
  };
  SESSION_MAP.set(id, session);
  return session;
}

export function classifyTerminalInput(input: string, mode: TerminalInputMode = "auto"): InputClassification {
  const value = input.trim();
  const normalized = normalizeCommand(value);
  if (!value) return "EMPTY";
  if (value.length > 4000 || /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(value)) return "MALFORMED_INPUT";
  if (MODE_COMMANDS.has(normalized)) return "BUILTIN_COMMAND";
  if (isRegisteredCommand(normalized)) return normalized === "help" || normalized === "clear" ? "BUILTIN_COMMAND" : "ANN_SAFE_COMMAND";
  if (mode === "command") return matchesExplicitShellAttempt(value) ? "EXPLICIT_SHELL_ATTEMPT" : "MALFORMED_INPUT";
  if (matchesExplicitShellAttempt(value)) return "EXPLICIT_SHELL_ATTEMPT";
  return "CONVERSATION_MESSAGE";
}

export function isRegisteredCommand(normalized: string): boolean {
  if (SAFE_COMMAND_SET.has(normalized)) return true;
  if (normalized.startsWith("open ")) return PAGE_COMMANDS.has(normalized.slice(5).trim());
  return false;
}

export function safeHelpLines(): string[] {
  return [
    "Conversational use:",
    "- Write naturally to interact with ANN.",
    "",
    "Modes:",
    "- mode auto",
    "- mode chat",
    "- mode command",
    "",
    "Safe commands:",
    ...SAFE_COMMANDS.map((command) => `- ${command}`),
    "- open <dashboard|projects|pipeline|models|knowledge|runtime|artifacts|logs|settings>",
    "",
    "Task control:",
    "- cancel",
    "- resume",
    "- approvals",
    "- history",
    "",
    "Model diagnostics:",
    "- models",
    "- runtime",
    "- status",
  ];
}

export function runSafeTerminalCommand(command: string, session?: ConversationSession) {
  const normalized = normalizeCommand(command);
  let lines: string[];
  let handledByUi = false;
  if (!normalized || normalized === "help") {
    lines = safeHelpLines();
  } else if (normalized === "status" || normalized === "ann status") {
    lines = [
      "ANN Desktop: online",
      `Root: ${ROOT}`,
      `Platform: ${os.type()} ${os.release()}`,
      `Mode: ${labelMode(session?.currentMode ?? "auto")}`,
      "Terminal: safe allowlist mode with conversation classifier",
      "Arbitrary shell execution: disabled",
    ];
  } else if (normalized === "runtime") {
    const runtime = getRuntimeStatusCapability();
    lines = [
      `Runtime policy: ${runtime.policy}`,
      `Backend: ${runtime.backend}`,
      `Active models: ${runtime.activeModels}`,
      `Parallel LLM loads: ${runtime.parallelLoads}`,
      `Model load policy: ${runtime.realModelLoad}`,
    ];
  } else if (normalized === "models") {
    const inventory = getModelInventoryCapability();
    lines = inventory.models.map((model) => `${model.name} | ${model.backend} | ${model.status} | ${model.path}`);
  } else if (normalized === "projects") {
    lines = safeList("generated-projects");
  } else if (normalized === "artifacts") {
    lines = safeList("outputs");
  } else if (normalized === "logs") {
    lines = tailAudit();
  } else if (normalized === "history") {
    lines = (session?.recentMessages ?? []).slice(-10).map((message) => `${message.role}: ${message.text}`);
    if (!lines.length) lines = ["No terminal conversation history yet."];
  } else if (normalized === "approvals") {
    lines = session?.pendingApproval
      ? [`Pending approval ${session.pendingApproval.id}: ${session.pendingApproval.pipeline} risk=${session.pendingApproval.risk}`]
      : ["No pending terminal approval."];
  } else if (normalized === "resume") {
    lines = session?.activeTask ? [`Active task: ${session.activeTask}`] : ["No active task to resume."];
  } else if (normalized === "cancel") {
    if (session) {
      session.cancellationState = "cancelled";
      session.pendingApproval = null;
      session.pendingClarification = null;
      session.currentPipeline = null;
      session.currentModel = "none";
    }
    lines = ["Cancelled transient terminal task state. No patch was applied and no shell command was executed."];
  } else if (normalized.startsWith("open ") || normalized === "run" || normalized === "stop" || normalized === "clear") {
    handledByUi = true;
    lines = [`Handled by desktop UI: ${command}`];
  } else {
    lines = [`Blocked: "${command}" is not in the ANN safe terminal allowlist. Type "help".`];
  }
  return { status: "ok", command, lines, handledByUi };
}

export function handleModeCommand(command: string, session: ConversationSession) {
  const normalized = normalizeCommand(command);
  if (normalized === "chat" || normalized === "chat on" || normalized === "mode chat") session.currentMode = "chat";
  if (normalized === "chat off" || normalized === "mode auto") session.currentMode = "auto";
  if (normalized === "mode command") session.currentMode = "command";
  return {
    status: "completed",
    displayMessage: `Mode: ${labelMode(session.currentMode)}`,
    events: [{ kind: "system" as const, text: `Mode changed to ${labelMode(session.currentMode)}` }],
  };
}

export async function handleConversationMessage(message: string, session: ConversationSession) {
  const requestId = `req-${cryptoRandomId()}`;
  session.activeRequestId = requestId;
  session.cancellationState = "idle";
  appendMessage(session, "USER", message);

  const model = inspectConversationModel();
  const intent = inferIntent(message, session);
  const contract = buildIntentContract(requestId, session.conversationId, message, intent);
  const capabilities = await runCapabilities(contract.requested_capabilities, { message, session, contract, risk: intent.risk });
  const needsApproval = contract.requires_human_approval;
  const needsClarification = contract.missing_information.length > 0 && intent.blockingMissingInformation;
  const startPipeline = capabilities.start_pipeline as StartPipelineCapability | undefined;
  const runStarted = startPipeline?.status === "RUN_STARTED";
  const status = runStarted ? "running" : needsApproval ? "needs_approval" : needsClarification ? "needs_clarification" : "completed";
  const realResponse = runRealConversationInference({
    message,
    session,
    model,
    contract,
    capabilities,
    needsApproval,
    needsClarification,
  });

  session.activeTask = intent.primaryIntent === "general_conversation" ? session.activeTask : message;
  session.currentPipeline = contract.recommended_pipeline === "none" ? null : contract.recommended_pipeline;
  session.currentModel = model.displayName;
  session.pendingClarification = needsClarification ? contract.missing_information[0] : null;
  session.pendingApproval = needsApproval ? { id: `approval-${requestId}`, pipeline: contract.recommended_pipeline, risk: intent.risk } : null;
  if (runStarted) {
    session.activeProject = startPipeline.workspace_directory;
    session.pendingApproval = startPipeline.pending_approvals
      ? { id: `backend-${startPipeline.run_id}`, pipeline: contract.recommended_pipeline, risk: intent.risk }
      : session.pendingApproval;
  }

  const assistant =
    renderPipelineHandoffMessage(startPipeline)
    ?? realResponse.text
    ?? renderAssistantMessage({ message, model, intent, contract, capabilities, needsApproval, needsClarification });
  appendMessage(session, "ANN", assistant);
  session.lastStructuredResult = { intent_contract: contract, capabilities, model };
  session.currentModel = "none";

  return {
    request_id: requestId,
    conversation_id: session.conversationId,
    status,
    display_message: assistant,
    mode: session.currentMode,
    input_classification: "CONVERSATION_MESSAGE",
    intent_contract: contract,
    pipeline: contract.recommended_pipeline === "none" ? null : contract.recommended_pipeline,
    approvals: session.pendingApproval ? [session.pendingApproval] : [],
    capabilities,
    model,
    events: [
      { kind: "status" as const, text: "Entendiendo petición" },
      { kind: "status" as const, text: "Construyendo contexto" },
      { kind: "status" as const, text: "Extrayendo intención" },
      { kind: "status" as const, text: "Validando restricciones" },
      ...(realResponse.events ?? []),
      ...(startPipeline
        ? [
            { kind: "pipeline" as const, text: "Handoff preparado para Architect Agent" },
            { kind: "pipeline" as const, text: `Architect handoff status: ${startPipeline.status}` },
            ...(startPipeline.run_id ? [{ kind: "pipeline" as const, text: `Run iniciado: ${startPipeline.run_id}` }] : []),
          ]
        : []),
      { kind: "pipeline" as const, text: `Pipeline: ${contract.recommended_pipeline}` },
      ...(needsApproval ? [{ kind: "approval" as const, text: "Approval required before any write action." }] : []),
      { kind: "assistant" as const, text: assistant },
    ],
    terminal_status: terminalStatus(session, model),
  };
}

export function blockedShellAttemptResponse(message: string, session: ConversationSession) {
  appendMessage(session, "ERROR", `Blocked shell attempt: ${message}`);
  return {
    request_id: `req-${cryptoRandomId()}`,
    conversation_id: session.conversationId,
    status: "blocked",
    display_message: "Blocked: explicit shell execution attempts must use approved ANN capabilities or safe registered commands. No shell was executed.",
    mode: session.currentMode,
    input_classification: "EXPLICIT_SHELL_ATTEMPT",
    intent_contract: null,
    pipeline: null,
    approvals: [],
    events: [{ kind: "error" as const, text: "Explicit shell attempt blocked by ANN terminal policy." }],
    terminal_status: terminalStatus(session, inspectConversationModel()),
  };
}

function inferIntent(message: string, session: ConversationSession) {
  const text = message.toLowerCase();
  const constraints = extractConstraints(message);
  if (/^(hola|buenas|hello|hi)\b/.test(text) || /qu[eé] puedes hacer/.test(text)) {
    return intent("general_conversation", "none", false, false, ["conversation_help"], constraints, "low", false);
  }
  if (/modelos|modelo.*disponible|model inventory/.test(text)) {
    return intent("model_inventory_query", "none", false, false, ["get_model_inventory"], constraints, "low", false);
  }
  if (/runtime|bloquead|gpu|backend|vram/.test(text)) {
    return intent("runtime_diagnostics_query", "runtime_setup_or_diagnostics", false, false, ["get_runtime_status"], constraints, "low", false);
  }
  if (/contin[uú]a|resume|hazlo|usa ese proyecto/.test(text)) {
    return intent("resume_active_task", session.currentPipeline ?? "repository_analysis", false, false, ["get_active_project"], constraints, "medium", !session.activeTask);
  }
  if (/aplica.*parche|apply.*patch/.test(text)) {
    return intent("patch_application", "patch_application", true, true, ["start_pipeline"], constraints, "high", false);
  }
  if (/(build|create|make|develop|generate|implement|crea|crear|haz|hacer|desarrolla|genera|implementa|construye)\b/.test(text)
    || /\b(saas|crm|ecommerce|api|app|aplicaci[oó]n|videojuego|juego|dashboard|backend|frontend)\b/.test(text)) {
    return intent("software_build_request", "project_creation", true, true, ["start_pipeline"], constraints, "high", false);
  }
  if (/test|pytest|prueba/.test(text) && !/arregl|corrig|fix/.test(text)) {
    return intent("test_and_validate", "test_and_validate", true, false, ["start_pipeline"], constraints, "medium", false);
  }
  if (/seguridad|security|audit/.test(text)) {
    return intent("security_review", "security_review", true, false, ["start_pipeline"], constraints, "medium", false);
  }
  if (/arregl|corrig|fix|error|login|bug/.test(text)) {
    return intent("debug_and_fix", "debug_and_fix", true, true, ["get_active_project", "start_pipeline"], constraints, "high", !session.activeProject);
  }
  if (/analiza|revisa|estado de ann|estado del proyecto|proyecto/.test(text)) {
    return intent("repository_analysis", "repository_analysis", false, false, ["get_active_project", "get_recent_artifacts"], constraints, "medium", false);
  }
  if (/plan|interfaz|terminar/.test(text)) {
    return intent("requirement_analysis", "requirement_analysis", false, false, ["start_pipeline"], constraints, "medium", false);
  }
  return intent("general_conversation", "none", false, false, ["conversation_help"], constraints, "low", false);
}

function intent(
  primaryIntent: string,
  pipeline: string,
  requiresConfirmation: boolean,
  requiresApproval: boolean,
  capabilities: string[],
  constraints: string[],
  risk: string,
  blockingMissingInformation: boolean,
) {
  return { primaryIntent, pipeline, requiresConfirmation, requiresApproval, capabilities, constraints, risk, blockingMissingInformation };
}

function buildIntentContract(requestId: string, conversationId: string, message: string, inferred: ReturnType<typeof inferIntent>): IntentContract {
  const missing = inferred.blockingMissingInformation ? ["Necesito un proyecto activo o una ruta de proyecto permitida en D: o E:."] : [];
  return {
    contract_version: "ann_intent_contract_v1",
    request_id: requestId,
    conversation_id: conversationId,
    primary_intent: inferred.primaryIntent,
    recommended_pipeline: inferred.pipeline,
    requires_confirmation: inferred.requiresConfirmation,
    requires_human_approval: inferred.requiresApproval,
    explicit_constraints: inferred.constraints,
    forbidden_actions: [
      "no_shell_execution_from_model",
      "no_direct_patch_application",
      "no_dependency_installation_without_approval",
      ...inferred.constraints.filter((constraint) => /no |sin |don't|do not/i.test(constraint)),
    ],
    requested_capabilities: inferred.capabilities,
    missing_information: missing,
    status: missing.length ? "NEEDS_CLARIFICATION" : inferred.requiresApproval ? "NEEDS_APPROVAL" : "READY",
  };
}

function renderAssistantMessage(input: {
  message: string;
  model: ConversationModelState;
  intent: ReturnType<typeof inferIntent>;
  contract: IntentContract;
  capabilities: Record<string, unknown>;
  needsApproval: boolean;
  needsClarification: boolean;
}) {
  const { model, intent, contract, capabilities, needsApproval, needsClarification } = input;
  const modelLine = model.backendKind === "real"
    ? "Qwen3-4B real backend is available for conversation orchestration."
    : model.backendKind === "fake"
      ? "Conversation mode is running with a simulated backend. Real model inference is not active."
      : model.reason;

  if (intent.primaryIntent === "general_conversation") {
    if (model.backendKind === "unavailable") {
      return [
        "Conversation mode unavailable.",
        "Safe ANN commands remain available.",
        "Type status, models, runtime or help.",
        modelLine,
      ].join("\n");
    }
    return [
      "Hola. Soy ANN, la voz conversacional de Agentic Neural Network.",
      "Mi tarea es entender lo que quieres construir o arreglar, convertirlo en un contrato de intención, seleccionar la pipeline correcta, coordinar agentes locales y pedir aprobación antes de cualquier cambio.",
      "Puedo ayudarte a analizar proyectos, preparar planes, revisar modelos, diagnosticar el runtime, resumir actividad, conservar restricciones y preparar acciones seguras.",
      modelLine,
    ].join("\n");
  }
  if (intent.primaryIntent === "model_inventory_query") {
    const inventory = capabilities.get_model_inventory as ReturnType<typeof getModelInventoryCapability> | undefined;
    const models = inventory?.models ?? [];
    return [
      "Model Inventory real:",
      ...models.map((modelItem) => `- ${modelItem.name}: ${modelItem.status}, backend=${modelItem.backend}, path=${modelItem.path}`),
      modelLine,
    ].join("\n");
  }
  if (intent.primaryIntent === "runtime_diagnostics_query") {
    const runtime = capabilities.get_runtime_status as ReturnType<typeof getRuntimeStatusCapability> | undefined;
    return [
      "Runtime status:",
      `- Backend: ${runtime?.backend ?? "unknown"}`,
      `- Policy: ${runtime?.policy ?? "unknown"}`,
      `- Active models: ${runtime?.activeModels ?? 0}`,
      `- Parallel LLM loads: ${runtime?.parallelLoads ?? 0}`,
      modelLine,
    ].join("\n");
  }
  if (needsClarification) {
    return [
      `He detectado la intención ${contract.primary_intent}.`,
      `Pipeline propuesta: ${contract.recommended_pipeline}.`,
      ...contract.explicit_constraints.map((constraint) => `Restricción conservada: ${constraint}`),
      contract.missing_information[0],
      modelLine,
    ].join("\n");
  }
  if (needsApproval) {
    return [
      "La tarea está preparada.",
      "",
      `Pipeline: ${contract.recommended_pipeline}`,
      "",
      "Restricciones:",
      ...(contract.explicit_constraints.length ? contract.explicit_constraints.map((constraint) => `- ${constraint}`) : ["- Solicitar aprobación antes de modificar archivos."]),
      "- No ejecutar shell arbitrario.",
      "- No instalar dependencias automáticamente.",
      "",
      "Acción pendiente:",
      "Type: approve, reject, details",
      modelLine,
    ].join("\n");
  }
  return [
    `He detectado la intención ${contract.primary_intent}.`,
    `Pipeline propuesta: ${contract.recommended_pipeline}.`,
    ...contract.explicit_constraints.map((constraint) => `Restricción conservada: ${constraint}`),
    "No se ha aplicado ningún cambio todavía.",
    modelLine,
  ].join("\n");
}

function renderPipelineHandoffMessage(startPipeline?: StartPipelineCapability) {
  if (!startPipeline) return null;
  if (startPipeline.status === "RUN_STARTED") {
    return [
      "ANN ha preparado el handoff para Architect Agent y ha iniciado el run real.",
      "",
      `Run ID: ${startPipeline.run_id}`,
      `Estado inicial: ${startPipeline.run_status}`,
      `Workspace: ${startPipeline.workspace_directory}`,
      "Modo de aprobación: supervisado",
      "",
      "El arquitecto recibirá el input optimizado, lo convertirá en plan técnico y coordinará la pipeline de agentes. Cualquier modificación seguirá pasando por los gates de aprobación.",
    ].join("\n");
  }
  if (startPipeline.status === "RUN_PREPARED_TEST_MODE") {
    return [
      "ANN ha preparado el handoff para Architect Agent.",
      "",
      "Modo test: no se ha llamado al backend.",
      `Workspace objetivo: ${startPipeline.workspace_directory}`,
      "El payload contiene intención, restricciones, riesgos, pipeline recomendada e instrucciones para que Architect Agent arranque el trabajo.",
    ].join("\n");
  }
  if (startPipeline.status === "BLOCKED_NEEDS_CLARIFICATION") {
    return [
      "ANN ha preparado la intención, pero no iniciará la pipeline hasta resolver la información que falta.",
      `Workspace objetivo: ${startPipeline.workspace_directory}`,
      startPipeline.error ?? "Falta contexto obligatorio.",
    ].join("\n");
  }
  if (startPipeline.status === "RUN_START_FAILED") {
    return [
      "ANN ha preparado el handoff para Architect Agent, pero no pudo iniciar el run en el backend.",
      "",
      `Backend: ${startPipeline.api_base}`,
      `Workspace objetivo: ${startPipeline.workspace_directory}`,
      `Error: ${startPipeline.error ?? "unknown"}`,
      "",
      "Cuando la API local esté levantada, este mismo mensaje podrá arrancar la pipeline real.",
    ].join("\n");
  }
  return null;
}

async function runCapabilities(names: string[], context: CapabilityContext) {
  const result: Record<string, unknown> = {};
  for (const name of names) {
    if (name === "get_model_inventory") result[name] = getModelInventoryCapability();
    else if (name === "get_runtime_status") result[name] = getRuntimeStatusCapability();
    else if (name === "get_active_project") result[name] = { status: "NO_ACTIVE_PROJECT", project: null, readOnly: true };
    else if (name === "get_recent_artifacts") result[name] = { status: "OK", artifacts: safeList("outputs", 10), readOnly: true };
    else if (name === "start_pipeline") result[name] = await startPipelineFromConversation(context);
    else result[name] = { status: "BLOCKED", error: "unknown_capability", readOnly: true };
  }
  return result;
}

function buildArchitectHandoff(context: CapabilityContext) {
  const { message, session, contract, risk } = context;
  const constraints = contract.explicit_constraints.length
    ? contract.explicit_constraints.map((constraint) => `- ${constraint}`).join("\n")
    : "- No extra user constraints captured.";
  const missing = contract.missing_information.length
    ? contract.missing_information.map((item) => `- ${item}`).join("\n")
    : "- None.";
  return [
    "# ANN CHAT HANDOFF TO ARCHITECT",
    "",
    "## Source",
    `Conversation ID: ${session.conversationId}`,
    `Request ID: ${contract.request_id}`,
    `Original user input: ${message}`,
    "",
    "## Intent Contract",
    `Primary intent: ${contract.primary_intent}`,
    `Recommended pipeline: ${contract.recommended_pipeline}`,
    `Risk: ${risk}`,
    `Requires confirmation: ${contract.requires_confirmation}`,
    `Requires human approval: ${contract.requires_human_approval}`,
    "",
    "## User Constraints",
    constraints,
    "",
    "## Missing Information",
    missing,
    "",
    "## Non-Negotiable Safety Rules",
    "- Preserve local-first execution.",
    "- Do not execute arbitrary shell commands from model output.",
    "- Do not install dependencies without explicit approval.",
    "- Do not apply patches without approval gates.",
    "- Keep generated work inside the selected workspace directory.",
    "- Produce diffs/proposed files before mutation when possible.",
    "",
    "## Architect Instructions",
    "Translate the user input into an implementation-ready engineering plan.",
    "Clarify domain assumptions only when required to avoid destructive or impossible work.",
    "Create architecture boundaries, major components, data model needs, API surface, frontend surface, test plan, security risks, and acceptance criteria.",
    "Hand off concrete tasks to Product, Planner, Frontend, Backend, Database, QA, Security, Documentation, Review, and Release agents.",
    "If the request is ambiguous but safe, make conservative assumptions and continue with reversible proposed artifacts.",
    "",
    "## Expected First Outputs",
    "- Requirements summary.",
    "- Architecture plan.",
    "- Task decomposition.",
    "- Risk register.",
    "- Proposed file changes or generated artifact list.",
    "- Approval requirements.",
  ].join("\n");
}

async function startPipelineFromConversation(context: CapabilityContext): Promise<StartPipelineCapability> {
  const workspace = normalizeWorkspaceDirectory(context.session.activeProject ?? DEFAULT_WORKSPACE_DIRECTORY);
  const handoff = buildArchitectHandoff(context);
  const base: StartPipelineCapability = {
    status: "PREPARED_NOT_EXECUTED",
    approvalRequired: true,
    readOnly: false,
    architect_handoff: handoff,
    workspace_directory: workspace,
    approval_mode: "supervised",
    api_base: API_BASE,
  };

  if (context.contract.missing_information.length > 0) {
    return { ...base, status: "BLOCKED_NEEDS_CLARIFICATION", error: context.contract.missing_information.join(" ") };
  }

  if (process.env.NODE_ENV === "test") {
    return { ...base, status: "RUN_PREPARED_TEST_MODE" };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(`${API_BASE.replace(/\/$/, "")}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idea: handoff.slice(0, 3900),
        workspace_directory: workspace,
        approval_mode: "supervised",
      }),
      signal: controller.signal,
    });
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (!response.ok) {
      return { ...base, status: "RUN_START_FAILED", error: String(body.detail ?? response.statusText) };
    }
    return {
      ...base,
      status: "RUN_STARTED",
      run_id: String(body.run_id ?? ""),
      run_status: String(body.status ?? "unknown"),
      pending_approvals: Number(body.pending_approvals ?? 0),
      workspace_directory: String(body.workspace_directory ?? workspace),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown_backend_error";
    return { ...base, status: "RUN_START_FAILED", error: message };
  } finally {
    clearTimeout(timeout);
  }
}

function normalizeWorkspaceDirectory(value: string) {
  const normalized = value.trim().replace(/\//g, "\\");
  if (/^[DE]:\\/i.test(normalized)) return normalized;
  return DEFAULT_WORKSPACE_DIRECTORY;
}

function getModelInventoryCapability() {
  const inventoryPath = path.join(/*turbopackIgnore: true*/ ROOT, "config", "ann_model_inventory.json");
  const payload = readJson(inventoryPath) as { models?: Record<string, unknown>[] } | null;
  const models = (payload?.models ?? []).map((model) => ({
    name: String(model.model_name ?? model.name ?? "unknown"),
    backend: String(model.backend ?? "unknown"),
    status: String(model.status ?? "unknown"),
    path: String(model.path ?? model.source_path ?? ""),
    enabled: Boolean(model.enabled),
    role: String(model.role ?? ""),
  }));
  return { status: "OK", readOnly: true, source: inventoryPath, models };
}

function getRuntimeStatusCapability() {
  const policyPath = path.join(/*turbopackIgnore: true*/ ROOT, "config", "ann_model_policy.json");
  const policy = readJson(policyPath) as Record<string, unknown> | null;
  return {
    status: "OK",
    readOnly: true,
    backend: String(policy?.default_backend ?? "unknown"),
    policy: Boolean(policy?.allow_real_model_load) ? "REAL_MODEL_LOAD_ENABLED" : "REAL_MODEL_LOAD_BLOCKED_BY_POLICY",
    realModelLoad: Boolean(policy?.allow_real_model_load),
    activeModels: 0,
    parallelLoads: 0,
    maxLoadedModels: Number(policy?.max_loaded_models ?? 1),
    vramPolicy: String(policy?.vram_policy ?? "SEQUENTIAL"),
  };
}

function getTerminalConversationRuntime() {
  const configPath = path.join(/*turbopackIgnore: true*/ ROOT, "config", "ann_terminal_conversation_runtime.json");
  const config = readJson(configPath) as Record<string, unknown> | null;
  return {
    allowRealInference: Boolean(config?.allow_real_inference),
    runtimeType: String(config?.runtime_type ?? "external_wsl_conda"),
    pythonExecutableWsl: String(config?.python_executable_wsl ?? "python3"),
    modelName: String(config?.model_name ?? "qwen3_4b_conversation_orchestrator"),
    modelPathWindows: String(config?.model_path_windows ?? ""),
    modelPathWsl: String(config?.model_path_wsl ?? ""),
    maxTokens: Number(config?.max_tokens ?? 160),
    contextTokens: Number(config?.context_tokens ?? 2048),
    temperature: Number(config?.temperature ?? 0.2),
    requireGpu: config?.require_gpu !== false,
    nGpuLayers: Number(config?.n_gpu_layers ?? -1),
    timeoutMs: Number(config?.timeout_ms ?? 180000),
  };
}

function isWslRuntimeReady(pythonExecutableWsl: string) {
  if (process.env.NODE_ENV === "test") return { ready: true, reason: "test_runtime_skipped" };
  try {
    const result = spawnSync(
      "wsl.exe",
      [
        "-e",
        pythonExecutableWsl,
        "-c",
        [
          "import importlib.util",
          "if importlib.util.find_spec('llama_cpp') is None: raise SystemExit(2)",
          "try:",
          "    import torch",
          "except Exception:",
          "    raise SystemExit(3)",
          "raise SystemExit(0 if torch.cuda.is_available() else 4)",
        ].join("\n"),
      ],
      { encoding: "utf8", timeout: 15000, shell: false, windowsHide: true },
    );
    if (result.status === 0) return { ready: true, reason: "llama_cpp_cuda_ready" };
    return { ready: false, reason: result.stderr?.trim() || result.stdout?.trim() || `exit_${result.status}` };
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown_runtime_error";
    return { ready: false, reason: message };
  }
}

function runRealConversationInference(input: {
  message: string;
  session: ConversationSession;
  model: ConversationModelState;
  contract: IntentContract;
  capabilities: Record<string, unknown>;
  needsApproval: boolean;
  needsClarification: boolean;
}): { text: string | null; events: TerminalConversationEvent[]; result?: Record<string, unknown> } {
  const { model } = input;
  if (process.env.NODE_ENV === "test") return { text: null, events: [] };
  if (model.backendKind !== "real" || !model.runtime) return { text: null, events: [] };

  const outputDir = path.join(/*turbopackIgnore: true*/ ROOT, "outputs", "conversation_runtime", `request-${cryptoRandomId()}`);
  fs.mkdirSync(outputDir, { recursive: true });
  const requestPath = path.join(/*turbopackIgnore: true*/ outputDir, "request.json");
  const resultPath = path.join(/*turbopackIgnore: true*/ outputDir, "result.json");
  const prompt = buildRealConversationPrompt(input);
  const requestPayload = {
    model_name: model.modelName,
    model_path_wsl: model.runtime.modelPathWsl,
    prompt,
    max_tokens: model.runtime.maxTokens,
    context_tokens: model.runtime.contextTokens,
    temperature: model.runtime.temperature,
    require_gpu: model.runtime.requireGpu,
    n_gpu_layers: model.runtime.nGpuLayers,
  };
  fs.writeFileSync(requestPath, JSON.stringify(requestPayload, null, 2), "utf8");

  const scriptPath = path.join(/*turbopackIgnore: true*/ ROOT, "scripts", "runtime", "run_conversation_llama_cpp.py");
  const result = spawnSync(
    "wsl.exe",
    [
      "-e",
      model.runtime.pythonExecutableWsl,
      toWslPath(scriptPath),
      "--request-json",
      toWslPath(requestPath),
    ],
    {
      cwd: ROOT,
      encoding: "utf8",
      timeout: model.runtime.timeoutMs,
      shell: false,
      windowsHide: true,
      maxBuffer: 1024 * 1024 * 4,
    },
  );

  const parsed = parseLastJsonLine(result.stdout);
  const diagnostic = {
    status: parsed?.status ?? "FAILED",
    exitCode: result.status,
    signal: result.signal,
    stdout: result.stdout?.slice(-4000) ?? "",
    stderr: result.stderr?.slice(-4000) ?? "",
    parsed,
    modelName: model.modelName,
    modelPath: model.expectedPath,
    activeModelsAfter: parsed?.active_models_after ?? 0,
    parallelLlmLoadsAfter: parsed?.parallel_llm_loads_after ?? 0,
    safeModeFinal: parsed?.safe_mode_final ?? true,
  };
  fs.writeFileSync(resultPath, JSON.stringify(diagnostic, null, 2), "utf8");

  const events: TerminalConversationEvent[] = [
    { kind: "status", text: `Preparando modelo real: ${model.displayName}` },
    { kind: "status", text: "Ejecutando inferencia local controlada" },
  ];
  if (parsed?.status === "PASSED" && typeof parsed.text === "string" && parsed.text.trim()) {
    events.push({ kind: "status", text: `Modelo descargado. active_models=${parsed.active_models_after ?? 0}, parallel_llm_loads=${parsed.parallel_llm_loads_after ?? 0}` });
    return { text: cleanAssistantVoice(parsed.text), events, result: diagnostic };
  }
  events.push({ kind: "error", text: `Real conversation inference failed; fallback deterministic response used. Artifact: ${resultPath}` });
  return { text: null, events, result: diagnostic };
}

function parseLastJsonLine(stdout: string | null | undefined): Record<string, unknown> | null {
  const lines = String(stdout ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const line of lines.reverse()) {
    try {
      const parsed = JSON.parse(line) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
    } catch {
      continue;
    }
  }
  return null;
}

function toWslPath(rawPath: string) {
  const normalized = rawPath.replace(/\\/g, "/");
  const match = normalized.match(/^([A-Za-z]):\/(.*)$/);
  if (!match) return normalized;
  return `/mnt/${match[1].toLowerCase()}/${match[2]}`;
}

function buildRealConversationPrompt(input: {
  message: string;
  session: ConversationSession;
  model: ConversationModelState;
  contract: IntentContract;
  capabilities: Record<string, unknown>;
  needsApproval: boolean;
  needsClarification: boolean;
}) {
  return [
    "<|im_start|>system",
    "Your name is ANN.",
    "ANN means Agentic Neural Network.",
    "You are the official voice of ANN to the user inside ANN Terminal.",
    "You are not a generic chatbot.",
    "You are able to converse directly with the user in ANN Terminal.",
    "Never say you cannot converse, cannot provide help in this context, or are only a limited assistant.",
    "Your mission is to understand the user's software-engineering intent, preserve constraints, build an ANN intent contract, select safe local pipelines, coordinate ANN agents, explain runtime/model state, and ask for approval before any write, shell, patch, install, deployment, or critical action.",
    "Your current capabilities: natural-language conversation, intent detection, requirement and constraint extraction, model inventory explanation, runtime diagnostics, pipeline selection, project analysis planning, debug/fix planning, test planning, security review routing, artifact explanation, approval handoff, and safe command guidance.",
    "You can talk naturally with the user. You can explain what ANN can do. You can prepare actions. You cannot directly execute shell commands, modify files, install dependencies, apply patches, bypass approvals, or claim tests ran without evidence.",
    "When the user greets you, introduce yourself as ANN and briefly state your purpose and capabilities.",
    "If a write action is needed, say it needs approval. Preserve explicit user constraints.",
    "Reply in the user's language. Be clear, direct, and confident. Do not mention internal JSON unless useful.",
    "<|im_end|>",
    "<|im_start|>user",
    "/no_think",
    JSON.stringify(
      {
        message: input.message,
        intent_contract: input.contract,
        capabilities: input.capabilities,
        pending_approval: input.needsApproval,
        pending_clarification: input.needsClarification,
        session: {
          conversation_id: input.session.conversationId,
          active_project: input.session.activeProject,
          active_task: input.session.activeTask,
        },
      },
      null,
      2,
    ),
    "<|im_end|>",
    "<|im_start|>assistant",
  ].join("\n");
}

function cleanAssistantVoice(text: string) {
  return text
    .replace(/Aunque actualmente no puedo realizar conversaciones directas como un asistente tradicional,?\s*/gi, "")
    .replace(/No soy capaz de realizar conversaciones o proporcionar ayuda en este contexto\.?\s*/gi, "")
    .replace(/Mi función es limitada y no puedo ejecutar comandos, modificar archivos, instalar dependencias o aplicar parches\.?\s*/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function inspectConversationModel(): ConversationModelState {
  const inventory = getModelInventoryCapability();
  const runtime = getRuntimeStatusCapability();
  const terminalRuntime = getTerminalConversationRuntime();
  const model =
    inventory.models.find((item) => item.name === terminalRuntime.modelName)
    ?? inventory.models.find((item) => item.role === "CONVERSATION_ORCHESTRATOR" && item.enabled && item.status !== "missing")
    ?? inventory.models.find((item) => item.name === "qwen3_4b_conversation_orchestrator");
  const expectedPath = terminalRuntime.modelPathWindows || model?.path || "D:/Models/qwen3-4b-instruct-2507-q4_k_m.gguf";
  const exists = fileExists(expectedPath);
  if (!model) {
    return {
      status: "MODEL_NOT_REGISTERED",
      displayName: "none",
      backendKind: "unavailable" as const,
      expectedPath,
      modelName: terminalRuntime.modelName || "none",
      reason: "Qwen3-4B Conversation Orchestrator is not registered.",
    };
  }
  if (!exists) {
    return {
      status: "MODEL_NOT_FOUND",
      displayName: "none",
      backendKind: "unavailable" as const,
      expectedPath,
      modelName: model.name,
      reason: `${model.name} is registered but the model file was not found. Expected: ${expectedPath}`,
    };
  }
  if (!terminalRuntime.allowRealInference) {
    return {
      status: "TERMINAL_REAL_INFERENCE_DISABLED",
      displayName: `${model.name} (simulated)`,
      backendKind: "fake" as const,
      expectedPath,
      modelName: model.name,
      reason: "Conversation mode is running with a simulated backend because terminal real inference is disabled.",
    };
  }
  if (runtime.activeModels > 0 || runtime.parallelLoads > 0) {
    return {
      status: "RUNTIME_BUSY",
      displayName: "none",
      backendKind: "unavailable" as const,
      expectedPath,
      modelName: model.name,
      reason: "Conversation mode is unavailable because another local model appears active.",
    };
  }
  const wslReady = isWslRuntimeReady(terminalRuntime.pythonExecutableWsl);
  if (!wslReady.ready) {
    return {
      status: "RUNTIME_UNAVAILABLE",
      displayName: "none",
      backendKind: "unavailable" as const,
      expectedPath,
      modelName: model.name,
      reason: `Conversation mode is unavailable because the local inference runtime is not ready: ${wslReady.reason}`,
    };
  }
  return {
    status: "REAL_BACKEND_READY",
    displayName: model.name,
    backendKind: "real" as const,
    expectedPath,
    modelName: model.name,
    reason: "Qwen3 real backend is available through the controlled external WSL runtime.",
    runtime: terminalRuntime,
  };
}

function extractConstraints(message: string) {
  const constraints: string[] = [];
  const text = message.toLowerCase();
  if (/no (toques|modifiques|cambies).*(base de datos|db|database)|sin .*base de datos/.test(text)) constraints.push("No modificar la base de datos.");
  if (/no apliques|sin aplicar|no aplicar/.test(text)) constraints.push("No aplicar parches todavía.");
  if (/solo.*tests|solo.*pruebas/.test(text)) constraints.push("Ejecutar solo tests relacionados.");
  if (/no instales|sin instalar/.test(text)) constraints.push("No instalar dependencias.");
  return constraints;
}

function safeList(relativePath: string, limit = 12): string[] {
  try {
    return fs
      .readdirSync(path.join(/*turbopackIgnore: true*/ ROOT, relativePath), { withFileTypes: true })
      .slice(0, limit)
      .map((entry) => `${entry.isDirectory() ? "dir " : "file"} ${path.join(/*turbopackIgnore: true*/ relativePath, entry.name)}`);
  } catch {
    return [`No entries found in ${relativePath}`];
  }
}

function tailAudit(limit = 8): string[] {
  try {
    return fs
      .readFileSync(path.join(/*turbopackIgnore: true*/ ROOT, "logs", "audit.jsonl"), "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-limit)
      .map((line) => {
        try {
          const parsed = JSON.parse(line) as Record<string, unknown>;
          return `${String(parsed.timestamp ?? "")} ${String(parsed.actor ?? parsed.component ?? "ANN")} ${String(parsed.message ?? parsed.event ?? "")}`.trim();
        } catch {
          return line;
        }
      });
  } catch {
    return ["No audit log available yet."];
  }
}

function terminalStatus(session: ConversationSession, model: ConversationModelState) {
  return {
    mode: labelMode(session.currentMode),
    status: session.pendingApproval ? "Waiting approval" : session.pendingClarification ? "Waiting clarification" : "Idle",
    model: model.displayName,
    backend: model.backendKind,
    activeModels: 0,
    parallelLlmLoads: 0,
    tokensPerSecond: null,
  };
}

function appendMessage(session: ConversationSession, role: ConversationSession["recentMessages"][number]["role"], text: string) {
  session.recentMessages.push({ role, text, at: new Date().toISOString() });
  session.recentMessages = session.recentMessages.slice(-30);
}

function normalizeCommand(input: string) {
  return input.trim().replace(/\s+/g, " ").toLowerCase();
}

function matchesExplicitShellAttempt(input: string) {
  return SHELL_ATTEMPT_PATTERNS.some((pattern) => pattern.test(input.trim()));
}

function labelMode(mode: TerminalInputMode) {
  if (mode === "chat") return "Chat";
  if (mode === "command") return "Command";
  return "Auto";
}

function readJson(filePath: string) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as unknown;
  } catch {
    return null;
  }
}

function fileExists(filePath: string) {
  const resolved = filePath.replace(/^D:\//i, "D:\\").replace(/\//g, "\\");
  return fs.existsSync(resolved);
}

function cryptoRandomId() {
  return Math.random().toString(36).slice(2, 10);
}
