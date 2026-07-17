export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

export type Agent = {
  name: string;
  role: string;
  goals: string[];
  tools: string[];
  outputs: string[];
};

export type EngineeringRun = {
  run_id: string;
  idea: string;
  workspace_directory: string;
  approval_mode: "full" | "supervised";
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  pending_approvals: number;
  execution_results?: Record<string, unknown> | null;
  tasks: Array<{
    title: string;
    owner: string;
    description: string;
    dependencies?: string[];
    task_id?: string;
    status?: string;
  }>;
  agent_results: Array<Record<string, unknown>>;
  proposed_files: Array<{ path: string; diff: string; approval_id: string }>;
  security_review: { passed: boolean; findings: unknown[]; notes: string[] };
};

export type Approval = {
  approval_id: string;
  approval_type: string;
  title: string;
  description: string;
  requested_by: string;
  status: string;
  payload: Record<string, unknown>;
};

export type ChecklistItem = {
  id: string;
  title: string;
  description: string;
  required?: boolean;
  status?: string;
  legal_review_required?: boolean;
};

export type ChecklistSection = {
  id: string;
  title: string;
  items: ChecklistItem[];
};

export type IntegrationStatus = {
  provider: string;
  category: string;
  mode: string;
  configured: boolean;
  required_env: string[];
};

export type SaasTemplate = {
  id: string;
  name: string;
  description: string;
  core_entities: string[];
  workflows: string[];
  integrations: string[];
};

export type SeniorFinding = {
  severity: string;
  area: string;
  message: string;
  recommendation: string;
};

export type SeniorGate = {
  name: string;
  status: "pass" | "fail" | "needs_human_review";
  score: number;
  findings: SeniorFinding[];
  risks: string[];
  required_fixes: string[];
  optional_improvements: string[];
  human_review_notes: string[];
};

export type SeniorAssessment = {
  idea: string;
  weak_before: string[];
  gates: SeniorGate[];
  scorecard: Record<string, number>;
  release_blockers: string[];
  human_review_required: string[];
  product_discovery: Record<string, unknown>;
  requirements_quality: Record<string, unknown>;
  sdlc_pipeline: Array<Record<string, unknown>>;
  test_strategy: Record<string, unknown>;
  threat_model: Record<string, unknown>;
  compliance_evidence: Array<Record<string, unknown>>;
};

export type BusinessContextInput = {
  industry?: string;
  target_customer?: string;
  geography?: string;
  revenue_model?: string;
  budget?: string;
  timeline?: string;
  risk_tolerance?: string;
  compliance_needs?: string;
  operational_constraints?: string;
  existing_tools?: string[];
  competitors?: string[];
};

export type HumanGateDecisionInput = {
  gate_id: string;
  approver_name: string;
  role: string;
  decision: "approved" | "rejected" | "needs_changes";
  comments?: string;
  risk_acceptance?: string;
};

export type RiskItem = {
  id: string;
  risk_title: string;
  category: string;
  severity: string;
  likelihood: string;
  owner: string;
  mitigation: string;
  status: string;
  accepted_by: string;
  review_date: string;
};

export type AgentOfficeStatus =
  | "idle"
  | "thinking"
  | "planning"
  | "coding"
  | "testing"
  | "reviewing"
  | "blocked"
  | "waiting approval"
  | "completed"
  | "failed";

export type AgentOfficeEvent = {
  id: string;
  agentId: string;
  agentName: string;
  type: AgentOfficeStatus | string;
  message: string;
  createdAt: string;
};

export type AgentOfficeAgent = {
  id: string;
  name: string;
  role: string;
  status: AgentOfficeStatus;
  currentTask: string;
  progress: number;
  position: { x: number; y: number };
  deskId: string;
  lastActivityAt: string;
  events: AgentOfficeEvent[];
  confidence: number;
  blockedReason: string | null;
  approvalRequired: boolean;
};

export type AgentOfficeState = {
  provider: "live" | "mock";
  runId?: string | null;
  runStatus?: string;
  generatedAt: string;
  office: { width: number; height: number; theme: string };
  agents: AgentOfficeAgent[];
  events: AgentOfficeEvent[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = init?.signal ? null : new AbortController();
  const timeout = controller
    ? globalThis.setTimeout(() => controller.abort(), 8000)
    : undefined;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    signal: init?.signal ?? controller?.signal,
    ...init
  }).finally(() => {
    if (timeout != null) globalThis.clearTimeout(timeout);
  });
  if (!response.ok) {
    const text = await response.text();
    let parsed: { detail?: unknown } | null = null;
    try {
      parsed = JSON.parse(text) as { detail?: unknown };
    } catch {
      parsed = null;
    }
    if (typeof parsed?.detail === "string") {
      throw new Error(parsed.detail);
    }
    if (Array.isArray(parsed?.detail)) {
      throw new Error(parsed.detail.map((item) => String(item.msg ?? "Validation error")).join("; "));
    }
    throw new Error(text);
  }
  return response.json() as Promise<T>;
}

