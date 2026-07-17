import { describe, expect, it } from "vitest";
import {
  blockedShellAttemptResponse,
  classifyTerminalInput,
  getOrCreateSession,
  handleConversationMessage,
  handleModeCommand,
  runSafeTerminalCommand,
} from "./ann-terminal";

describe("ANN terminal conversation classifier", () => {
  it("routes greetings to conversation mode instead of safe command blocking", async () => {
    expect(classifyTerminalInput("hola", "auto")).toBe("CONVERSATION_MESSAGE");

    const session = getOrCreateSession("test-terminal-hola");
    const response = await handleConversationMessage("hola", session);

    expect(response.status).toBe("completed");
    expect(response.display_message).toMatch(/Hola\. Soy ANN|Conversation mode unavailable/);
    expect(response.intent_contract.primary_intent).toBe("general_conversation");
    expect(response.terminal_status.activeModels).toBe(0);
    expect(response.terminal_status.parallelLlmLoads).toBe(0);
  });

  it("keeps natural technical questions conversational without treating keywords as shell", () => {
    expect(classifyTerminalInput("qué puedes hacer", "auto")).toBe("CONVERSATION_MESSAGE");
    expect(classifyTerminalInput("por qué falla pip en el runtime", "auto")).toBe("CONVERSATION_MESSAGE");
  });

  it("keeps registered ANN commands on the safe allowlist path", () => {
    const session = getOrCreateSession("test-terminal-command");

    expect(classifyTerminalInput("models", "auto")).toBe("ANN_SAFE_COMMAND");

    const result = runSafeTerminalCommand("models", session);
    expect(result.status).toBe("ok");
    expect(result.lines.join("\n")).toContain("qwen");
  });

  it("supports explicit mode switching without executing anything", () => {
    const session = getOrCreateSession("test-terminal-mode");
    const response = handleModeCommand("mode chat", session);

    expect(response.status).toBe("completed");
    expect(session.currentMode).toBe("chat");
    expect(classifyTerminalInput("status", session.currentMode)).toBe("ANN_SAFE_COMMAND");

    handleModeCommand("mode command", session);
    expect(session.currentMode).toBe("command");
    expect(classifyTerminalInput("hola", session.currentMode)).toBe("MALFORMED_INPUT");
  });

  it("blocks explicit shell and package installation attempts", () => {
    const session = getOrCreateSession("test-terminal-blocked-shell");

    expect(classifyTerminalInput("pip install stripe", "auto")).toBe("EXPLICIT_SHELL_ATTEMPT");

    const response = blockedShellAttemptResponse("pip install stripe", session);
    expect(response.status).toBe("blocked");
    expect(response.display_message).toContain("No shell was executed");
    expect(response.terminal_status.activeModels).toBe(0);
    expect(response.terminal_status.parallelLlmLoads).toBe(0);
  });

  it("does not pretend Qwen3 conversation is real when unavailable or policy-blocked", async () => {
    const session = getOrCreateSession("test-terminal-model-truth");
    const response = await handleConversationMessage("que modelos tienes", session);
    const model = response.model;

    expect(["MODEL_NOT_FOUND", "SIMULATED_BACKEND", "REAL_BACKEND_READY", "MODEL_NOT_REGISTERED"]).toContain(model.status);
    if (model.status !== "REAL_BACKEND_READY") {
      expect(response.display_message).not.toContain("real backend is available for conversation orchestration");
    }
  });

  it("creates an intent contract and preserves user constraints for operational messages", async () => {
    const session = getOrCreateSession("test-terminal-contract");
    const response = await handleConversationMessage("arregla el login pero no cambies la base de datos", session);

    expect(response.intent_contract.contract_version).toBe("ann_intent_contract_v1");
    expect(response.intent_contract.primary_intent).toBe("debug_and_fix");
    expect(response.intent_contract.recommended_pipeline).toBe("debug_and_fix");
    expect(response.intent_contract.requires_human_approval).toBe(true);
    expect(response.intent_contract.explicit_constraints).toContain("No modificar la base de datos.");
    expect(response.approvals.length).toBe(1);
  });

  it("exposes read-only runtime and model capabilities through conversational requests", async () => {
    const session = getOrCreateSession("test-terminal-readonly-capabilities");
    const modelResponse = await handleConversationMessage("qué modelos están disponibles", session);
    const runtimeResponse = await handleConversationMessage("explícame por qué el runtime está bloqueado", session);

    expect(modelResponse.intent_contract.primary_intent).toBe("model_inventory_query");
    expect(modelResponse.capabilities.get_model_inventory).toMatchObject({ status: "OK", readOnly: true });
    expect(runtimeResponse.intent_contract.primary_intent).toBe("runtime_diagnostics_query");
    expect(runtimeResponse.capabilities.get_runtime_status).toMatchObject({ status: "OK", readOnly: true, activeModels: 0, parallelLoads: 0 });
  });

  it("turns software build requests into an Architect handoff instead of passive chat", async () => {
    const session = getOrCreateSession("test-terminal-architect-handoff");
    const response = await handleConversationMessage("Build me a SaaS CRM with auth and billing", session);
    const startPipeline = response.capabilities.start_pipeline as Record<string, unknown>;

    expect(response.intent_contract.primary_intent).toBe("software_build_request");
    expect(response.intent_contract.recommended_pipeline).toBe("project_creation");
    expect(startPipeline.status).toBe("RUN_PREPARED_TEST_MODE");
    expect(String(startPipeline.architect_handoff)).toContain("ANN CHAT HANDOFF TO ARCHITECT");
    expect(String(startPipeline.architect_handoff)).toContain("Build me a SaaS CRM with auth and billing");
    expect(response.display_message).toContain("Architect Agent");
  });
});
