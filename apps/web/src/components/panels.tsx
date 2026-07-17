"use client";

import {
  Check,
  Clock,
  FileCode2,
  FolderInput,
  GitBranch,
  Loader2,
  PencilLine,
  Play,
  Shield,
  SquareTerminal,
  X
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useWorkbench } from "@/store/workbench";

export type PanelId =
  | "chat"
  | "explorer"
  | "activity"
  | "timeline"
  | "terminal"
  | "diff"
  | "logs"
  | "files"
  | "approvals"
  | "security"
  | "readiness"
  | "senior"
  | "business"
  | "market"
  | "humanGates"
  | "riskRegister"
  | "confidence"
  | "architectureTradeoffs"
  | "securityRisks"
  | "complianceRoom"
  | "releaseBoard"
  | "intelligence";

export type PanelDefinition = {
  id: PanelId;
  title: string;
  component: () => ReactNode;
  size: "large" | "medium" | "small";
};

function ProgressIcon({ kind }: { kind: "command" | "edit" | "analysis" | "approval" }) {
  if (kind === "edit") return <PencilLine size={14} />;
  if (kind === "approval") return <Shield size={14} />;
  if (kind === "analysis") return <Clock size={14} />;
  return <SquareTerminal size={14} />;
}

export function ChatContent() {
  const [idea, setIdea] = useState("Build me a SaaS CRM");
  const [workspaceDirectory, setWorkspaceDirectory] = useState("D:\\AgenticEngineeringNetwork\\generated-projects");
  const [approvalMode, setApprovalMode] = useState<"supervised" | "full">("supervised");
  const messages = useWorkbench((state) => state.messages);
  const progressEvents = useWorkbench((state) => state.progressEvents);
  const activeRun = useWorkbench((state) => state.activeRun);
  const setActiveRun = useWorkbench((state) => state.setActiveRun);
  const appendTerminal = useWorkbench((state) => state.appendTerminal);
  const addMessage = useWorkbench((state) => state.addMessage);
  const addProgressEvent = useWorkbench((state) => state.addProgressEvent);
  const queryClient = useQueryClient();
  const runQuery = useQuery({
    queryKey: ["run", activeRun?.run_id],
    queryFn: () => api.getRun(activeRun?.run_id ?? ""),
    enabled: Boolean(activeRun?.run_id && ["running", "waiting_for_approval"].includes(activeRun.status)),
    refetchInterval: 2500
  });

  useEffect(() => {
    if (!runQuery.data || !activeRun || runQuery.data.run_id !== activeRun.run_id) return;
    const previousStatus = activeRun.status;
    setActiveRun(runQuery.data);
    if (previousStatus === "running" && runQuery.data.status === "waiting_for_approval") {
      appendTerminal(`Run ${runQuery.data.run_id} is waiting for ${runQuery.data.pending_approvals} approval gates.`);
      const messageId = progressEvents[progressEvents.length - 1]?.messageId ?? "welcome";
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "approval",
        label: `Esperando ${runQuery.data.pending_approvals} aprobaciones`
      });
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
    }
    if (previousStatus !== "completed" && runQuery.data.status === "completed") {
      appendTerminal(`Run ${runQuery.data.run_id} completed after approval gates.`);
      const messageId = progressEvents[progressEvents.length - 1]?.messageId ?? "welcome";
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "analysis",
        label: `Se planificaron ${runQuery.data.tasks.length} tareas`
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "command",
        label: `Se ejecutaron ${runQuery.data.agent_results.length} agentes`
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "edit",
        label: `Se editaron ${runQuery.data.proposed_files.length} archivos propuestos`
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "approval",
        label: "Aprobaciones resueltas; fase final completada"
      });
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
    }
    if (previousStatus !== "blocked" && runQuery.data.status === "blocked") {
      appendTerminal(`Run ${runQuery.data.run_id} blocked: ${runQuery.data.error ?? "approval rejected"}`);
    }
    if (previousStatus !== "failed" && runQuery.data.status === "failed") {
      appendTerminal(`Run ${runQuery.data.run_id} failed: ${runQuery.data.error ?? "unknown error"}`);
    }
  }, [activeRun, addProgressEvent, appendTerminal, progressEvents, queryClient, runQuery.data, setActiveRun]);

  const mutation = useMutation({
    mutationFn: api.createRun,
    onSuccess: (run, _input, context) => {
      const messageId = context?.assistantMessageId ?? crypto.randomUUID();
      setActiveRun(run);
      appendTerminal(`Run ${run.run_id} started in ${run.workspace_directory}.`);
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "analysis",
        label: "Run iniciado en segundo plano"
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "approval",
        label: `Modo de aprobación: ${run.approval_mode === "full" ? "total" : "supervisada"}`
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "approval",
        label: `Directorio de trabajo: ${run.workspace_directory}`
      });
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onMutate: () => {
      const userMessageId = crypto.randomUUID();
      const assistantMessageId = crypto.randomUUID();
      addMessage({ id: userMessageId, role: "user", text: idea });
      addMessage({
        id: assistantMessageId,
        role: "assistant",
        text: "Voy a analizar la idea, preparar el plan multi-agente, generar diffs y dejar cada operación pendiente de aprobación."
      });
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId: assistantMessageId,
        kind: "analysis",
        label: "Analizando requisitos y directorio de trabajo"
      });
      return { assistantMessageId };
    },
    onError: (error, _input, context) => {
      const messageId = context?.assistantMessageId ?? crypto.randomUUID();
      addProgressEvent({
        id: crypto.randomUUID(),
        messageId,
        kind: "approval",
        label: `No se inició: ${error.message}`
      });
      appendTerminal(`Run rejected before start: ${error.message}`);
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate({ idea, workspace_directory: workspaceDirectory, approval_mode: approvalMode });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="scrollbar flex-1 space-y-5 overflow-auto px-4 py-4">
        {messages.map((message) => {
          const events = progressEvents.filter((event) => event.messageId === message.id);
          return (
            <article key={message.id} className={message.role === "user" ? "ml-auto max-w-[86%]" : "max-w-[92%]"}>
              <p
                className={
                  message.role === "user"
                    ? "rounded-md border border-line bg-panel2 px-3 py-2 text-sm leading-6 text-text"
                    : "text-sm leading-6 text-text"
                }
              >
                {message.text}
              </p>
              {events.length ? (
                <div className="mt-3 space-y-2 text-xs text-muted">
                  {events.map((event) => (
                    <div key={event.id} className="flex items-center gap-2">
                      <ProgressIcon kind={event.kind} />
                      <span>{event.label}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          );
        })}
        {mutation.isPending ? (
          <div className="flex items-center gap-2 text-xs text-muted">
            <Loader2 size={14} className="animate-spin" />
            Procesando la ejecución actual
          </div>
        ) : null}
      </div>
      <form onSubmit={submit} className="border-t border-line bg-panel px-4 py-3">
        <div className="rounded-lg border border-line bg-canvas focus-within:border-accent">
          <textarea
            className="min-h-24 w-full resize-none bg-transparent px-3 py-3 text-sm leading-6 outline-none"
            value={idea}
            onChange={(event) => setIdea(event.target.value)}
            placeholder="Describe qué software quieres construir..."
          />
          <div className="flex flex-wrap items-center gap-2 border-t border-line px-2 py-2">
            <div className="flex min-w-[280px] flex-1 items-center gap-2 rounded border border-line bg-panel px-2">
              <FolderInput size={15} className="text-accent" />
              <input
                className="h-8 min-w-0 flex-1 bg-transparent text-xs text-text outline-none"
                value={workspaceDirectory}
                onChange={(event) => setWorkspaceDirectory(event.target.value)}
                aria-label="Workspace directory"
              />
            </div>
            <div className="inline-flex h-8 overflow-hidden rounded border border-line bg-panel text-xs">
              <button
                className={approvalMode === "supervised" ? "bg-accent px-2 font-semibold text-canvas" : "px-2 text-muted"}
                type="button"
                onClick={() => setApprovalMode("supervised")}
              >
                Supervisada
              </button>
              <button
                className={approvalMode === "full" ? "bg-accent px-2 font-semibold text-canvas" : "px-2 text-muted"}
                type="button"
                onClick={() => setApprovalMode("full")}
              >
                Total
              </button>
            </div>
            <button
              className="inline-flex h-8 items-center justify-center gap-2 rounded border border-accent bg-accent px-3 text-xs font-semibold text-canvas disabled:opacity-60"
              disabled={mutation.isPending}
              type="submit"
            >
              <Play size={14} />
              {mutation.isPending ? "Planning" : "Start"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

export function ProjectExplorerContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-start gap-2 text-muted">
        <GitBranch size={16} className="mt-0.5 shrink-0" />
        <span className="break-all">{activeRun?.workspace_directory ?? "D:\\AgenticEngineeringNetwork\\generated-projects"}</span>
      </div>
      {activeRun?.proposed_files.map((file) => (
        <div key={file.approval_id} className="flex items-center gap-2 pl-4 text-text">
          <FileCode2 size={15} /> {file.path.split(/[\\/]/).pop()}
        </div>
      )) ?? <p className="text-muted">No generated files yet.</p>}
    </div>
  );
}

export function AgentActivityFeedContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  const { data: logs } = useQuery({ queryKey: ["logs"], queryFn: api.logs, refetchInterval: 2000 });
  const liveEvents = (logs ?? []).filter((event) => {
    const metadata = event.metadata as Record<string, unknown> | undefined;
    const nested = metadata?.metadata as Record<string, unknown> | undefined;
    const runId = metadata?.run_id ?? nested?.parent_run_id;
    return (
      activeRun?.run_id &&
      runId === activeRun.run_id &&
      ["agent.started", "agent.decision"].includes(String(event.event_type))
    );
  });
  return (
    <div className="space-y-3">
      {activeRun?.agent_results.length ? (
        activeRun.agent_results.map((result, index) => (
          <article key={`${String(result.agent)}-${index}`} className="border-l-2 border-accent pl-3">
            <h3 className="text-sm font-semibold">{String(result.agent)}</h3>
            <p className="mt-1 text-xs leading-5 text-muted">{String(result.decision)}</p>
          </article>
        ))
      ) : liveEvents.length ? (
        liveEvents.map((event) => (
          <article key={String(event.event_id)} className="border-l-2 border-warn pl-3">
            <h3 className="text-sm font-semibold">{String(event.actor)}</h3>
            <p className="mt-1 text-xs leading-5 text-muted">{String(event.message)}</p>
          </article>
        ))
      ) : activeRun?.status === "running" ? (
        <p className="text-sm text-warn">Agents are starting. Waiting for first model event...</p>
      ) : (
        <p className="text-sm text-muted">Agents are idle.</p>
      )}
    </div>
  );
}

export function TaskTimelineContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  return (
    <div className="space-y-2 text-sm">
      {activeRun?.tasks.map((task) => (
        <div key={task.task_id} className="grid grid-cols-[20px_1fr] gap-2">
          <Clock size={15} className="mt-0.5 text-warn" />
          <div>
            <div className="font-medium">{task.title}</div>
            <div className="text-xs text-muted">{task.owner}</div>
          </div>
        </div>
      )) ?? <p className="text-muted">No tasks planned.</p>}
    </div>
  );
}

export function DiffViewerContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  const diff = activeRun?.proposed_files[0]?.diff ?? "No diff selected.";
  return <pre className="whitespace-pre-wrap text-xs leading-5 text-text">{diff}</pre>;
}

export function TerminalContent() {
  const lines = useWorkbench((state) => state.terminalLines);
  return <pre className="whitespace-pre-wrap text-xs leading-5 text-accent">{lines.join("\n")}</pre>;
}

export function LogsContent() {
  const { data } = useQuery({ queryKey: ["logs"], queryFn: api.logs, refetchInterval: 5000 });
  return (
    <div className="space-y-2 text-xs text-muted">
      {data?.map((event) => (
        <div key={String(event.event_id)} className="border-b border-line pb-2">
          <span className="text-text">{String(event.event_type)}</span> {String(event.actor)}
        </div>
      )) ?? "No audit events yet."}
    </div>
  );
}

export function GeneratedFilesContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  return (
    <div className="space-y-2 text-xs">
      {activeRun?.proposed_files.map((file) => (
        <div key={file.approval_id} className="border border-line bg-canvas p-2">
          <div className="font-semibold text-text">{file.path}</div>
          <div className="mt-1 text-muted">Approval: {file.approval_id}</div>
        </div>
      )) ?? <p className="text-muted">Generated artifacts will appear here.</p>}
    </div>
  );
}

export function ApprovalCenterContent() {
  const queryClient = useQueryClient();
  const activeRun = useWorkbench((state) => state.activeRun);
  const appendTerminal = useWorkbench((state) => state.appendTerminal);
  const { data } = useQuery({ queryKey: ["approvals"], queryFn: api.approvals, refetchInterval: 4000 });
  const mutation = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) => api.decideApproval(id, approved),
    onSuccess: (approval) => {
      appendTerminal(`${approval.status}: ${approval.title}`);
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
      if (activeRun?.run_id) {
        void queryClient.invalidateQueries({ queryKey: ["run", activeRun.run_id] });
      }
    }
  });

  return (
    <div className="space-y-2">
      {data?.map((approval) => (
        <article key={approval.approval_id} className="border border-line bg-canvas p-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold">{approval.title}</h3>
              <p className="mt-1 text-xs text-muted">{approval.approval_type} by {approval.requested_by}</p>
            </div>
            <span className="text-xs text-warn">{approval.status}</span>
          </div>
          {approval.status === "pending" ? (
            <div className="mt-3 flex gap-2">
              <button
                className="inline-flex h-8 items-center gap-1 rounded border border-accent px-2 text-xs text-accent"
                onClick={() => mutation.mutate({ id: approval.approval_id, approved: true })}
              >
                <Check size={14} /> Approve
              </button>
              <button
                className="inline-flex h-8 items-center gap-1 rounded border border-danger px-2 text-xs text-danger"
                onClick={() => mutation.mutate({ id: approval.approval_id, approved: false })}
              >
                <X size={14} /> Reject
              </button>
            </div>
          ) : null}
        </article>
      )) ?? <p className="text-sm text-muted">No approval requests.</p>}
    </div>
  );
}