export const api = {
  agents: () => request<Agent[]>("/agents"),
  agentOfficeState: () => request<AgentOfficeState>("/agent-office/state"),
  agentOfficeEvents: (limit = 50) => request<{ events: AgentOfficeEvent[] }>(`/agent-office/events?limit=${limit}`),
  approvals: () => request<Approval[]>("/approvals"),
  logs: () => request<Array<Record<string, unknown>>>("/logs/audit"),
  auditLogs: (limit = 100) => request<Array<Record<string, unknown>>>(`/logs/audit?limit=${limit}`),
  readiness: () => request<{ title: string; disclaimer: string; sections: ChecklistSection[] }>("/readiness"),
  compliance: () => request<{ title: string; disclaimer: string; sections: ChecklistSection[] }>("/compliance"),
  integrations: () => request<{ providers: IntegrationStatus[] }>("/integrations/status"),
  billingStatus: () =>
    request<{
      provider: string;
      configured: boolean;
      mock_mode: boolean;
      publishable_key_present: boolean;
      price_id_present: boolean;
      webhook_secret_present: boolean;
    }>("/billing/status"),
  createCheckout: (input: { customer_email: string; tenant_id: string }) =>
    request<Record<string, unknown>>("/billing/checkout", { method: "POST", body: JSON.stringify(input) }),
  createPortal: (input: { customer_id: string }) =>
    request<Record<string, unknown>>("/billing/portal", { method: "POST", body: JSON.stringify(input) }),
  saasTemplates: () => request<{ templates: SaasTemplate[] }>("/saas-templates"),
  settings: () =>
    request<{
      max_repair_attempts: number;
      repair_backoff_base_seconds: number;
      repair_backoff_max_seconds: number;
      ai_provider: string;
      local_model_path: string;
      notes: string[];
    }>("/settings"),
  updateSettings: (input: { max_repair_attempts: number }) =>
    request<{ max_repair_attempts: number; requires_restart: boolean; message: string }>("/settings", {
      method: "POST",
      body: JSON.stringify(input)
    }),
  refineRequirements: (idea: string) => request<Record<string, unknown>>("/requirements/refine", { method: "POST", body: JSON.stringify({ idea }) }),
  seniorAssessment: (idea: string) =>
    request<SeniorAssessment>("/senior-review/assess", { method: "POST", body: JSON.stringify({ idea }) }),
  seniorStandards: () => request<Record<string, unknown>>("/senior-review/standards"),
  sdlcPipeline: () => request<{ phases: Array<Record<string, unknown>> }>("/sdlc/pipeline"),
  testStrategy: () => request<Record<string, unknown>>("/testing/strategy"),
  threatModel: () => request<Record<string, unknown>>("/security/threat-model"),
  complianceEvidence: () => request<{ evidence: Array<Record<string, unknown>> }>("/compliance/evidence"),
  marketValidation: (idea: string) =>
    request<Record<string, unknown>>("/market-validation", { method: "POST", body: JSON.stringify({ idea }) }),
  intelligenceSuite: (idea: string) =>
    request<Record<string, unknown>>("/intelligence/suite", { method: "POST", body: JSON.stringify({ idea }) }),
  productIntelligence: (idea: string) =>
    request<Record<string, unknown>>("/intelligence/product", { method: "POST", body: JSON.stringify({ idea }) }),
  architectureIntelligence: () => request<Record<string, unknown>>("/intelligence/architecture"),
  securityIntelligence: () => request<Record<string, unknown>>("/intelligence/security"),
  complianceIntelligence: () => request<Record<string, unknown>>("/intelligence/compliance"),
  releaseIntelligence: () => request<Record<string, unknown>>("/intelligence/release"),
  simulations: (input: { monthly_visitors?: number; conversion_rate?: number; price?: number }) =>
    request<Record<string, unknown>>("/simulations", { method: "POST", body: JSON.stringify(input) }),
  approvalPackets: () => request<Record<string, unknown>>("/approval-packets"),
  businessContext: () => request<Record<string, unknown>>("/business-context"),
  saveBusinessContext: (input: BusinessContextInput) =>
    request<Record<string, unknown>>("/business-context", { method: "POST", body: JSON.stringify(input) }),
  humanGates: () => request<Record<string, unknown>>("/human-gates"),
  decideHumanGate: (input: HumanGateDecisionInput) =>
    request<Record<string, unknown>>("/human-gates", { method: "POST", body: JSON.stringify(input) }),
  risks: () => request<{ risks: RiskItem[]; unresolved_critical: number }>("/risks"),
  saveRisks: (risks: RiskItem[]) => request<{ risks: RiskItem[]; unresolved_critical: number }>("/risks", { method: "POST", body: JSON.stringify({ risks }) }),
  confidence: () => request<Record<string, unknown>>("/confidence"),
  architectureUncertainty: () => request<Record<string, unknown>>("/architecture/uncertainty"),
  legalWorkflow: () => request<Record<string, unknown>>("/legal/workflow"),
  productionSecurityReadiness: () => request<Record<string, unknown>>("/security/production-readiness"),
  releaseReadiness: () => request<Record<string, unknown>>("/release/readiness"),
  runs: (limit = 25) => request<EngineeringRun[]>(`/runs?limit=${limit}`),
  getRun: (runId: string) => request<EngineeringRun>(`/runs/${runId}`),
  createRun: (input: { idea: string; workspace_directory?: string; approval_mode?: "full" | "supervised" }) =>
    request<EngineeringRun>("/runs", { method: "POST", body: JSON.stringify(input) }),
  decideApproval: (approvalId: string, approved: boolean) =>
    request<Approval>(`/approvals/${approvalId}`, {
      method: "POST",
      body: JSON.stringify({ approved })
    })
};