export function SecurityContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  return (
    <div>
      <div className="flex items-center gap-2 text-sm">
        <Shield size={16} className={activeRun?.security_review.passed ? "text-accent" : "text-danger"} />
        {activeRun ? (activeRun.security_review.passed ? "Passed initial scan" : "Findings require review") : "Waiting for run"}
      </div>
      <ul className="mt-3 space-y-2 text-xs text-muted">
        {activeRun?.security_review.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </div>
  );
}

function sectionProgress(items: Array<{ status?: string; required?: boolean }>) {
  const done = items.filter((item) => item.status === "complete" || item.status === "configured").length;
  const required = items.filter((item) => item.required !== false).length || items.length;
  return `${done}/${required}`;
}

export function ProductionReadinessContent() {
  const [maxAttempts, setMaxAttempts] = useState(10);
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: api.readiness });
  const compliance = useQuery({ queryKey: ["compliance"], queryFn: api.compliance });
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: api.integrations, refetchInterval: 10000 });
  const billing = useQuery({ queryKey: ["billing-status"], queryFn: api.billingStatus, refetchInterval: 10000 });
  const templates = useQuery({ queryKey: ["saas-templates"], queryFn: api.saasTemplates });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const updateSettings = useMutation({ mutationFn: api.updateSettings });

  const configuredIntegrations = integrations.data?.providers.filter((provider) => provider.configured).length ?? 0;
  const totalIntegrations = integrations.data?.providers.length ?? 0;

  useEffect(() => {
    if (settings.data) {
      setMaxAttempts(settings.data.max_repair_attempts);
    }
  }, [settings.data]);

  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-text">SaaS readiness</h3>
          {readiness.isLoading ? <Loader2 size={14} className="animate-spin text-muted" /> : null}
        </div>
        <p className="text-xs leading-5 text-muted">{readiness.data?.disclaimer}</p>
        <div className="grid gap-2 md:grid-cols-2">
          {readiness.data?.sections.map((section) => (
            <article key={section.id} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text">{section.title}</span>
                <span className="text-xs text-accent">{sectionProgress(section.items)}</span>
              </div>
              <p className="mt-1 text-xs text-muted">{section.items[0]?.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-text">Integrations</h3>
          <span className="text-xs text-accent">{configuredIntegrations}/{totalIntegrations} configured</span>
        </div>
        <article className="border border-line bg-canvas p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-text">Stripe billing</span>
            <span className={billing.data?.configured ? "text-xs text-accent" : "text-xs text-warn"}>
              {billing.data?.mock_mode ? "mock mode" : "live configured"}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            Checkout, customer portal, and webhook endpoints are available through the API.
          </p>
        </article>
        <div className="grid gap-2 md:grid-cols-2">
          {integrations.data?.providers.map((provider) => (
            <article key={provider.provider} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text">{provider.provider}</span>
                <span className={provider.configured ? "text-xs text-accent" : "text-xs text-warn"}>{provider.mode}</span>
              </div>
              <p className="mt-1 text-xs text-muted">
                {provider.category} · {provider.required_env.length ? provider.required_env.join(", ") : "no secrets required"}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">Compliance dashboard</h3>
        <p className="text-xs leading-5 text-muted">{compliance.data?.disclaimer}</p>
        <div className="grid gap-2 md:grid-cols-2">
          {compliance.data?.sections.map((section) => (
            <article key={section.id} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text">{section.title}</span>
                <span className="text-xs text-warn">
                  {section.items.filter((item) => item.legal_review_required).length} legal
                </span>
              </div>
              <p className="mt-1 text-xs text-muted">{section.items[0]?.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">SaaS templates</h3>
        <div className="grid gap-2 md:grid-cols-2">
          {templates.data?.templates.map((template) => (
            <article key={template.id} className="border border-line bg-canvas p-2">
              <div className="font-medium text-text">{template.name}</div>
              <p className="mt-1 text-xs leading-5 text-muted">{template.description}</p>
              <p className="mt-2 text-xs text-accent">{template.core_entities.join(" · ")}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">Correction loop</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="h-8 w-24 rounded border border-line bg-canvas px-2 text-xs outline-none"
            min={1}
            max={50}
            type="number"
            value={maxAttempts}
            onChange={(event) => setMaxAttempts(Number(event.target.value))}
          />
          <button
            className="h-8 rounded border border-accent px-3 text-xs font-semibold text-accent disabled:opacity-60"
            disabled={updateSettings.isPending || settings.isLoading}
            onClick={() => updateSettings.mutate({ max_repair_attempts: maxAttempts })}
            type="button"
          >
            Save limit
          </button>
        </div>
        <p className="text-xs leading-5 text-muted">
          Active provider: {settings.data?.ai_provider ?? "unknown"} · Model: {settings.data?.local_model_path ?? "not loaded"}
        </p>
        <p className="text-xs leading-5 text-muted">
          {updateSettings.data?.message ?? settings.data?.notes[0] ?? "The correction loop stops and escalates after the configured limit."}
        </p>
      </section>
    </div>
  );
}

function gateClass(status: string) {
  if (status === "pass") return "text-accent";
  if (status === "fail") return "text-danger";
  return "text-warn";
}

function asRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function SimpleList({ items }: { items: unknown }) {
  const values = Array.isArray(items) ? items.map((item) => String(item)) : [];
  return (
    <ul className="space-y-1 text-xs text-muted">
      {values.slice(0, 8).map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

export function SeniorReviewContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  const idea = activeRun?.idea ?? "Build me a SaaS CRM with billing, tenant isolation, RBAC, tests, and deployment";
  const assessment = useQuery({
    queryKey: ["senior-assessment", idea],
    queryFn: () => api.seniorAssessment(idea)
  });

  if (assessment.isLoading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-muted">
        <Loader2 size={14} className="animate-spin" />
        Running senior review gates
      </div>
    );
  }

  if (assessment.isError) {
    return <p className="p-4 text-sm text-danger">Senior review failed: {assessment.error.message}</p>;
  }

  const data = assessment.data;
  const scoreEntries = Object.entries(data?.scorecard ?? {}).filter(([key]) => key !== "overall");
  const suiteCount = Array.isArray(data?.test_strategy.suites) ? data.test_strategy.suites.length : 0;

  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-text">Senior scorecard</h3>
          <span className="text-lg font-semibold text-accent">{data?.scorecard.overall ?? 0}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {scoreEntries.map(([key, value]) => (
            <article key={key} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-text">{key.replaceAll("_", " ")}</span>
                <span className="text-xs text-accent">{value}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded bg-panel2">
                <div className="h-full bg-accent" style={{ width: `${Math.max(0, Math.min(100, Number(value)))}%` }} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">Senior gates</h3>
        <div className="grid gap-2 md:grid-cols-2">
          {data?.gates.map((gate) => (
            <article key={gate.name} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text">{gate.name}</span>
                <span className={`text-xs ${gateClass(gate.status)}`}>{gate.status} · {gate.score}</span>
              </div>
              {gate.findings[0] ? (
                <p className="mt-1 text-xs leading-5 text-muted">{gate.findings[0].message}</p>
              ) : (
                <p className="mt-1 text-xs leading-5 text-muted">{gate.risks[0] ?? "No blocking findings."}</p>
              )}
              {gate.required_fixes.length ? (
                <p className="mt-2 text-xs text-warn">{gate.required_fixes[0]}</p>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">Release blockers</h3>
        {data?.release_blockers.length ? (
          <ul className="space-y-1 text-xs text-warn">
            {data.release_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        ) : (
          <p className="text-xs text-muted">No automatic senior gate has marked a hard release blocker. Human production sign-off is still required.</p>
        )}
      </section>

      <section className="grid gap-2 md:grid-cols-2">
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">SDLC phases</h3>
          <p className="mt-1 text-xs text-muted">{data?.sdlc_pipeline.length ?? 0} phases with inputs, outputs, checks, gates, and retry policy.</p>
        </article>
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">Test dashboard</h3>
          <p className="mt-1 text-xs text-muted">
            {suiteCount} suites: unit, integration, contract, E2E, security, smoke, regression.
          </p>
        </article>
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">Security review</h3>
          <p className="mt-1 text-xs text-muted">STRIDE, dependency, auth, RBAC, API abuse, validation, and rate-limit review are modeled.</p>
        </article>
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">Compliance evidence</h3>
          <p className="mt-1 text-xs text-muted">{data?.compliance_evidence.length ?? 0} evidence artifacts tracked; legal review remains required.</p>
        </article>
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-text">Human review required</h3>
        <ul className="space-y-1 text-xs text-muted">
          {data?.human_review_required.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </section>
    </div>
  );
}

export function BusinessContextContent() {
  const query = useQuery({ queryKey: ["business-context"], queryFn: api.businessContext, refetchInterval: 10000 });
  const context = (query.data?.context ?? {}) as Record<string, unknown>;
  const missing = Array.isArray(query.data?.critical_missing) ? query.data.critical_missing : [];
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Business Context Intake</h3>
      <p className={query.data?.approval_blocked ? "text-xs text-danger" : "text-xs text-accent"}>
        {query.data?.approval_blocked ? "Senior approval blocked: critical context missing." : "Critical context captured."}
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {["industry", "target_customer", "geography", "revenue_model", "budget", "timeline", "risk_tolerance", "compliance_needs"].map((field) => (
          <article key={field} className="border border-line bg-canvas p-2">
            <div className="text-xs font-medium text-text">{field.replaceAll("_", " ")}</div>
            <p className="mt-1 text-xs text-muted">{String(context[field] || "missing")}</p>
          </article>
        ))}
      </div>
      <p className="text-xs text-warn">Missing critical: {missing.map(String).join(", ") || "none"}</p>
    </div>
  );
}

export function MarketValidationContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  const query = useQuery({
    queryKey: ["market-validation", activeRun?.idea],
    queryFn: () => api.marketValidation(activeRun?.idea ?? "Build me a SaaS CRM")
  });
  const tasks = asRecords(query.data?.tasks);
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Market Validation Dashboard</h3>
      <p className="text-xs text-warn">Product approval status: {String(query.data?.product_approval_status ?? "evidence required")}</p>
      <section className="grid gap-2 md:grid-cols-2">
        {tasks.map((task) => (
          <article key={String(task.id)} className="border border-line bg-canvas p-2">
            <div className="font-medium text-text">{String(task.title)}</div>
            <p className="mt-1 text-xs text-warn">{String(task.status)}</p>
            <p className="mt-1 text-xs text-muted">{asRecords([]).length ? "" : Array.isArray(task.evidence_required) ? task.evidence_required.map(String).join(", ") : ""}</p>
          </article>
        ))}
      </section>
      <h4 className="text-xs font-semibold text-text">Interview script</h4>
      <SimpleList items={query.data?.interview_script} />
    </div>
  );
}

export function HumanApprovalGatesContent() {
  const queryClient = useQueryClient();
  const [approverName, setApproverName] = useState("");
  const [role, setRole] = useState("");
  const query = useQuery({ queryKey: ["human-gates"], queryFn: api.humanGates, refetchInterval: 5000 });
  const mutation = useMutation({
    mutationFn: api.decideHumanGate,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["human-gates"] })
  });
  const gates = Array.isArray(query.data?.required_gates) ? query.data.required_gates.map(String) : [];
  const missing = Array.isArray(query.data?.missing_gates) ? query.data.missing_gates.map(String) : [];
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Human Approval Gates</h3>
      <div className="grid gap-2 md:grid-cols-2">
        <input className="h-8 rounded border border-line bg-canvas px-2 text-xs outline-none" placeholder="Approver name" value={approverName} onChange={(event) => setApproverName(event.target.value)} />
        <input className="h-8 rounded border border-line bg-canvas px-2 text-xs outline-none" placeholder="Role" value={role} onChange={(event) => setRole(event.target.value)} />
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {gates.map((gate) => (
          <article key={gate} className="border border-line bg-canvas p-2">
            <div className="font-medium text-text">{gate.replaceAll("_", " ")}</div>
            <p className={missing.includes(gate) ? "mt-1 text-xs text-warn" : "mt-1 text-xs text-accent"}>{missing.includes(gate) ? "missing" : "approved"}</p>
            <button
              className="mt-2 h-7 rounded border border-accent px-2 text-xs text-accent disabled:opacity-50"
              disabled={!approverName || !role || mutation.isPending}
              onClick={() => mutation.mutate({ gate_id: gate, approver_name: approverName, role, decision: "approved", comments: "Approved from workbench.", risk_acceptance: "Owner accepts listed residual risks." })}
              type="button"
            >
              Approve
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}

export function RiskRegisterContent() {
  const query = useQuery({ queryKey: ["risks"], queryFn: api.risks, refetchInterval: 10000 });
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Risk Register</h3>
      <p className={query.data?.unresolved_critical ? "text-xs text-danger" : "text-xs text-accent"}>
        Unresolved critical risks: {query.data?.unresolved_critical ?? 0}
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {query.data?.risks.map((risk) => (
          <article key={risk.id} className="border border-line bg-canvas p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-text">{risk.risk_title}</span>
              <span className={risk.severity === "critical" ? "text-xs text-danger" : "text-xs text-warn"}>{risk.severity}</span>
            </div>
            <p className="mt-1 text-xs text-muted">{risk.category} · {risk.owner} · {risk.status}</p>
            <p className="mt-1 text-xs text-muted">{risk.mitigation}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export function ConfidenceDashboardContent() {
  const query = useQuery({ queryKey: ["confidence"], queryFn: api.confidence, refetchInterval: 10000 });
  const assessments = asRecords(query.data?.assessments);
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Confidence Dashboard</h3>
      <p className="text-xs leading-5 text-muted">{String(query.data?.responsibility_statement ?? "")}</p>
      <div className="grid gap-2 md:grid-cols-2">
        {assessments.map((assessment) => (
          <article key={String(assessment.area)} className="border border-line bg-canvas p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-text">{String(assessment.area).replaceAll("_", " ")}</span>
              <span className={String(assessment.confidence) === "blocked" ? "text-xs text-danger" : "text-xs text-accent"}>{String(assessment.confidence)}</span>
            </div>
            <p className="mt-1 text-xs text-muted">Evidence: {Array.isArray(assessment.evidence_used) ? assessment.evidence_used.map(String).join(", ") || "none" : "none"}</p>
            <p className="mt-1 text-xs text-warn">Missing: {Array.isArray(assessment.missing_evidence) ? assessment.missing_evidence.map(String).join(", ") : ""}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export function ArchitectureTradeoffContent() {
  const query = useQuery({ queryKey: ["architecture-uncertainty"], queryFn: api.architectureUncertainty });
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Architecture Tradeoff Review</h3>
      <p className="text-xs text-warn">Senior architect sign-off required: {String(query.data?.architect_signoff_required ?? true)}</p>
      <h4 className="text-xs font-semibold text-text">Tradeoffs</h4>
      <div className="grid gap-2 md:grid-cols-2">
        {asRecords(query.data?.tradeoff_analysis).map((item) => (
          <article key={String(item.decision)} className="border border-line bg-canvas p-2">
            <div className="font-medium text-text">{String(item.decision)}</div>
            <p className="mt-1 text-xs text-muted">Benefit: {String(item.benefit)}</p>
            <p className="mt-1 text-xs text-warn">Cost: {String(item.cost)}</p>
          </article>
        ))}
      </div>
      <h4 className="text-xs font-semibold text-text">Failure modes</h4>
      <SimpleList items={query.data?.failure_mode_analysis} />
    </div>
  );
}

export function SecurityRiskRegisterContent() {
  const query = useQuery({ queryKey: ["security-production-readiness"], queryFn: api.productionSecurityReadiness, refetchInterval: 10000 });
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Security Risk Register</h3>
      <p className={query.data?.production_blocked ? "text-xs text-danger" : "text-xs text-accent"}>
        Production blocked: {String(query.data?.production_blocked ?? true)}
      </p>
      <SimpleList items={query.data?.production_security_readiness_checklist} />
      <p className="text-xs text-warn">Penetration test required: {String(query.data?.penetration_test_required ?? true)}</p>
    </div>
  );
}

export function ComplianceEvidenceRoomContent() {
  const evidence = useQuery({ queryKey: ["compliance-evidence"], queryFn: api.complianceEvidence });
  const legal = useQuery({ queryKey: ["legal-workflow"], queryFn: api.legalWorkflow });
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Compliance Evidence Room</h3>
      <p className="text-xs text-danger">{String(legal.data?.draft_notice ?? "All legal outputs are drafts requiring qualified human review.")}</p>
      <div className="grid gap-2 md:grid-cols-2">
        {evidence.data?.evidence.map((item) => (
          <article key={String(item.control)} className="border border-line bg-canvas p-2">
            <div className="font-medium text-text">{String(item.control)}</div>
            <p className="mt-1 text-xs text-muted">{String(item.artifact)}</p>
            <p className={item.human_review_required ? "mt-1 text-xs text-warn" : "mt-1 text-xs text-accent"}>human review: {String(item.human_review_required)}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export function ReleaseReadinessBoardContent() {
  const query = useQuery({ queryKey: ["release-readiness"], queryFn: api.releaseReadiness, refetchInterval: 10000 });
  const blockers = Array.isArray(query.data?.blockers) ? query.data.blockers.map(String) : [];
  return (
    <div className="space-y-3 text-sm">
      <h3 className="font-semibold text-text">Release Readiness Board</h3>
      <p className={query.data?.status === "blocked" ? "text-xs text-danger" : "text-xs text-accent"}>Status: {String(query.data?.status ?? "blocked")}</p>
      <p className="text-xs leading-5 text-muted">{String(query.data?.responsibility_statement ?? "")}</p>
      {blockers.length ? <SimpleList items={blockers} /> : <p className="text-xs text-muted">No release blockers detected by automated checks.</p>}
    </div>
  );
}

export function IntelligenceCommandCenterContent() {
  const activeRun = useWorkbench((state) => state.activeRun);
  const idea = activeRun?.idea ?? "Build me a SaaS CRM with billing, RBAC, tests, and deployment";
  const suite = useQuery({ queryKey: ["intelligence-suite", idea], queryFn: () => api.intelligenceSuite(idea) });
  const simulations = useQuery({ queryKey: ["simulations"], queryFn: () => api.simulations({ monthly_visitors: 1000, conversion_rate: 0.03, price: 29 }) });
  const packets = useQuery({ queryKey: ["approval-packets"], queryFn: api.approvalPackets });

  const sections = ["product", "architecture", "security", "compliance", "release"];
  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-2">
        <h3 className="font-semibold text-text">Intelligence Command Center</h3>
        <p className="text-xs leading-5 text-muted">{String(suite.data?.responsibility_statement ?? "")}</p>
      </section>
      <section className="grid gap-2 md:grid-cols-2">
        {sections.map((section) => {
          const data = (suite.data?.[section] ?? {}) as Record<string, unknown>;
          const conclusion = (data.conclusion ?? {}) as Record<string, unknown>;
          return (
            <article key={section} className="border border-line bg-canvas p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text">{section}</span>
                <span className={String(conclusion.confidence) === "blocked" ? "text-xs text-danger" : "text-xs text-accent"}>
                  {String(conclusion.confidence ?? "unknown")}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted">
                Evidence: {Array.isArray(conclusion.evidence) ? conclusion.evidence.map(String).join(", ") : "pending"}
              </p>
              <p className="mt-1 text-xs text-warn">
                Human validation: {Array.isArray(conclusion.human_validation_required) ? conclusion.human_validation_required.map(String).join(", ") : "required"}
              </p>
            </article>
          );
        })}
      </section>
      <section className="grid gap-2 md:grid-cols-2">
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">Simulation estimates</h3>
          <p className="mt-1 text-xs text-warn">{String(simulations.data?.estimate_notice ?? "Simulations are estimates, not guarantees.")}</p>
          <p className="mt-1 text-xs text-muted">MRR: {String((simulations.data?.pricing as Record<string, unknown> | undefined)?.monthly_recurring_revenue ?? "n/a")}</p>
          <p className="mt-1 text-xs text-muted">Infra: {String((simulations.data?.infrastructure_costs as Record<string, unknown> | undefined)?.monthly_usd ?? "n/a")}</p>
        </article>
        <article className="border border-line bg-canvas p-2">
          <h3 className="font-semibold text-text">Approval packets</h3>
          <p className="mt-1 text-xs text-muted">{asRecords(packets.data?.packets).length} owner packets prepared.</p>
          <p className="mt-1 text-xs text-warn">Every packet still requires a named human decision.</p>
        </article>
      </section>
    </div>
  );
}

export const panelDefinitions: PanelDefinition[] = [
  { id: "chat", title: "Codex Console", component: ChatContent, size: "large" },
  { id: "explorer", title: "Project Explorer", component: ProjectExplorerContent, size: "small" },
  { id: "activity", title: "Agent Activity", component: AgentActivityFeedContent, size: "medium" },
  { id: "timeline", title: "Task Timeline", component: TaskTimelineContent, size: "medium" },
  { id: "terminal", title: "Terminal Output", component: TerminalContent, size: "medium" },
  { id: "diff", title: "Diff Viewer", component: DiffViewerContent, size: "large" },
  { id: "logs", title: "Logs", component: LogsContent, size: "medium" },
  { id: "files", title: "Generated Files", component: GeneratedFilesContent, size: "medium" },
  { id: "approvals", title: "Approval Center", component: ApprovalCenterContent, size: "medium" },
  { id: "security", title: "Security Review", component: SecurityContent, size: "small" },
  { id: "readiness", title: "Production Readiness", component: ProductionReadinessContent, size: "large" },
  { id: "senior", title: "Senior Review", component: SeniorReviewContent, size: "large" },
  { id: "business", title: "Business Context Intake", component: BusinessContextContent, size: "large" },
  { id: "market", title: "Market Validation", component: MarketValidationContent, size: "large" },
  { id: "humanGates", title: "Human Approval Gates", component: HumanApprovalGatesContent, size: "large" },
  { id: "riskRegister", title: "Risk Register", component: RiskRegisterContent, size: "large" },
  { id: "confidence", title: "Confidence Dashboard", component: ConfidenceDashboardContent, size: "large" },
  { id: "architectureTradeoffs", title: "Architecture Tradeoffs", component: ArchitectureTradeoffContent, size: "large" },
  { id: "securityRisks", title: "Security Risk Register", component: SecurityRiskRegisterContent, size: "medium" },
  { id: "complianceRoom", title: "Compliance Evidence Room", component: ComplianceEvidenceRoomContent, size: "large" },
  { id: "releaseBoard", title: "Release Readiness Board", component: ReleaseReadinessBoardContent, size: "large" },
  { id: "intelligence", title: "Intelligence Command Center", component: IntelligenceCommandCenterContent, size: "large" }
];

export function usePanel(panelId: string | null) {
  return useMemo(
    () => panelDefinitions.find((panel) => panel.id === panelId) ?? panelDefinitions[0],
    [panelId]
  );
}
