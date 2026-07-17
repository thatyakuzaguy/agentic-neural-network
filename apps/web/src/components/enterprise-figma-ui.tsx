"use client";

import { useState, useEffect, useRef } from "react";
import {
  LayoutDashboard, FolderOpen, Workflow, Brain, Database, Activity,
  Archive, FileText, Settings, Play, Square, RefreshCw,
  Plus, Search, Bell, CheckCircle2, Clock, Loader2, AlertCircle,
  XCircle, Cpu, HardDrive, Zap, Code2, Shield, GitBranch,
  ChevronRight, ChevronDown, ChevronUp, Circle, ArrowDown, User,
  TrendingUp, Package, Terminal, Eye, FlaskConical,
  Server, Network, Hash, Filter, Download, Lock, ChevronLeft
} from "lucide-react";
import { api, type AgentOfficeAgent, type AgentOfficeEvent, type AgentOfficeState, type Approval, type EngineeringRun } from "@/lib/api";

type PageId = "dashboard" | "projects" | "pipeline" | "models" | "knowledge" | "runtime" | "artifacts" | "approvals" | "logs" | "settings";
type StageStatus = "complete" | "running" | "pending" | "error" | "blocked" | "skipped";

interface Stage {
  id: string; num: number; name: string;
  type: "input" | "agent" | "system" | "output";
  status: StageStatus; model?: string; duration: string;
  confidence?: number; tokens?: number;
  artifacts?: { name: string; ext: string }[];
  isLoop?: boolean; isConditional?: boolean; note?: string;
}

interface RuntimeData {
  gpu: number; vramUsed: number; vramTotal: number;
  ramUsed: number; ramTotal: number; cpu: number;
  tokensPerSec: number; activeModel: string; activeStage: string;
  uptime: string; gpuModel: string; pipelineId: string;
  status: "live" | "partial" | "unavailable";
  gpuSource: string; gpuCuda: number;
  loadedModels: { id: string; name: string; status: string; tps: number; usedVramGb: number }[];
  errors: string[];
}

type UiEntry = {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number;
  modifiedAt: string;
};

type UiLogEntry = {
  level: string;
  time: string;
  agent: string;
  msg: string;
};

type UiState = {
  root: string;
  sampledAt: string;
  projects: UiEntry[];
  artifacts: UiEntry[];
  docs: UiEntry[];
  models: UiEntry[];
  logs: UiLogEntry[];
  settings: {
    approvalMode: string;
    workspaceRoot: string;
    terminalMode: string;
    network: string;
  };
};

type UiBrowseResponse = {
  kind: "directory" | "file";
  path: string;
  entries?: UiEntry[];
  name?: string;
  size?: number;
  modifiedAt?: string;
  previewable?: boolean;
  content?: string | null;
};

type BackendSettings = Awaited<ReturnType<typeof api.settings>>;

type UiLoadState = "loading" | "ready" | "error";

type RecentRunRow = {
  id: string;
  task: string;
  status: "running" | "complete" | "error" | "blocked";
  duration: string;
  loc: string;
  time: string;
};

type ActivityRow = {
  t: string;
  agent: string;
  action: string;
  color: string;
};

type AppNotice = {
  title: string;
  message: string;
  tone: "info" | "success" | "warning" | "error";
};

type TerminalLine = {
  type: "system" | "cmd" | "info" | "ok" | "run" | "blank" | "error" | "assistant" | "approval" | "pipeline";
  text: string;
};

type TerminalConversationEvent = {
  kind: "status" | "assistant" | "command" | "error" | "approval" | "pipeline" | "system";
  text: string;
};

type TerminalConversationResponse = {
  status?: string;
  display_message?: string;
  pipeline?: string | null;
  approvals?: Array<{ id: string; pipeline: string; risk: string }>;
  capabilities?: {
    start_pipeline?: {
      status?: string;
      run_id?: string;
      run_status?: string;
      pending_approvals?: number;
      workspace_directory?: string;
    };
  };
  mode?: "auto" | "chat" | "command" | "Auto" | "Chat" | "Command";
  input_classification?: string;
  events?: TerminalConversationEvent[];
  terminal_status?: {
    mode?: string;
    status?: string;
    model?: string;
    backend?: string;
    activeModels?: number;
    parallelLlmLoads?: number;
  };
  model?: {
    displayName?: string;
    backendKind?: string;
    status?: string;
    reason?: string;
  };
};

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "projects",  label: "Projects",  icon: FolderOpen },
  { id: "pipeline",  label: "Pipeline",  icon: Workflow },
  { id: "models",    label: "Models",    icon: Brain },
  { id: "knowledge", label: "Knowledge", icon: Database },
  { id: "runtime",   label: "Runtime",   icon: Activity },
  { id: "artifacts", label: "Artifacts", icon: Archive },
  { id: "approvals", label: "Approvals", icon: Shield },
  { id: "logs",      label: "Logs",      icon: FileText },
  { id: "settings",  label: "Settings",  icon: Settings },
] as const;

const S = {
  complete: { color: "#00c896", bg: "rgba(0,200,150,0.08)", border: "rgba(0,200,150,0.28)", label: "Complete", Icon: CheckCircle2 },
  running:  { color: "#00d0ff", bg: "rgba(0,208,255,0.08)", border: "rgba(0,208,255,0.38)", label: "Running",  Icon: Loader2 },
  pending:  { color: "#445577", bg: "rgba(68,85,119,0.08)", border: "rgba(68,85,119,0.22)", label: "Pending",  Icon: Circle },
  error:    { color: "#ff3757", bg: "rgba(255,55,87,0.08)", border: "rgba(255,55,87,0.3)",  label: "Error",    Icon: AlertCircle },
  blocked:  { color: "#f5a623", bg: "rgba(245,166,35,0.08)", border: "rgba(245,166,35,0.3)", label: "Blocked", Icon: Lock },
  skipped:  { color: "#334466", bg: "rgba(51,68,102,0.05)", border: "rgba(51,68,102,0.15)", label: "Skipped",  Icon: XCircle },
};

const TERMINAL_LINES: TerminalLine[] = [
  { type: "system", text: "ANN OS v2.4.1 — Agentic Neural Network Operating System" },
  { type: "system", text: "Session: local desktop runtime · Conversation classifier active" },
  { type: "blank", text: "" },
  { type: "info",   text: "Write naturally to talk with ANN, or type help, status, logs, projects, artifacts, models, runtime, or clear." },
  { type: "info",   text: "Natural language goes through /api/conversation/message. Safe commands still use the allowlist and never use arbitrary shell execution." },
];

const INIT_RUNTIME: RuntimeData = {
  gpu: 0, vramUsed: 0, vramTotal: 0,
  ramUsed: 0, ramTotal: 0, cpu: 0,
  tokensPerSec: 0, activeModel: "Detecting runtime...",
  activeStage: "Sampling local telemetry", uptime: "—",
  gpuModel: "Detecting", pipelineId: "Idle",
  status: "partial", gpuSource: "starting", gpuCuda: 0,
  loadedModels: [], errors: [],
};

async function localJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

function clamp(v: number, lo: number, hi: number) { return Math.min(hi, Math.max(lo, v)); }

function formatClock(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(startValue?: string | null, endValue?: string | null) {
  if (!startValue) return "—";
  const start = new Date(startValue).getTime();
  const end = endValue ? new Date(endValue).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

function formatConfidence(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "—";
  const percentage = value <= 1 ? value * 100 : value;
  return `${Math.round(percentage)}%`;
}

function displayRunIdea(idea?: string | null) {
  if (!idea?.trim()) return "Untitled engineering run";
  const originalInput = idea.match(/^Original user input:\s*(.+)$/im)?.[1]?.trim();
  return originalInput || idea.trim();
}

function formatSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function entryRows(entries: UiEntry[], fallback: RecentRunRow[] = []): RecentRunRow[] {
  if (entries.length === 0) return fallback;
  return entries.slice(0, 5).map((entry, index) => ({
    id: entry.path || `${entry.name}-${index}`,
    task: entry.name,
    status: "complete",
    duration: "—",
    loc: entry.type === "directory" ? "workspace" : formatSize(entry.size),
    time: formatClock(entry.modifiedAt),
  }));
}

function eventColor(type: string) {
  const lower = type.toLowerCase();
  if (lower.includes("fail") || lower.includes("block")) return "#ff3757";
  if (lower.includes("review") || lower.includes("plan")) return "#7c3aed";
  if (lower.includes("wait") || lower.includes("approval")) return "#f5a623";
  if (lower.includes("complete")) return "#00c896";
  return "#00d0ff";
}

function latestRun(runs: EngineeringRun[]): EngineeringRun | null {
  return runs[0] ?? null;
}

function runStatus(status: string): RecentRunRow["status"] {
  if (["completed", "complete", "passed"].includes(status)) return "complete";
  if (status === "blocked") return "blocked";
  if (["failed", "error"].includes(status)) return "error";
  return "running";
}

function runRows(runs: EngineeringRun[], localEntries: UiEntry[]): RecentRunRow[] {
  if (runs.length > 0) {
    return runs.slice(0, 8).map((run) => ({
      id: run.run_id,
      task: displayRunIdea(run.idea),
      status: runStatus(run.status),
      duration: run.pending_approvals > 0
        ? `${run.pending_approvals} approvals`
        : formatDuration(run.created_at, run.updated_at),
      loc: String(run.proposed_files.length || run.tasks.length || "—"),
      time: run.created_at ? formatClock(run.created_at) : run.run_id.slice(0, 8),
    }));
  }
  return entryRows(localEntries);
}

function artifactExt(pathname: string) {
  const ext = pathname.split(".").pop();
  return ext && ext !== pathname ? ext.slice(0, 8) : "file";
}

function runArtifacts(run: EngineeringRun | null): Stage["artifacts"] {
  if (!run) return [];
  return run.proposed_files.slice(0, 8).map((file) => ({
    name: file.path,
    ext: artifactExt(file.path),
  }));
}

function stageStatusFromAgent(agent: AgentOfficeAgent): StageStatus {
  if (agent.status === "completed") return "complete";
  if (agent.status === "failed" || agent.status === "blocked") return "error";
  if (agent.status === "idle") return "pending";
  return "running";
}

function stageTypeFromAgent(agent: AgentOfficeAgent): Stage["type"] {
  const name = `${agent.name} ${agent.role}`.toLowerCase();
  if (name.includes("test") || name.includes("qa")) return "system";
  if (name.includes("release") || name.includes("final")) return "output";
  return "agent";
}

function stageTypeFromOwner(owner: string): Stage["type"] {
  const lower = owner.toLowerCase();
  if (lower.includes("qa") || lower.includes("test")) return "system";
  if (lower.includes("release") || lower.includes("meta")) return "output";
  if (lower.includes("product") || lower.includes("requirements")) return "input";
  return "agent";
}

function taskStatus(status: string | undefined, agent?: AgentOfficeAgent): StageStatus {
  const normalized = String(status ?? "").toLowerCase();
  if (["complete", "completed", "passed"].includes(normalized)) return "complete";
  if (["failed", "error"].includes(normalized)) return "error";
  if (normalized === "blocked") return "blocked";
  if (normalized === "skipped") return "skipped";
  if (["running"].includes(normalized)) return "running";
  if (agent) return stageStatusFromAgent(agent);
  return "pending";
}

function effectiveTaskStatus(
  task: EngineeringRun["tasks"][number],
  run: EngineeringRun,
  rawStatuses: Map<string, string>,
) {
  const normalized = String(task.status ?? "pending").toLowerCase();
  if (normalized !== "pending") return normalized;
  if (run.status === "completed") return "complete";
  const blockedByDependency = (task.dependencies ?? []).some(dependency =>
    ["failed", "error", "blocked"].includes(String(rawStatuses.get(dependency) ?? "").toLowerCase())
  );
  if (blockedByDependency || ["failed", "blocked"].includes(run.status.toLowerCase())) return "blocked";
  return normalized;
}

function agentForTaskOwner(agents: AgentOfficeAgent[], owner: string) {
  const normalizedOwner = owner.toLowerCase().replace(/\s+agent$/, "");
  return agents.find(agent => {
    const name = agent.name.toLowerCase();
    const role = agent.role.toLowerCase();
    return normalizedOwner.includes(name) || name.includes(normalizedOwner.replace(/\s+engineer$/, "")) || normalizedOwner.includes(role);
  });
}

function pipelineStages(agentOffice: AgentOfficeState | null, run: EngineeringRun | null): Stage[] {
  const agents = agentOffice?.agents ?? [];
  if (run?.tasks?.length) {
    const rawStatuses = new Map(run.tasks.map(task => [task.task_id ?? task.title, String(task.status ?? "pending")]));
    return run.tasks.map((task, index): Stage => {
      const agent = agentForTaskOwner(agents, task.owner);
      const effectiveStatus = effectiveTaskStatus(task, run, rawStatuses);
      const status = taskStatus(effectiveStatus);
      const blockedDependencies = (task.dependencies ?? []).filter(dependency =>
        ["failed", "error", "blocked"].includes(String(rawStatuses.get(dependency) ?? "").toLowerCase())
      );
      return {
        id: task.task_id ?? `${task.owner}-${index}`,
        num: index + 1,
        name: task.title,
        type: stageTypeFromOwner(task.owner),
        status,
        model: task.owner,
        duration: agent ? formatClock(agent.lastActivityAt) : "—",
        confidence: agent?.confidence,
        artifacts: task.task_id === "frontend_generation" || task.task_id === "release_package" ? runArtifacts(run) : [],
        note: status === "blocked" && blockedDependencies.length > 0
          ? `${task.description} Blocked by: ${blockedDependencies.join(", ")}`
          : task.dependencies?.length
          ? `${task.description} Depends on: ${task.dependencies.join(", ")}`
          : task.description,
        isConditional: agent?.approvalRequired || task.task_id === "frontend_generation",
      };
    });
  }
  if (agents.length === 0 && !run) return [];

  const inputStage: Stage = {
    id: "task",
    num: 0,
    name: "Task Input",
    type: "input",
    status: run ? "complete" : "pending",
    duration: "—",
    note: run?.idea,
  };

  const agentStages = agents
    .slice()
    .sort((a, b) => a.position.y - b.position.y || a.position.x - b.position.x)
    .map((agent, index): Stage => ({
      id: agent.id,
      num: index + 1,
      name: agent.name,
      type: stageTypeFromAgent(agent),
      status: stageStatusFromAgent(agent),
      model: agent.role,
      duration: formatClock(agent.lastActivityAt),
      confidence: agent.confidence,
      artifacts: index === 0 ? runArtifacts(run) : [],
      note: agent.blockedReason ?? agent.currentTask,
      isConditional: agent.approvalRequired,
    }));

  const outputStatus: StageStatus =
    run?.status === "completed" ? "complete" :
    run?.status === "failed" || run?.status === "blocked" ? "error" :
    run ? "pending" : "pending";

  return [
    inputStage,
    ...agentStages,
    {
      id: "output",
      num: agentStages.length + 1,
      name: "Approved Output",
      type: "output",
      status: outputStatus,
      duration: "—",
      artifacts: runArtifacts(run),
    },
  ];
}

function pipelineProgress(stages: Stage[]) {
  if (stages.length === 0) return 0;
  return Math.round((stages.filter(stage => stage.status === "complete").length / stages.length) * 100);
}

function activityRows(events: AgentOfficeEvent[]): ActivityRow[] {
  return events.slice(-7).reverse().map(event => ({
    t: formatClock(event.createdAt),
    agent: event.agentName,
    action: event.message,
    color: eventColor(event.type),
  }));
}

function logRows(remoteLogs: Array<Record<string, unknown>> | null, uiState: UiState | null): UiLogEntry[] {
  const mapped = remoteLogs?.slice(-80).reverse().map((item, index) => ({
    level: String(item.level ?? item.status ?? "INFO").toUpperCase(),
    time: formatClock(String(item.created_at ?? item.timestamp ?? item.time ?? "")),
    agent: String(item.agent ?? item.actor ?? item.component ?? "ANN"),
    msg: String(item.message ?? item.event ?? item.action ?? `Audit entry ${index + 1}`),
  })) ?? [];
  if (mapped.length > 0) return mapped;
  if (uiState?.logs?.length) return uiState.logs;
  return [];
}

function liveOutputRows(stage: Stage, events: AgentOfficeEvent[], logs: UiLogEntry[]) {
  const eventRows = events
    .filter(event => event.agentId === stage.id || event.agentName === stage.name)
    .slice(0, 4)
    .map(event => ({ c: eventColor(event.type), t: event.message }));
  if (eventRows.length > 0) return eventRows;
  return logs.slice(0, 4).map(log => ({
    c: log.level === "ERROR" ? "#ff3757" : log.level === "WARN" ? "#f5a623" : "#00c896",
    t: `${log.agent}: ${log.msg}`,
  }));
}

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function noticeColor(tone: AppNotice["tone"]) {
  if (tone === "success") return "#00c896";
  if (tone === "warning") return "#f5a623";
  if (tone === "error") return "#ff3757";
  return "#00d0ff";
}

function approvalStatusColor(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "approved") return "#00c896";
  if (normalized === "rejected" || normalized === "failed") return "#ff3757";
  if (normalized === "pending") return "#f5a623";
  return "#00d0ff";
}

function approvalPayloadLine(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  if (value == null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function CircularGauge({ value, label, color, size = 60 }: { value: number; label: string; color: string; size?: number }) {
  const r = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (value / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={4.5} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4.5}
            strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
            style={{ transition: "stroke-dasharray 0.7s ease-out", filter: `drop-shadow(0 0 4px ${color}88)` }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color, fontWeight: 600 }}>{value}%</span>
        </div>
      </div>
      <span className="text-[9px] tracking-widest uppercase" style={{ color: "rgba(212,223,247,0.35)" }}>{label}</span>
    </div>
  );
}

function BarGauge({ used, total, label, color }: { used: number; total: number; label: string; color: string }) {
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-[10px] uppercase tracking-widest" style={{ color: "rgba(212,223,247,0.35)" }}>{label}</span>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color }}>{used}GB/{total}GB</span>
      </div>
      <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}88, ${color})`, boxShadow: `0 0 6px ${color}66` }} />
      </div>
    </div>
  );
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const W = 200, H = 36;
  if (data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data), range = (max - min) || 1;
  const pts = data.map((v, i) => ({ x: (i / (data.length - 1)) * W, y: H - ((v - min) / range) * (H - 4) - 2 }));
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L ${W} ${H} L 0 ${H} Z`;
  const id = `sg-${color.replace("#", "")}`;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={1.5}
        style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
    </svg>
  );
}

function ExtBadge({ ext }: { ext: string }) {
  const c: Record<string, string> = { py: "#4ec9b0", md: "#89b4fa", yaml: "#cba6f7", sql: "#fab387", ts: "#4ec9b0", js: "#f9e2af" };
  return (
    <span className="px-1.5 py-0.5 rounded text-[8px] font-mono font-semibold uppercase"
      style={{ color: c[ext] || "#89b4fa", background: `${c[ext] || "#89b4fa"}15`, border: `1px solid ${c[ext] || "#89b4fa"}30` }}>
      {ext}
    </span>
  );
}

function StageIcon({ type, model }: { type: Stage["type"]; model?: string }) {
  if (type === "input") return <Hash size={13} />;
  if (type === "output") return <Package size={13} />;
  if (type === "system") return <FlaskConical size={13} />;
  if (model?.includes("Coder")) return <Code2 size={13} />;
  if (model?.includes("DeepSeek")) return <Shield size={13} />;
  return <Brain size={13} />;
}

function PipelineStageCard({ stage, selected, onClick }: { stage: Stage; selected: boolean; onClick: () => void }) {
  const cfg = S[stage.status];
  const running = stage.status === "running";
  return (
    <button onClick={onClick} className="w-full text-left rounded-lg border transition-all duration-200 p-3 group"
      style={{
        background: selected ? cfg.bg : "rgba(12,18,33,0.7)",
        borderColor: running ? cfg.border : selected ? cfg.border : "rgba(0,208,255,0.1)",
        animation: running ? "glow-pulse 2.5s ease-in-out infinite" : "none",
      }}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 flex flex-col items-center gap-1.5 pt-0.5">
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-mono font-bold flex-shrink-0"
            style={{ border: `1.5px solid ${cfg.border}`, color: cfg.color, background: cfg.bg, fontFamily: "JetBrains Mono, monospace" }}>
            {stage.num}
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-2">
              <span style={{ color: cfg.color, opacity: 0.7 }}><StageIcon type={stage.type} model={stage.model} /></span>
              <span className="text-sm font-semibold text-foreground">{stage.name}</span>
              {stage.isLoop && (
                <span className="text-[9px] px-1.5 py-0.5 rounded border"
                  style={{ color: "#f5a623", borderColor: "#f5a62330", background: "#f5a62310" }}>
                  LOOP
                </span>
              )}
              {stage.isConditional && (
                <span className="text-[9px] px-1.5 py-0.5 rounded border"
                  style={{ color: "#7c3aed", borderColor: "#7c3aed30", background: "#7c3aed10" }}>
                  COND
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {stage.model && (
                <span className="text-[10px] px-2 py-0.5 rounded border"
                  style={{ fontFamily: "JetBrains Mono, monospace", color: "#7c9fcf", borderColor: "rgba(124,159,207,0.2)", background: "rgba(124,159,207,0.06)" }}>
                  {stage.model}
                </span>
              )}
              <div className="flex items-center gap-1" style={{ color: cfg.color }}>
                <cfg.Icon size={11} className={running ? "animate-spin" : ""} />
                <span className="text-[10px] font-medium">{cfg.label}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 mb-1.5" style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(212,223,247,0.35)" }}>
            <span className="flex items-center gap-1"><Clock size={9} />{stage.duration}</span>
            {stage.confidence != null && (
              <span style={{ color: cfg.color }}>conf {formatConfidence(stage.confidence)}</span>
            )}
            {stage.tokens != null && (
              <span>{(stage.tokens / 1000).toFixed(1)}k tok</span>
            )}
          </div>
          {stage.artifacts && stage.artifacts.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {stage.artifacts.map(a => (
                <div key={a.name} className="flex items-center gap-1 px-1.5 py-0.5 rounded border"
                  style={{ borderColor: "rgba(0,208,255,0.1)", background: "rgba(0,208,255,0.04)" }}>
                  <ExtBadge ext={a.ext} />
                  <span className="text-[9px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.45)" }}>{a.name}</span>
                </div>
              ))}
            </div>
          )}
          {stage.note && (
            <p className="mt-1.5 text-[9px]" style={{ color: "rgba(212,223,247,0.3)" }}>{stage.note}</p>
          )}
        </div>
      </div>
    </button>
  );
}

function StageConnector({ active }: { active: boolean }) {
  return (
    <div className="flex justify-center items-center py-0.5" style={{ height: 28 }}>
      <div className="relative flex flex-col items-center">
        <div className="w-px overflow-hidden relative" style={{ height: 20, background: active ? "rgba(0,208,255,0.25)" : "rgba(68,85,119,0.2)" }}>
          {active && (
            <div className="absolute w-full h-4"
              style={{ background: "linear-gradient(to bottom, transparent, #00d0ff, transparent)", animation: "flow-down 1.4s linear infinite" }} />
          )}
        </div>
        <ArrowDown size={8} style={{ color: active ? "#00d0ff" : "#334466", marginTop: -1 }} />
      </div>
    </div>
  );
}

function LeftNav({ active, onNav }: { active: PageId; onNav: (p: PageId) => void }) {
  return (
    <aside className="w-14 flex-shrink-0 flex flex-col border-r"
      style={{ background: "#080e1e", borderColor: "rgba(0,208,255,0.08)" }}>
      <div className="h-12 flex items-center justify-center border-b flex-shrink-0"
        style={{ borderColor: "rgba(0,208,255,0.08)" }}>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold"
          style={{ background: "linear-gradient(135deg, #00d0ff22, #7c3aed22)", border: "1px solid rgba(0,208,255,0.3)", color: "#00d0ff", fontFamily: "JetBrains Mono, monospace", boxShadow: "0 0 12px rgba(0,208,255,0.2)" }}>
          A
        </div>
      </div>
      <nav className="flex-1 flex flex-col items-center py-2 gap-1 overflow-hidden">
        {NAV_ITEMS.map(item => {
          const isActive = active === item.id;
          return (
            <button key={item.id} onClick={() => onNav(item.id as PageId)}
              title={item.label}
              className="relative w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-150 group"
              style={{
                background: isActive ? "rgba(0,208,255,0.1)" : "transparent",
                color: isActive ? "#00d0ff" : "rgba(212,223,247,0.3)",
              }}>
              {isActive && (
                <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full"
                  style={{ background: "#00d0ff", boxShadow: "0 0 8px #00d0ff" }} />
              )}
              <item.icon size={16} />
              <div className="absolute left-12 z-50 px-2 py-1 rounded text-xs font-medium pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 whitespace-nowrap"
                style={{ background: "#0c1221", border: "1px solid rgba(0,208,255,0.2)", color: "#d4dff7" }}>
                {item.label}
              </div>
            </button>
          );
        })}
      </nav>
      <div className="flex flex-col items-center pb-3 gap-2 flex-shrink-0">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-[9px] font-bold"
          style={{ background: "linear-gradient(135deg, #00d0ff33, #7c3aed33)", border: "1px solid rgba(0,208,255,0.25)", color: "#00d0ff" }}>
          JD
        </div>
      </div>
    </aside>
  );
}

function TopBar({ page, pipelineRunning, onTogglePipeline, terminalOpen, onToggleTerminal, onNav, onNotice }: {
  page: PageId; pipelineRunning: boolean; onTogglePipeline: () => void;
  terminalOpen: boolean; onToggleTerminal: () => void;
  onNav: (p: PageId) => void;
  onNotice: (notice: AppNotice) => void;
}) {
  const [command, setCommand] = useState("");
  const commandRef = useRef<HTMLInputElement | null>(null);
  const labels: Record<PageId, string> = {
    dashboard: "Dashboard", projects: "Projects", pipeline: "Engineering Pipeline",
    models: "Model Manager", knowledge: "Knowledge Base", runtime: "Runtime Monitor",
    artifacts: "Artifacts", approvals: "Approval Center", logs: "System Logs", settings: "Settings",
  };
  const runCommand = (raw: string) => {
    const value = raw.trim().toLowerCase();
    if (!value) return;
    const matched = NAV_ITEMS.find(item =>
      item.id.includes(value) || item.label.toLowerCase().includes(value)
    );
    if (matched) {
      onNav(matched.id as PageId);
      onNotice({ title: "Command executed", message: `Opened ${matched.label}.`, tone: "success" });
      setCommand("");
      return;
    }
    if (["terminal", "console", "cmd"].some(term => value.includes(term))) {
      onToggleTerminal();
      onNotice({ title: "Terminal toggled", message: "Safe ANN terminal panel changed visibility.", tone: "info" });
      setCommand("");
      return;
    }
    if (["run", "stop", "pipeline"].some(term => value.includes(term))) {
      onTogglePipeline();
      onNotice({ title: "Pipeline controls", message: "Opened the live run overview for backend-managed pipeline state.", tone: "info" });
      setCommand("");
      return;
    }
    onNotice({ title: "Unknown command", message: `No ANN command matched "${raw}". Try dashboard, projects, approvals, models, logs, runtime, or terminal.`, tone: "warning" });
  };

  useEffect(() => {
    const focusCommand = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        commandRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusCommand);
    return () => window.removeEventListener("keydown", focusCommand);
  }, []);

  return (
    <header className="h-12 flex-shrink-0 flex items-center gap-3 px-4 border-b"
      style={{ background: "rgba(8,14,30,0.8)", borderColor: "rgba(0,208,255,0.08)", backdropFilter: "blur(12px)" }}>
      <div className="flex items-center gap-1.5 text-xs" style={{ color: "rgba(212,223,247,0.35)" }}>
        <span>ANN</span>
        <ChevronRight size={11} />
        <span style={{ color: "#d4dff7" }}>{labels[page]}</span>
      </div>
      <div className="flex-1" />
      {page === "pipeline" && (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded border text-[11px] font-medium"
            style={{
              borderColor: pipelineRunning ? "rgba(0,208,255,0.3)" : "rgba(68,85,119,0.3)",
              background: pipelineRunning ? "rgba(0,208,255,0.08)" : "rgba(68,85,119,0.08)",
              color: pipelineRunning ? "#00d0ff" : "#445577",
            }}>
            {pipelineRunning ? <Loader2 size={10} className="animate-spin" /> : <Circle size={10} />}
            {pipelineRunning ? "Pipeline Running" : "Pipeline Idle"}
          </div>
          <button onClick={onTogglePipeline}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-semibold transition-all duration-150"
            style={{
              background: "rgba(0,208,255,0.15)",
              color: "#00d0ff",
              border: "1px solid rgba(0,208,255,0.3)",
            }}>
            {pipelineRunning ? <><Eye size={10} /> View</> : <><Plus size={10} /> New Run</>}
          </button>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          runCommand(command);
        }}
        className="flex items-center gap-1 px-2.5 py-1.5 rounded border text-xs"
        style={{ borderColor: "rgba(0,208,255,0.12)", background: "rgba(0,208,255,0.04)", color: "rgba(212,223,247,0.4)", width: 200 }}>
        <Search size={11} />
        <input
          ref={commandRef}
          aria-label="Search ANN commands"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              runCommand(command);
            }
          }}
          placeholder="Search commands..."
          className="min-w-0 flex-1 bg-transparent outline-none text-xs"
          style={{ color: "#d4dff7" }}
        />
        <button type="submit" aria-label="Execute ANN command" className="ml-auto flex items-center gap-0.5">
          <kbd className="text-[9px] px-1 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.06)", color: "rgba(212,223,247,0.3)" }}>↵</kbd>
        </button>
      </form>
      <button
        aria-label="Open system notifications"
        onClick={() => {
          onNav("logs");
          onNotice({ title: "Notifications", message: "Opened System Logs for recent ANN activity.", tone: "info" });
        }}
        className="relative w-8 h-8 flex items-center justify-center rounded transition-colors"
        style={{ color: "rgba(212,223,247,0.4)" }}>
        <Bell size={15} />
        <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full" style={{ background: "#00d0ff", boxShadow: "0 0 6px #00d0ff" }} />
      </button>
      <button aria-label={terminalOpen ? "Hide ANN terminal" : "Show ANN terminal"} onClick={onToggleTerminal}
        className="w-8 h-8 flex items-center justify-center rounded transition-all duration-150"
        style={{ color: terminalOpen ? "#00d0ff" : "rgba(212,223,247,0.4)", background: terminalOpen ? "rgba(0,208,255,0.1)" : "transparent" }}>
        <Terminal size={15} />
      </button>
    </header>
  );
}

function RuntimePanel({ data, tokenHistory }: { data: RuntimeData; tokenHistory: number[] }) {
  const liveColor = data.status === "live" ? "#00c896" : data.status === "partial" ? "#f5a623" : "#ff3757";
  const liveLabel = data.status === "live" ? "Live" : data.status === "partial" ? "Partial" : "Offline";
  const loadedModels = data.loadedModels.length > 0 ? data.loadedModels : [];
  return (
    <aside className="w-64 flex-shrink-0 flex flex-col overflow-y-auto border-l"
      style={{ background: "rgba(8,14,30,0.6)", borderColor: "rgba(0,208,255,0.08)", backdropFilter: "blur(8px)" }}>
      <div className="px-3 py-2.5 border-b flex-shrink-0 flex items-center justify-between"
        style={{ borderColor: "rgba(0,208,255,0.08)" }}>
        <span className="text-[10px] font-semibold tracking-widest uppercase" style={{ color: "rgba(0,208,255,0.7)" }}>Runtime Monitor</span>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: liveColor, boxShadow: `0 0 6px ${liveColor}` }} />
          <span className="text-[9px]" style={{ color: liveColor }}>{liveLabel}</span>
        </div>
      </div>

      <div className="px-3 py-3 border-b space-y-1.5" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="text-[9px] uppercase tracking-widest mb-2" style={{ color: "rgba(212,223,247,0.25)" }}>Active Model</div>
        <div className="flex items-center gap-2 p-2 rounded-lg" style={{ background: "rgba(0,208,255,0.06)", border: "1px solid rgba(0,208,255,0.12)" }}>
          <Brain size={13} style={{ color: "#00d0ff" }} />
          <div className="min-w-0">
            <p className="text-[11px] font-semibold truncate" style={{ color: "#d4dff7", fontFamily: "JetBrains Mono, monospace" }}>{data.activeModel}</p>
            <p className="text-[9px]" style={{ color: "rgba(212,223,247,0.35)" }}>{data.activeStage}</p>
          </div>
        </div>
      </div>

      <div className="px-3 py-3 border-b" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="text-[9px] uppercase tracking-widest mb-3" style={{ color: "rgba(212,223,247,0.25)" }}>Compute</div>
        <div className="flex justify-around">
          <CircularGauge value={Math.round(data.gpu)} label="GPU" color="#00d0ff" size={56} />
          <CircularGauge value={Math.round(data.cpu)} label="CPU" color="#7c3aed" size={56} />
        </div>
      </div>

      <div className="px-3 py-3 border-b space-y-3" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="text-[9px] uppercase tracking-widest" style={{ color: "rgba(212,223,247,0.25)" }}>Memory</div>
        <BarGauge used={data.vramUsed} total={data.vramTotal} label="VRAM" color="#00d0ff" />
        <BarGauge used={data.ramUsed} total={data.ramTotal} label="RAM" color="#7c3aed" />
      </div>

      <div className="px-3 py-3 border-b" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] uppercase tracking-widest" style={{ color: "rgba(212,223,247,0.25)" }}>Token Rate</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#00c896", fontWeight: 600 }}>
            {data.tokensPerSec.toLocaleString()}<span style={{ color: "rgba(212,223,247,0.3)", fontWeight: 400 }}>/s</span>
          </span>
        </div>
        <Sparkline data={tokenHistory} color="#00c896" />
      </div>

      <div className="px-3 py-3 space-y-2" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="text-[9px] uppercase tracking-widest mb-2" style={{ color: "rgba(212,223,247,0.25)" }}>System</div>
        {[
          { label: "GPU Model", value: data.gpuModel, icon: Server },
          { label: "Uptime",    value: data.uptime,  icon: Clock },
          { label: "Pipeline",  value: data.pipelineId, icon: Hash },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="flex items-center justify-between">
            <div className="flex items-center gap-1.5" style={{ color: "rgba(212,223,247,0.3)" }}>
              <Icon size={10} />
              <span className="text-[10px]">{label}</span>
            </div>
            <span className="text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.55)" }}>{value}</span>
          </div>
        ))}
      </div>

      <div className="px-3 py-2 mt-auto border-t" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
        <div className="text-[9px] uppercase tracking-widest mb-2" style={{ color: "rgba(212,223,247,0.25)" }}>Loaded Models</div>
        {loadedModels.length === 0 && (
          <div className="py-1 text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.35)" }}>
            No active GPU model process
          </div>
        )}
        {loadedModels.map(m => (
          <div key={m.id} className="flex items-center gap-2 py-1">
            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: "#00c896", boxShadow: "0 0 5px #00c896" }} />
            <span className="text-[10px] flex-1 truncate" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.5)" }}>{m.name}</span>
            <span className="text-[9px]" style={{ color: "#00d0ff" }}>{m.usedVramGb.toFixed(1)}GB</span>
          </div>
        ))}
        {data.errors.length > 0 && (
          <div className="mt-2 rounded border px-2 py-1.5 text-[9px]" style={{ borderColor: "rgba(255,55,87,0.25)", color: "rgba(255,95,120,0.85)", background: "rgba(255,55,87,0.06)" }}>
            {data.errors[0]}
          </div>
        )}
      </div>
    </aside>
  );
}

function TerminalPanel({ onClose, onRunSelected }: { onClose: () => void; onRunSelected?: (runId: string) => void }) {
  const [input, setInput] = useState("");
  const [lines, setLines] = useState<TerminalLine[]>(TERMINAL_LINES);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"auto" | "chat" | "command">("auto");
  const [statusText, setStatusText] = useState("Idle");
  const [modelText, setModelText] = useState("none");
  const [backendText, setBackendText] = useState("local");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const liveKeysRef = useRef<Set<string>>(new Set());
  const lastRunSnapshotRef = useRef<{ status?: string; pending?: number; agents?: number; files?: number } | null>(null);

  const eventType = (kind: TerminalConversationEvent["kind"]): TerminalLine["type"] => {
    if (kind === "assistant") return "assistant";
    if (kind === "error") return "error";
    if (kind === "approval") return "approval";
    if (kind === "pipeline") return "pipeline";
    if (kind === "command") return "info";
    return "run";
  };

  const normalizeMode = (value: unknown): "auto" | "chat" | "command" | null => {
    if (typeof value !== "string") return null;
    const lower = value.toLowerCase();
    if (lower === "auto" || lower === "chat" || lower === "command") return lower;
    return null;
  };

  const appendLiveLine = (key: string, line: TerminalLine) => {
    if (liveKeysRef.current.has(key)) return;
    liveKeysRef.current.add(key);
    setLines(prev => [...prev, line].slice(-240));
  };

  const isActiveRunStatus = (status: string) =>
    ["running", "waiting_for_approval", "pending", "queued"].includes(status.toLowerCase());

  const auditMetadata = (entry: Record<string, unknown>) => {
    const metadata = entry.metadata;
    return metadata && typeof metadata === "object" && !Array.isArray(metadata)
      ? metadata as Record<string, unknown>
      : {};
  };

  const auditMatchesRun = (entry: Record<string, unknown>, runId: string) => {
    const metadata = auditMetadata(entry);
    return metadata.run_id === runId
      || metadata.parent_run_id === runId
      || String(entry.message ?? "").includes(runId)
      || String(entry.event_type ?? "").includes(runId);
  };

  const summarizeRun = (run: EngineeringRun) => {
    const snapshot = {
      status: run.status,
      pending: run.pending_approvals,
      agents: run.agent_results.length,
      files: run.proposed_files.length,
    };
    const previous = lastRunSnapshotRef.current;
    if (!previous || previous.status !== snapshot.status || previous.pending !== snapshot.pending) {
      appendLiveLine(`run:${run.run_id}:status:${snapshot.status}:${snapshot.pending}`, {
        type: run.status === "failed" || run.status === "blocked" ? "error" : run.pending_approvals > 0 ? "approval" : "pipeline",
        text: `Run ${run.run_id.slice(0, 8)} status=${run.status} pending_approvals=${run.pending_approvals}`,
      });
      setStatusText(run.status);
    }
    if (!previous || previous.agents !== snapshot.agents) {
      appendLiveLine(`run:${run.run_id}:agents:${snapshot.agents}`, {
        type: "pipeline",
        text: `Agent outputs: ${snapshot.agents}/${run.tasks.length || "?"}`,
      });
    }
    if (!previous || previous.files !== snapshot.files) {
      appendLiveLine(`run:${run.run_id}:files:${snapshot.files}`, {
        type: "pipeline",
        text: `Proposed files/diffs: ${snapshot.files}`,
      });
    }
    for (const result of run.agent_results.slice(-8)) {
      const agent = String(result.agent ?? "Agent");
      const outputs = Array.isArray(result.outputs) ? result.outputs.map(String).join(", ") : "outputs ready";
      appendLiveLine(`run:${run.run_id}:agent:${agent}`, {
        type: "run",
        text: `${agent}: ${outputs}`,
      });
    }
    lastRunSnapshotRef.current = snapshot;
  };

  const runCommand = async (command: string) => {
    const trimmed = command.trim();
    if (!trimmed) return;
    setLines(prev => [...prev, { type: "cmd", text: trimmed }]);
    if (trimmed.toLowerCase() === "clear") {
      setLines([]);
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/conversation/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: "ann-terminal",
          message: trimmed,
          mode,
          client: "enterprise-figma-terminal",
        }),
      });
      const payload = await response.json() as TerminalConversationResponse;
      const nextMode = normalizeMode(payload.mode ?? payload.terminal_status?.mode);
      if (nextMode) setMode(nextMode);
      if (payload.terminal_status?.status) setStatusText(payload.terminal_status.status);
      else if (payload.status) setStatusText(payload.status);
      if (payload.terminal_status?.model) setModelText(payload.terminal_status.model);
      else if (payload.model?.displayName) setModelText(payload.model.displayName);
      if (payload.terminal_status?.backend) setBackendText(payload.terminal_status.backend);
      else if (payload.model?.backendKind) setBackendText(payload.model.backendKind);
      const startedRunId = payload.capabilities?.start_pipeline?.run_id;
      if (startedRunId) {
        setActiveRunId(startedRunId);
        onRunSelected?.(startedRunId);
        lastRunSnapshotRef.current = null;
        appendLiveLine(`watch:${startedRunId}`, {
          type: "pipeline",
          text: `Watching live run ${startedRunId} from ANN terminal.`,
        });
      }

      const responseLines: TerminalLine[] = (payload.events ?? []).map(event => ({
        type: eventType(event.kind),
        text: event.text,
      }));
      if (responseLines.length === 0 && payload.display_message) {
        responseLines.push({
          type: payload.status === "blocked" ? "error" : "assistant",
          text: payload.display_message,
        });
      }
      setLines(prev => [...prev, ...responseLines]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Terminal command failed";
      setLines(prev => [...prev, { type: "error", text: message }]);
    } finally {
      setBusy(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && input.trim()) {
      void runCommand(input.trim());
      setInput("");
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [lines]);

  useEffect(() => {
    let cancelled = false;
    const attachLatestRun = async () => {
      try {
        const runs = await api.runs(8);
        if (cancelled || activeRunId) return;
        const latest = runs.find(run => isActiveRunStatus(run.status)) ?? runs[0];
        if (!latest) return;
        setActiveRunId(latest.run_id);
        onRunSelected?.(latest.run_id);
        appendLiveLine(`watch:${latest.run_id}`, {
          type: "pipeline",
          text: `Watching latest run ${latest.run_id} status=${latest.status}.`,
        });
      } catch {
        appendLiveLine("watch:no-api", {
          type: "error",
          text: "Live run watcher could not reach the backend API yet.",
        });
      }
    };
    void attachLatestRun();
    return () => {
      cancelled = true;
    };
  }, [activeRunId]);

  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;

    const pollRun = async () => {
      try {
        const [runResult, logsResult] = await Promise.allSettled([
          api.getRun(activeRunId),
          api.auditLogs(60),
        ]);
        if (cancelled) return;
        if (runResult.status === "fulfilled") {
          summarizeRun(runResult.value);
          if (!isActiveRunStatus(runResult.value.status)) {
            appendLiveLine(`run:${activeRunId}:terminal:${runResult.value.status}`, {
              type: runResult.value.status === "completed" ? "ok" : "error",
              text: `Run ${activeRunId.slice(0, 8)} finished with status=${runResult.value.status}`,
            });
          }
        }
        if (logsResult.status === "fulfilled") {
          for (const entry of logsResult.value.filter(item => auditMatchesRun(item, activeRunId)).slice(-16)) {
            const eventId = String(entry.event_id ?? `${entry.created_at}-${entry.event_type}-${entry.message}`);
            const actor = String(entry.actor ?? "ANN");
            const eventType = String(entry.event_type ?? "event");
            const message = String(entry.message ?? "");
            appendLiveLine(`audit:${activeRunId}:${eventId}`, {
              type: eventType.includes("failed") || eventType.includes("blocked") ? "error" : eventType.includes("approval") ? "approval" : "run",
              text: `${actor}: ${eventType} — ${message}`,
            });
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Live watcher failed";
        appendLiveLine(`watch:${activeRunId}:error:${message}`, { type: "error", text: message });
      }
    };

    void pollRun();
    const interval = window.setInterval(pollRun, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeRunId]);

  const lineColor: Record<string, string> = {
    system: "rgba(0,208,255,0.45)", cmd: "#d4dff7", info: "rgba(212,223,247,0.45)",
    ok: "#00c896", run: "#f5a623", blank: "transparent", error: "#ff3757",
    assistant: "#d4dff7", approval: "#f5a623", pipeline: "#00d0ff",
  };

  return (
    <div className="flex-shrink-0 border-t flex flex-col" style={{ height: 200, background: "#050810", borderColor: "rgba(0,208,255,0.1)" }}>
      <div className="flex items-center gap-2 px-3 py-1.5 border-b flex-shrink-0"
        style={{ borderColor: "rgba(0,208,255,0.08)", background: "rgba(0,208,255,0.03)" }}>
        <div className="flex gap-1">
          {["#ff5f57", "#febc2e", "#28c840"].map(c => (
            <div key={c} className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />
          ))}
        </div>
        <span className="text-[10px] font-semibold tracking-widest uppercase ml-2" style={{ color: "rgba(0,208,255,0.5)" }}>ANN Terminal</span>
        <div className="ml-auto flex items-center gap-2" style={{ color: "rgba(212,223,247,0.3)", fontSize: 10 }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace" }}>mode:{mode}</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace" }}>status:{statusText}</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace" }}>model:{modelText}</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace" }}>backend:{backendText}</span>
          {activeRunId && <span style={{ fontFamily: "JetBrains Mono, monospace", color: "#00d0ff" }}>run:{activeRunId.slice(0, 8)}</span>}
          <button aria-label="Close ANN terminal" onClick={onClose} className="p-1 rounded hover:bg-white/5 transition-colors"><XCircle size={12} /></button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5"
        style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
        {lines.map((l, i) => (
          <div key={i} className="flex items-start gap-2">
            {l.type === "cmd" && <span style={{ color: "#00c896", flexShrink: 0 }}>ann@os ›</span>}
            {l.type !== "blank" && (
              <span style={{ color: lineColor[l.type] || "#d4dff7" }}>{l.text}</span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="px-3 py-2 border-t flex items-center gap-2" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#00c896" }}>ann@os ›</span>
        <input aria-label="Write naturally or enter ANN command" value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
          disabled={busy}
          placeholder={busy ? "Processing ANN input..." : mode === "command" ? "Enter safe ANN command..." : "Write naturally or enter ANN command..."}
          className="flex-1 bg-transparent text-sm outline-none"
          style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#d4dff7", caretColor: "#00d0ff" }} />
        <span style={{ animation: "cursor-blink 1.1s step-end infinite", color: "#00d0ff", fontFamily: "JetBrains Mono", fontSize: 13, lineHeight: 1 }}>█</span>
      </div>
    </div>
  );
}

function StatusBar({ runtime, pipelineRunning }: { runtime: RuntimeData; pipelineRunning: boolean }) {
  const items = [
    { icon: Activity, text: `Pipeline: ${pipelineRunning ? "Running" : "Idle"}`, color: pipelineRunning ? "#00d0ff" : "rgba(212,223,247,0.4)" },
    { icon: Brain, text: runtime.activeModel, color: "rgba(212,223,247,0.4)" },
    { icon: Cpu, text: `GPU ${Math.round(runtime.gpu)}%`, color: "rgba(212,223,247,0.4)" },
    { icon: Zap, text: `${runtime.tokensPerSec.toLocaleString()} tok/s`, color: "#00c896" },
    { icon: Clock, text: runtime.uptime, color: "rgba(212,223,247,0.4)" },
  ];
  return (
    <footer className="h-7 flex-shrink-0 flex items-center px-3 border-t gap-4"
      style={{ background: "#050810", borderColor: "rgba(0,208,255,0.08)", fontFamily: "JetBrains Mono, monospace", fontSize: 10 }}>
      {items.map(({ icon: Icon, text, color }) => (
        <div key={text} className="flex items-center gap-1.5" style={{ color }}>
          <Icon size={10} />
          <span>{text}</span>
        </div>
      ))}
      <div className="ml-auto flex items-center gap-3" style={{ color: "rgba(212,223,247,0.3)" }}>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: runtime.status === "unavailable" ? "#ff3757" : "#00c896", boxShadow: `0 0 4px ${runtime.status === "unavailable" ? "#ff3757" : "#00c896"}` }} />
          <span>{runtime.status === "unavailable" ? "Telemetry unavailable" : "Runtime telemetry active"}</span>
        </div>
        <span>ANN OS v2.4.1</span>
      </div>
    </footer>
  );
}

function DashboardPage({
  runtime,
  uiState,
  runs: backendRuns,
  agentOffice,
  agentEvents,
  uiLoadState,
  onSelectRun,
}: {
  runtime: RuntimeData;
  uiState: UiState | null;
  runs: EngineeringRun[];
  agentOffice: AgentOfficeState | null;
  agentEvents: AgentOfficeEvent[];
  uiLoadState: UiLoadState;
  onSelectRun: (runId: string) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "complete" | "blocked" | "error">("all");
  const projectCount = uiState?.projects.length ?? 0;
  const activePipelines = backendRuns.filter(run => run.status === "running").length;
  const awaitingApproval = backendRuns.filter(run => run.status === "waiting_for_approval").length;
  const latest = latestRun(backendRuns);
  const latestTasks = latest?.tasks ?? [];
  const completedTasks = latestTasks.filter(task => ["complete", "completed", "passed"].includes(String(task.status))).length;
  const activeAgentStates = new Set(["thinking", "planning", "coding", "testing", "reviewing", "waiting approval"]);
  const activeAgents = agentOffice?.agents.filter(agent => activeAgentStates.has(agent.status)).length ?? 0;
  const agentCount = agentOffice?.agents.length ?? 0;
  const allRuns = runRows(backendRuns, uiState?.projects ?? []);
  const runs = statusFilter === "all" ? allRuns : allRuns.filter(run => run.status === statusFilter);
  const activity = agentEvents.length > 0 ? activityRows(agentEvents) : [];
  const kpis = [
    { label: "Active Pipelines", value: String(activePipelines), sub: uiLoadState === "loading" ? "loading run state" : `${awaitingApproval} awaiting approval · ${backendRuns.length} recent runs`, icon: Workflow, color: "#00d0ff" },
    { label: "Agents Online",    value: String(agentCount), sub: agentCount > 0 ? `${activeAgents} active · ${agentCount - activeAgents} idle` : "agent feed unavailable", icon: Brain, color: "#7c3aed" },
    { label: "Token Throughput", value: `${(runtime.tokensPerSec / 1000).toFixed(1)}k/s`, sub: runtime.status === "live" ? "live runtime" : runtime.status, icon: Zap, color: "#00c896" },
    { label: "Pipeline Tasks",   value: String(latestTasks.length), sub: latestTasks.length > 0 ? `${completedTasks} complete in latest run` : `${projectCount} local workspaces`, icon: CheckCircle2, color: "#f5a623" },
  ];
  const statusColors: Record<string, string> = { running: "#00d0ff", complete: "#00c896", blocked: "#f5a623", error: "#ff3757" };

  return (
    <div className="p-5 space-y-5">
      <div className="grid grid-cols-4 gap-3">
        {kpis.map(k => (
          <div key={k.label} className="rounded-xl border p-4 transition-all duration-200 hover:border-opacity-40"
            style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)", backdropFilter: "blur(8px)" }}>
            <div className="flex items-start justify-between mb-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: `${k.color}15`, border: `1px solid ${k.color}30` }}>
                <k.icon size={15} style={{ color: k.color }} />
              </div>
              <TrendingUp size={12} style={{ color: "rgba(212,223,247,0.2)", marginTop: 4 }} />
            </div>
            <div className="text-2xl font-bold mb-0.5" style={{ color: k.color, fontFamily: "JetBrains Mono, monospace" }}>{k.value}</div>
            <div className="text-[11px] font-medium mb-1" style={{ color: "rgba(212,223,247,0.6)" }}>{k.label}</div>
            <div className="text-[10px]" style={{ color: "rgba(212,223,247,0.3)" }}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-4">
        <div className="rounded-xl border overflow-hidden" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
          <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
            <span className="text-sm font-semibold" style={{ color: "#d4dff7" }}>Recent Pipeline Runs</span>
            <button
              onClick={() => {
                const order: Array<typeof statusFilter> = ["all", "running", "complete", "blocked", "error"];
                setStatusFilter(order[(order.indexOf(statusFilter) + 1) % order.length]);
              }}
              className="text-[10px] flex items-center gap-1"
              style={{ color: "rgba(0,208,255,0.6)" }}>
              <Filter size={10} /> {statusFilter === "all" ? "Filter" : statusFilter}
            </button>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
                {["Task", "Status", "Duration", "Artifacts", "Started"].map(h => (
                  <th key={h} className="px-4 py-2 text-left text-[10px] uppercase tracking-widest font-semibold"
                    style={{ color: "rgba(212,223,247,0.25)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-xs" style={{ color: "rgba(212,223,247,0.35)" }}>
                    {uiLoadState === "loading" ? "Loading runs..." : "No pipeline runs found yet."}
                  </td>
                </tr>
              )}
              {runs.map(r => (
                <tr key={r.id} className="border-b hover:bg-white/[0.02] transition-colors"
                  style={{ borderColor: "rgba(0,208,255,0.04)" }}>
                  <td className="px-4 py-2.5 text-sm font-medium" style={{ color: "#d4dff7" }}>
                    <button type="button" onClick={() => onSelectRun(r.id)} className="text-left hover:underline" style={{ color: "inherit" }}>
                      {r.task}
                    </button>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="flex items-center gap-1.5 text-[11px] font-medium w-fit px-2 py-0.5 rounded-full"
                      style={{ color: statusColors[r.status], background: `${statusColors[r.status]}15`, border: `1px solid ${statusColors[r.status]}30` }}>
                      {r.status === "running" && <Loader2 size={9} className="animate-spin" />}
                      {r.status === "complete" && <CheckCircle2 size={9} />}
                      {r.status === "blocked" && <Lock size={9} />}
                      {r.status === "error" && <AlertCircle size={9} />}
                      {r.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.45)" }}>{r.duration}</td>
                  <td className="px-4 py-2.5 text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.45)" }}>{r.loc}</td>
                  <td className="px-4 py-2.5 text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.3)" }}>{r.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl border overflow-hidden" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
          <div className="px-4 py-3 border-b" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
            <span className="text-sm font-semibold" style={{ color: "#d4dff7" }}>Agent Activity</span>
          </div>
          <div className="p-3 space-y-2 overflow-y-auto" style={{ maxHeight: 260 }}>
            {activity.length === 0 && (
              <div className="p-3 text-xs" style={{ color: "rgba(212,223,247,0.35)" }}>
                No agent activity available.
              </div>
            )}
            {activity.map((e, i) => (
              <div key={i} className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                <div className="w-1 h-1 rounded-full mt-1.5 flex-shrink-0"
                  style={{ background: e.color, boxShadow: `0 0 5px ${e.color}` }} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] font-semibold" style={{ color: e.color }}>{e.agent}</span>
                    <span className="text-[9px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.25)" }}>{e.t}</span>
                  </div>
                  <p className="text-[10px] leading-relaxed" style={{ color: "rgba(212,223,247,0.45)" }}>{e.action}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PipelinePage({
  stages,
  activeRun,
  logs,
  agentEvents,
  loadState,
  onNotice,
}: {
  stages: Stage[];
  activeRun: EngineeringRun | null;
  logs: UiLogEntry[];
  agentEvents: AgentOfficeEvent[];
  loadState: UiLoadState;
  onNotice: (notice: AppNotice) => void;
}) {
  const [selectedId, setSelectedId] = useState<string>("task");
  const selected = stages.find(s => s.id === selectedId) ?? stages[0];
  const progress = pipelineProgress(stages);
  const completed = stages.filter(stage => stage.status === "complete").length;

  useEffect(() => {
    if (stages.length > 0 && !stages.some(stage => stage.id === selectedId)) {
      setSelectedId(stages[0].id);
    }
  }, [selectedId, stages]);

  return (
    <div className="flex h-full overflow-hidden">
      <div className="w-[520px] flex-shrink-0 overflow-y-auto p-4 border-r" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
        <div className="rounded-xl border p-3 mb-4" style={{ background: "rgba(0,208,255,0.04)", border: "1px solid rgba(0,208,255,0.15)" }}>
          <div className="flex items-start gap-2 mb-2">
            <Hash size={12} style={{ color: "#00d0ff", marginTop: 2 }} />
            <div>
              <p className="text-xs font-semibold" style={{ color: "#00d0ff" }}>Current Task</p>
              <p className="text-[11px] mt-0.5" style={{ color: "rgba(212,223,247,0.55)" }}>{activeRun?.run_id ?? "No active run"}</p>
            </div>
          </div>
          <p className="text-sm" style={{ color: "#d4dff7" }}>
            {activeRun ? displayRunIdea(activeRun.idea) : (loadState === "loading" ? "Loading pipeline state..." : "Start a run from the workbench to populate the engineering pipeline.")}
          </p>
          <div className="flex items-center gap-3 mt-2.5">
            <span className="text-[10px]" style={{ color: "rgba(212,223,247,0.35)" }}>{completed} / {stages.length || 0} stages complete</span>
            <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
              <div className="h-full rounded-full transition-all duration-700"
                style={{ width: `${progress}%`, background: "linear-gradient(90deg, #00d0ff88, #00d0ff)", boxShadow: "0 0 8px #00d0ff66" }} />
            </div>
            <span className="text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "#00d0ff" }}>{progress}%</span>
          </div>
        </div>

        <div className="space-y-0">
          {stages.length === 0 && (
            <div className="rounded-xl border p-6 text-center text-sm" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)", color: "rgba(212,223,247,0.35)" }}>
              {loadState === "loading" ? "Loading pipeline stages..." : "No live pipeline stages available."}
            </div>
          )}
          {stages.map((stage, idx) => (
            <div key={stage.id}>
              <PipelineStageCard stage={stage} selected={selectedId === stage.id} onClick={() => setSelectedId(stage.id)} />
              {idx < stages.length - 1 && (
                <StageConnector active={stage.status === "complete"} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selected && (
          <>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: `${S[selected.status].bg}`, border: `1px solid ${S[selected.status].border}` }}>
                <span style={{ color: S[selected.status].color }}><StageIcon type={selected.type} model={selected.model} /></span>
              </div>
              <div>
                <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>{selected.name}</h2>
                {selected.model && (
                  <span className="text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.4)" }}>{selected.model}</span>
                )}
              </div>
              {(() => { const sc = S[selected.status]; const SIcon = sc.Icon; return (
              <div className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium"
                style={{ color: sc.color, background: sc.bg, border: `1px solid ${sc.border}` }}>
                <SIcon size={11} className={selected.status === "running" ? "animate-spin" : ""} />
                {sc.label}
              </div>
              ); })()}
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Last Activity", value: selected.duration, icon: Clock },
                { label: "Confidence", value: formatConfidence(selected.confidence), icon: Shield },
                { label: "Tokens",     value: selected.tokens ? `${(selected.tokens / 1000).toFixed(1)}k` : "—", icon: Zap },
              ].map(m => (
                <div key={m.label} className="rounded-lg border p-3"
                  style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
                  <div className="flex items-center gap-1.5 mb-1.5" style={{ color: "rgba(212,223,247,0.35)" }}>
                    <m.icon size={11} />
                    <span className="text-[10px] uppercase tracking-widest">{m.label}</span>
                  </div>
                  <div className="text-lg font-bold" style={{ fontFamily: "JetBrains Mono, monospace", color: S[selected.status].color }}>{m.value}</div>
                </div>
              ))}
            </div>

            {selected.artifacts && selected.artifacts.length > 0 && (
              <div className="rounded-xl border overflow-hidden" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
                <div className="px-4 py-2.5 border-b flex items-center justify-between"
                  style={{ borderColor: "rgba(0,208,255,0.08)", background: "rgba(0,208,255,0.03)" }}>
                  <span className="text-xs font-semibold" style={{ color: "#d4dff7" }}>Generated Artifacts</span>
                  <button
                    onClick={() => {
                      downloadJson("ann-selected-stage-artifacts.json", {
                        stage: selected.name,
                        artifacts: selected.artifacts,
                      });
                      onNotice({ title: "Artifacts exported", message: `${selected.artifacts?.length ?? 0} artifact references downloaded.`, tone: "success" });
                    }}
                    className="text-[10px] flex items-center gap-1"
                    style={{ color: "rgba(0,208,255,0.6)" }}>
                    <Download size={10} /> Export All
                  </button>
                </div>
                <div className="p-3 space-y-1.5">
                  {selected.artifacts.map(a => (
                    <button key={a.name} type="button"
                      onClick={() => {
                        downloadJson("ann-artifact-reference.json", {
                          run_id: activeRun?.run_id ?? null,
                          stage: selected.name,
                          artifact: a,
                        });
                        onNotice({ title: "Artifact reference exported", message: a.name, tone: "success" });
                      }}
                      aria-label={`Export artifact reference ${a.name}`}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-white/[0.03] transition-colors group text-left"
                      style={{ border: "1px solid rgba(0,208,255,0.08)" }}>
                      <ExtBadge ext={a.ext} />
                      <span className="text-xs flex-1" style={{ fontFamily: "JetBrains Mono, monospace", color: "rgba(212,223,247,0.65)" }}>{a.name}</span>
                      <Eye size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "#00d0ff" }} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {selected.status === "running" && (
              <div className="rounded-xl border p-4" style={{ background: "rgba(0,208,255,0.04)", borderColor: "rgba(0,208,255,0.15)" }}>
                <div className="flex items-center gap-2 mb-3">
                  <Loader2 size={13} className="animate-spin" style={{ color: "#00d0ff" }} />
                  <span className="text-xs font-semibold" style={{ color: "#00d0ff" }}>Live Output</span>
                </div>
                <div className="space-y-1" style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
                  {liveOutputRows(selected, agentEvents, logs).map((l, i) => (
                    <p key={i} style={{ color: l.c }}>{l.t}</p>
                  ))}
                </div>
              </div>
            )}

            {selected.note && (
              <div className="rounded-lg px-3 py-2.5 border" style={{ background: "rgba(124,58,237,0.06)", borderColor: "rgba(124,58,237,0.2)" }}>
                <p className="text-xs" style={{ color: "rgba(212,223,247,0.5)" }}>{selected.note}</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ModelsPage({
  runtime,
  uiState,
  onRefresh,
}: {
  runtime: RuntimeData;
  uiState: UiState | null;
  onRefresh: () => void;
}) {
  const statusStyle: Record<string, { color: string; label: string }> = {
    loaded:   { color: "#00c896", label: "Loaded" },
    idle:     { color: "#f5a623", label: "Idle" },
    unloaded: { color: "#445577", label: "Unloaded" },
  };
  const liveModels = runtime.loadedModels.map((model, index) => ({
    id: model.id,
    name: model.name,
    family: model.name.split("-")[0] || "ANN",
    params: "runtime",
    quant: model.status,
    vram: Number(model.usedVramGb.toFixed(1)),
    total: runtime.vramTotal || Math.max(model.usedVramGb, 1),
    status: "loaded",
    role: runtime.activeStage,
    tps: model.tps,
    color: index % 2 === 0 ? "#00d0ff" : "#7c3aed",
  }));
  const localModels = uiState?.models.slice(0, 6).map((model, index) => ({
    id: model.path,
    name: model.name,
    family: "Local",
    params: formatSize(model.size),
    quant: model.type,
    vram: 0,
    total: runtime.vramTotal || 1,
    status: "unloaded",
    role: model.path,
    tps: 0,
    color: index % 2 === 0 ? "#00c896" : "#f5a623",
  })) ?? [];
  const liveNames = liveModels.map(model => model.name.toLowerCase());
  const declaredOnly = localModels.filter(model => {
    const name = model.name.toLowerCase();
    return !liveNames.some(liveName => liveName === name || liveName.includes(name) || name.includes(liveName));
  });
  const models = [...liveModels, ...declaredOnly];
  const allocated = models.reduce((total, model) => total + model.vram, 0);
  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>Model Manager</h2>
          <p className="text-xs mt-0.5" style={{ color: "rgba(212,223,247,0.4)" }}>{allocated.toFixed(1)}GB / {runtime.vramTotal || 0}GB VRAM allocated · {liveModels.length} models active</p>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold"
          style={{ background: "rgba(0,208,255,0.1)", border: "1px solid rgba(0,208,255,0.25)", color: "#00d0ff" }}>
          <RefreshCw size={12} /> Refresh Inventory
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {models.length === 0 && (
          <div className="col-span-2 rounded-xl border p-6 text-center text-sm"
            style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)", color: "rgba(212,223,247,0.35)" }}>
            No local model files or active GPU model processes found.
          </div>
        )}
        {models.map(m => {
          const ss = statusStyle[m.status] ?? statusStyle.unloaded;
          return (
            <div key={m.id} className="rounded-xl border p-4 hover:border-opacity-30 transition-all duration-200 group"
              style={{ background: "rgba(12,18,33,0.8)", borderColor: m.status !== "unloaded" ? `${m.color}22` : "rgba(0,208,255,0.08)" }}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="text-sm font-bold" style={{ fontFamily: "JetBrains Mono, monospace", color: "#d4dff7" }}>{m.name}</p>
                    <span className="text-[9px] px-1.5 py-0.5 rounded border font-semibold"
                      style={{ color: ss.color, borderColor: `${ss.color}30`, background: `${ss.color}12` }}>
                      {ss.label}
                    </span>
                  </div>
                  <p className="text-[11px]" style={{ color: "rgba(212,223,247,0.4)" }}>{m.role}</p>
                </div>
                <span className="text-[9px] uppercase tracking-widest" style={{ color: "rgba(212,223,247,0.25)" }}>{m.family}</span>
              </div>
              <div className="flex items-center gap-3 mb-3">
                {[{ label: "Size", value: m.params }, { label: "Quant", value: m.quant }, { label: "Speed", value: `${m.tps}t/s` }].map(item => (
                  <div key={item.label} className="text-center">
                    <p className="text-[9px] uppercase tracking-widest mb-0.5" style={{ color: "rgba(212,223,247,0.3)" }}>{item.label}</p>
                    <p className="text-xs font-semibold" style={{ fontFamily: "JetBrains Mono, monospace", color: m.color }}>{item.value}</p>
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[9px]">
                  <span className="uppercase tracking-widest" style={{ color: "rgba(212,223,247,0.3)" }}>VRAM</span>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", color: m.color }}>{m.vram}GB / {m.total}GB</span>
                </div>
                <div className="h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                  <div className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${(m.vram / m.total) * 100}%`, background: m.status !== "unloaded" ? m.color : "#334466", boxShadow: m.status !== "unloaded" ? `0 0 6px ${m.color}66` : "none" }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PlaceholderPage({ title, icon: Icon, description, accent = "#00d0ff" }: {
  title: string; icon: React.ElementType; description: string; accent?: string;
}) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto"
          style={{ background: `${accent}10`, border: `1px solid ${accent}25` }}>
          <Icon size={28} style={{ color: accent }} />
        </div>
        <h2 className="text-lg font-bold" style={{ color: "#d4dff7" }}>{title}</h2>
        <p className="text-sm max-w-xs" style={{ color: "rgba(212,223,247,0.4)" }}>{description}</p>
      </div>
    </div>
  );
}

function WorkspaceListPage({ title, icon: Icon, description, entries, loadState, accent = "#00d0ff" }: {
  title: string;
  icon: React.ElementType;
  description: string;
  entries: UiEntry[];
  loadState: UiLoadState;
  accent?: string;
}) {
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [currentEntries, setCurrentEntries] = useState(entries);
  const [preview, setPreview] = useState<UiBrowseResponse | null>(null);
  const [browseState, setBrowseState] = useState<UiLoadState>(loadState);
  const [browseError, setBrowseError] = useState<string | null>(null);

  useEffect(() => {
    if (currentPath === null) {
      setCurrentEntries(entries);
      setBrowseState(loadState);
    }
  }, [currentPath, entries, loadState]);

  const browse = async (targetPath: string) => {
    setBrowseState("loading");
    setBrowseError(null);
    try {
      const payload = await localJson<UiBrowseResponse>(`/api/ui/browse?path=${encodeURIComponent(targetPath)}`);
      if (payload.kind === "directory") {
        setCurrentPath(payload.path);
        setCurrentEntries(payload.entries ?? []);
        setPreview(null);
      } else {
        setPreview(payload);
      }
      setBrowseState("ready");
    } catch (error) {
      setBrowseState("error");
      setBrowseError(error instanceof Error ? error.message : "Could not open the selected item.");
    }
  };

  const goUp = () => {
    if (!currentPath) return;
    const parent = currentPath.replace(/[\\/]+$/, "").split(/[\\/]/).slice(0, -1).join("\\");
    if (!parent) {
      setCurrentPath(null);
      setCurrentEntries(entries);
      setPreview(null);
      setBrowseState(loadState);
      return;
    }
    void browse(parent);
  };

  return (
    <div className="p-5 h-full flex flex-col">
      <div className="text-center space-y-3 mb-5">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto"
          style={{ background: `${accent}10`, border: `1px solid ${accent}25` }}>
          <Icon size={24} style={{ color: accent }} />
        </div>
        <div>
          <h2 className="text-lg font-bold" style={{ color: "#d4dff7" }}>{title}</h2>
          <p className="text-sm max-w-sm mx-auto mt-2" style={{ color: "rgba(212,223,247,0.4)" }}>{description}</p>
        </div>
      </div>
      <div className="rounded-xl border overflow-hidden flex-1" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
          <div className="flex items-center gap-2 min-w-0">
            {currentPath && (
              <button type="button" onClick={goUp} aria-label={`Go up from ${currentPath}`}
                className="w-7 h-7 rounded flex items-center justify-center"
                style={{ color: accent, border: `1px solid ${accent}30`, background: `${accent}0d` }}>
                <ChevronLeft size={13} />
              </button>
            )}
            <span className="text-sm font-semibold flex-shrink-0" style={{ color: "#d4dff7" }}>{currentEntries.length} items</span>
            {currentPath && <span className="text-[10px] truncate" style={{ color: "rgba(212,223,247,0.35)", fontFamily: "JetBrains Mono, monospace" }}>{currentPath}</span>}
          </div>
          <span className="text-[10px]" style={{ color: browseState === "error" ? "#ff3757" : "rgba(212,223,247,0.35)", fontFamily: "JetBrains Mono, monospace" }}>
            {browseState === "loading" ? "loading..." : browseState}
          </span>
        </div>
        <div className={preview ? "grid grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)] h-full" : "h-full"}>
        <div className="overflow-y-auto h-full">
          {browseError && <div className="p-4 text-xs" style={{ color: "#ff3757" }}>{browseError}</div>}
          {currentEntries.length === 0 && !browseError && (
            <div className="h-full flex items-center justify-center text-sm" style={{ color: "rgba(212,223,247,0.35)" }}>
              {browseState === "loading" ? "Loading local data..." : "No local items found."}
            </div>
          )}
          {currentEntries.map(entry => (
            <button key={entry.path} type="button" onClick={() => void browse(entry.path)}
              aria-label={`Open ${entry.type} ${entry.name}`}
              className="w-full flex items-center gap-3 px-4 py-3 border-b hover:bg-white/[0.02] transition-colors text-left"
              style={{ borderColor: "rgba(0,208,255,0.04)" }}>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: `${accent}12`, border: `1px solid ${accent}25` }}>
                {entry.type === "directory" ? <FolderOpen size={14} style={{ color: accent }} /> : <FileText size={14} style={{ color: accent }} />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold truncate" style={{ color: "#d4dff7" }}>{entry.name}</p>
                <p className="text-[10px] truncate" style={{ color: "rgba(212,223,247,0.35)", fontFamily: "JetBrains Mono, monospace" }}>{entry.path}</p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-[10px]" style={{ color: "rgba(212,223,247,0.45)", fontFamily: "JetBrains Mono, monospace" }}>{formatSize(entry.size)}</p>
                <p className="text-[9px]" style={{ color: "rgba(212,223,247,0.25)" }}>{formatClock(entry.modifiedAt)}</p>
              </div>
              <ChevronRight size={12} style={{ color: "rgba(212,223,247,0.2)" }} />
            </button>
          ))}
        </div>
        {preview && (
          <div className="border-l h-full flex flex-col overflow-hidden" style={{ borderColor: "rgba(0,208,255,0.08)", background: "#05080f" }}>
            <div className="px-3 py-2.5 border-b flex items-center gap-2" style={{ borderColor: "rgba(0,208,255,0.08)" }}>
              <FileText size={13} style={{ color: accent }} />
              <span className="text-xs font-semibold truncate flex-1" style={{ color: "#d4dff7" }}>{preview.name}</span>
              <a href={`/api/ui/browse?path=${encodeURIComponent(preview.path)}&download=1`}
                className="text-[10px] flex items-center gap-1" style={{ color: accent }}>
                <Download size={10} /> Download
              </a>
              <button type="button" onClick={() => setPreview(null)} aria-label="Close file preview" style={{ color: "rgba(212,223,247,0.35)" }}>×</button>
            </div>
            <div className="flex-1 overflow-auto p-3">
              {preview.previewable ? (
                <pre className="text-[10px] whitespace-pre-wrap break-words" style={{ color: "rgba(212,223,247,0.65)", fontFamily: "JetBrains Mono, monospace" }}>{preview.content}</pre>
              ) : (
                <div className="h-full flex items-center justify-center text-center text-xs px-6" style={{ color: "rgba(212,223,247,0.4)" }}>
                  Preview is unavailable for this file type or size. Use Download to open the original file.
                </div>
              )}
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}

function RuntimeDetailPage({ runtime, tokenHistory }: { runtime: RuntimeData; tokenHistory: number[] }) {
  return (
    <div className="p-5 space-y-4">
      <div>
        <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>Runtime Monitor</h2>
        <p className="text-xs mt-0.5" style={{ color: "rgba(212,223,247,0.4)" }}>Live local telemetry from Windows and ANN model runtime.</p>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "GPU", value: `${Math.round(runtime.gpu)}%`, icon: Cpu, color: "#00d0ff" },
          { label: "CPU", value: `${Math.round(runtime.cpu)}%`, icon: Activity, color: "#7c3aed" },
          { label: "VRAM", value: `${runtime.vramUsed} / ${runtime.vramTotal}GB`, icon: HardDrive, color: "#00c896" },
          { label: "Token Rate", value: `${runtime.tokensPerSec}/s`, icon: Zap, color: "#f5a623" },
        ].map(item => (
          <div key={item.label} className="rounded-xl border p-4" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
            <div className="flex items-center gap-2 mb-2" style={{ color: item.color }}>
              <item.icon size={14} />
              <span className="text-[10px] uppercase tracking-widest">{item.label}</span>
            </div>
            <div className="text-xl font-bold" style={{ color: item.color, fontFamily: "JetBrains Mono, monospace" }}>{item.value}</div>
          </div>
        ))}
      </div>
      <div className="rounded-xl border p-4" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold" style={{ color: "#d4dff7" }}>Runtime Details</span>
          <span className="text-[10px]" style={{ color: runtime.status === "live" ? "#00c896" : "#f5a623" }}>{runtime.status}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs" style={{ color: "rgba(212,223,247,0.55)" }}>
          <p>GPU Model: <span style={{ color: "#d4dff7" }}>{runtime.gpuModel}</span></p>
          <p>GPU Source: <span style={{ color: "#d4dff7" }}>{runtime.gpuSource}</span></p>
          <p>Active Model: <span style={{ color: "#d4dff7" }}>{runtime.activeModel}</span></p>
          <p>Stage: <span style={{ color: "#d4dff7" }}>{runtime.activeStage}</span></p>
          <p>Pipeline: <span style={{ color: "#d4dff7" }}>{runtime.pipelineId}</span></p>
          <p>Uptime: <span style={{ color: "#d4dff7" }}>{runtime.uptime}</span></p>
        </div>
        <div className="mt-4">
          <Sparkline data={tokenHistory} color="#00c896" />
        </div>
      </div>
    </div>
  );
}

function SettingsPage({ uiState, settings }: { uiState: UiState | null; settings: BackendSettings | null }) {
  const items = [
    { label: "Approval Mode", value: uiState?.settings.approvalMode ?? "supervised" },
    { label: "Workspace Root", value: uiState?.settings.workspaceRoot ?? "D:\\AgenticEngineeringNetwork" },
    { label: "Terminal Mode", value: uiState?.settings.terminalMode ?? "safe-allowlist" },
    { label: "Network", value: uiState?.settings.network ?? "disabled-by-default" },
    { label: "AI Provider", value: settings?.ai_provider ?? "local" },
    { label: "Repair Attempts", value: String(settings?.max_repair_attempts ?? "—") },
  ];
  return (
    <div className="p-5">
      <div className="mb-4">
        <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>Settings</h2>
        <p className="text-xs mt-0.5" style={{ color: "rgba(212,223,247,0.4)" }}>Read-only snapshot of ANN runtime and safety configuration.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {items.map(item => (
          <div key={item.label} className="rounded-xl border p-4" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
            <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "rgba(212,223,247,0.3)" }}>{item.label}</p>
            <p className="text-sm break-all" style={{ color: "#d4dff7", fontFamily: "JetBrains Mono, monospace" }}>{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LogsPage({ logs }: { logs: UiLogEntry[] }) {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const visibleLogs = levelFilter === "ALL" ? logs : logs.filter(log => log.level === levelFilter);
  const lc: Record<string, string> = { INFO: "#00d0ff", WARN: "#f5a623", ERROR: "#ff3757", DEBUG: "#445577" };
  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>System Logs</h2>
        <div className="flex gap-1 ml-auto">
          {["ALL", "INFO", "WARN", "ERROR"].map(l => (
            <button
              key={l}
              onClick={() => setLevelFilter(l)}
              className="px-2 py-1 rounded text-[10px] font-semibold transition-colors"
              style={{ background: l === levelFilter ? "rgba(0,208,255,0.1)" : "transparent", color: l === levelFilter ? "#00d0ff" : "rgba(212,223,247,0.3)", border: `1px solid ${l === levelFilter ? "rgba(0,208,255,0.25)" : "rgba(0,208,255,0.06)"}` }}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 rounded-xl border overflow-hidden" style={{ background: "#05080f", borderColor: "rgba(0,208,255,0.1)" }}>
        <div className="overflow-y-auto h-full">
          {visibleLogs.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm" style={{ color: "rgba(212,223,247,0.35)" }}>
              No audit logs available.
            </div>
          )}
          {visibleLogs.map((l, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-2 hover:bg-white/[0.02] border-b transition-colors"
              style={{ borderColor: "rgba(0,208,255,0.04)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              <span className="text-[9px] w-16 flex-shrink-0 mt-0.5 font-bold" style={{ color: lc[l.level] }}>{l.level}</span>
              <span className="w-14 flex-shrink-0" style={{ color: "rgba(212,223,247,0.25)" }}>{l.time}</span>
              <span className="w-24 flex-shrink-0 font-semibold" style={{ color: "rgba(212,223,247,0.45)" }}>{l.agent}</span>
              <span style={{ color: "rgba(212,223,247,0.6)" }}>{l.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ApprovalCenterPage({
  approvals,
  activeRun,
  loadState,
  onRefresh,
  onNotice,
}: {
  approvals: Approval[];
  activeRun: EngineeringRun | null;
  loadState: UiLoadState;
  onRefresh: () => Promise<void>;
  onNotice: (notice: AppNotice) => void;
}) {
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [bulkResolving, setBulkResolving] = useState<"approve" | "reject" | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  const pending = approvals.filter(approval => approval.status.toLowerCase() === "pending");
  const activeRunApprovals = activeRun
    ? pending.filter(approval =>
        approvalPayloadLine(approval.payload, "run_id") === activeRun.run_id ||
        activeRun.proposed_files.some(file => file.approval_id === approval.approval_id)
      )
    : [];
  const visibleApprovals = showResolved ? approvals : pending;

  const decide = async (approval: Approval, approved: boolean) => {
    setResolvingId(approval.approval_id);
    try {
      await api.decideApproval(approval.approval_id, approved);
      await onRefresh();
      onNotice({
        title: approved ? "Approval accepted" : "Approval rejected",
        message: `${approval.title} was ${approved ? "approved" : "rejected"}.`,
        tone: approved ? "success" : "warning",
      });
    } catch (error) {
      onNotice({
        title: "Approval failed",
        message: error instanceof Error ? error.message : "ANN could not submit this approval decision.",
        tone: "error",
      });
    } finally {
      setResolvingId(null);
    }
  };

  const decideActiveRun = async (approved: boolean) => {
    if (activeRunApprovals.length === 0) return;
    setBulkResolving(approved ? "approve" : "reject");
    try {
      for (const approval of activeRunApprovals) {
        await api.decideApproval(approval.approval_id, approved);
      }
      await onRefresh();
      onNotice({
        title: approved ? "Run approvals accepted" : "Run approvals rejected",
        message: `${activeRunApprovals.length} pending approval${activeRunApprovals.length === 1 ? "" : "s"} for the active run were ${approved ? "approved" : "rejected"}.`,
        tone: approved ? "success" : "warning",
      });
    } catch (error) {
      onNotice({
        title: "Bulk approval failed",
        message: error instanceof Error ? error.message : "ANN could not finish the active run approval batch.",
        tone: "error",
      });
    } finally {
      setBulkResolving(null);
    }
  };

  return (
    <div className="p-5 h-full flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield size={16} style={{ color: "#f5a623" }} />
            <h2 className="text-base font-bold" style={{ color: "#d4dff7" }}>Approval Center</h2>
          </div>
          <p className="text-xs" style={{ color: "rgba(212,223,247,0.42)" }}>
            Review and approve ANN write actions, shell actions, package installs, and deployment gates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowResolved(value => !value)}
            className="px-3 py-1.5 rounded-lg border text-[11px] font-semibold"
            style={{ color: "#00d0ff", borderColor: "rgba(0,208,255,0.25)", background: "rgba(0,208,255,0.05)" }}>
            {showResolved ? "Show pending" : "Show all"}
          </button>
          <button
            onClick={() => void onRefresh()}
            className="px-3 py-1.5 rounded-lg border text-[11px] font-semibold flex items-center gap-1.5"
            style={{ color: "#d4dff7", borderColor: "rgba(0,208,255,0.12)", background: "rgba(12,18,33,0.8)" }}>
            <RefreshCw size={11} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Pending", value: pending.length, color: "#f5a623" },
          { label: "Active Run", value: activeRunApprovals.length, color: "#00d0ff" },
          { label: "Total", value: approvals.length, color: "#7c3aed" },
        ].map(item => (
          <div key={item.label} className="rounded-xl border p-4" style={{ background: "rgba(12,18,33,0.8)", borderColor: "rgba(0,208,255,0.1)" }}>
            <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "rgba(212,223,247,0.35)" }}>{item.label}</p>
            <p className="text-2xl font-bold" style={{ color: item.color, fontFamily: "JetBrains Mono, monospace" }}>{item.value}</p>
          </div>
        ))}
      </div>

      {activeRunApprovals.length > 0 && (
        <div className="rounded-xl border p-4 flex items-center justify-between gap-4" style={{ background: "rgba(245,166,35,0.06)", borderColor: "rgba(245,166,35,0.2)" }}>
          <div>
            <p className="text-sm font-semibold" style={{ color: "#f5a623" }}>Active run is waiting for approval</p>
            <p className="text-[11px] mt-1 break-all" style={{ color: "rgba(212,223,247,0.5)", fontFamily: "JetBrains Mono, monospace" }}>
              {activeRun?.run_id} · {activeRunApprovals.length} pending decision{activeRunApprovals.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              disabled={bulkResolving != null}
              onClick={() => void decideActiveRun(true)}
              className="px-3 py-2 rounded-lg border text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50"
              style={{ color: "#00c896", borderColor: "rgba(0,200,150,0.35)", background: "rgba(0,200,150,0.08)" }}>
              <CheckCircle2 size={12} /> {bulkResolving === "approve" ? "Approving..." : "Approve active run"}
            </button>
            <button
              disabled={bulkResolving != null}
              onClick={() => void decideActiveRun(false)}
              className="px-3 py-2 rounded-lg border text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50"
              style={{ color: "#ff3757", borderColor: "rgba(255,55,87,0.35)", background: "rgba(255,55,87,0.08)" }}>
              <XCircle size={12} /> {bulkResolving === "reject" ? "Rejecting..." : "Reject active run"}
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 rounded-xl border overflow-hidden" style={{ background: "#05080f", borderColor: "rgba(0,208,255,0.1)" }}>
        {loadState === "loading" && (
          <div className="h-full flex items-center justify-center gap-2 text-sm" style={{ color: "rgba(212,223,247,0.45)" }}>
            <Loader2 size={14} className="animate-spin" /> Loading approvals...
          </div>
        )}
        {loadState === "error" && (
          <div className="h-full flex items-center justify-center gap-2 text-sm" style={{ color: "#ff3757" }}>
            <AlertCircle size={14} /> Could not load approvals from the backend.
          </div>
        )}
        {loadState !== "loading" && loadState !== "error" && visibleApprovals.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-6">
            <CheckCircle2 size={28} style={{ color: "#00c896" }} />
            <p className="mt-3 text-sm font-semibold" style={{ color: "#d4dff7" }}>No pending approvals</p>
            <p className="mt-1 text-xs" style={{ color: "rgba(212,223,247,0.4)" }}>ANN will continue automatically when no supervised gate is waiting.</p>
          </div>
        )}
        {loadState !== "loading" && loadState !== "error" && visibleApprovals.length > 0 && (
          <div className="h-full overflow-y-auto divide-y" style={{ borderColor: "rgba(0,208,255,0.06)" }}>
            {visibleApprovals.map(approval => {
              const color = approvalStatusColor(approval.status);
              const isPending = approval.status.toLowerCase() === "pending";
              const runId = approvalPayloadLine(approval.payload, "run_id");
              const path = approvalPayloadLine(approval.payload, "path");
              const command = approvalPayloadLine(approval.payload, "command");
              return (
                <div key={approval.approval_id} className="p-4 hover:bg-white/[0.02] transition-colors">
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: `${color}12`, border: `1px solid ${color}44`, color }}>
                      {isPending ? <Lock size={15} /> : approval.status.toLowerCase() === "approved" ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-sm font-semibold truncate" style={{ color: "#d4dff7" }}>{approval.title}</p>
                        <span className="px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider"
                          style={{ color, borderColor: `${color}44`, background: `${color}10`, fontFamily: "JetBrains Mono, monospace" }}>
                          {approval.status}
                        </span>
                        <span className="px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider"
                          style={{ color: "rgba(212,223,247,0.45)", borderColor: "rgba(0,208,255,0.08)", background: "rgba(0,208,255,0.03)" }}>
                          {approval.approval_type}
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed" style={{ color: "rgba(212,223,247,0.55)" }}>{approval.description}</p>
                      <div className="flex flex-wrap gap-2 mt-2 text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                        <span style={{ color: "rgba(212,223,247,0.32)" }}>by {approval.requested_by}</span>
                        {runId && <span style={{ color: "#00d0ff" }}>run {runId}</span>}
                        {path && <span className="break-all" style={{ color: "#f5a623" }}>{path}</span>}
                        {command && <span className="break-all" style={{ color: "#7c3aed" }}>{command}</span>}
                      </div>
                    </div>
                    {isPending && (
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          disabled={resolvingId === approval.approval_id}
                          onClick={() => void decide(approval, true)}
                          className="px-3 py-1.5 rounded-lg border text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50"
                          style={{ color: "#00c896", borderColor: "rgba(0,200,150,0.35)", background: "rgba(0,200,150,0.08)" }}>
                          <CheckCircle2 size={11} /> Approve
                        </button>
                        <button
                          disabled={resolvingId === approval.approval_id}
                          onClick={() => void decide(approval, false)}
                          className="px-3 py-1.5 rounded-lg border text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50"
                          style={{ color: "#ff3757", borderColor: "rgba(255,55,87,0.35)", background: "rgba(255,55,87,0.08)" }}>
                          <XCircle size={11} /> Reject
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function NoticeToast({ notice, onClose }: { notice: AppNotice | null; onClose: () => void }) {
  if (!notice) return null;
  const color = noticeColor(notice.tone);
  return (
    <div className="absolute right-72 top-14 z-50 w-80 rounded-xl border p-3 shadow-2xl"
      style={{ background: "rgba(12,18,33,0.96)", borderColor: `${color}55`, boxShadow: `0 0 24px ${color}22` }}>
      <div className="flex items-start gap-3">
        <div className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold" style={{ color }}>{notice.title}</p>
          <p className="text-[11px] mt-1 leading-relaxed" style={{ color: "rgba(212,223,247,0.55)" }}>{notice.message}</p>
        </div>
        <button aria-label="Dismiss notification" onClick={onClose} className="text-[10px]" style={{ color: "rgba(212,223,247,0.35)" }}>×</button>
      </div>
    </div>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState<PageId>("pipeline");
  const [terminalOpen, setTerminalOpen] = useState(true);
  const [runtime, setRuntime] = useState<RuntimeData>(INIT_RUNTIME);
  const [uiState, setUiState] = useState<UiState | null>(null);
  const [uiLoadState, setUiLoadState] = useState<UiLoadState>("loading");
  const [agentOffice, setAgentOffice] = useState<AgentOfficeState | null>(null);
  const [agentEvents, setAgentEvents] = useState<AgentOfficeEvent[]>([]);
  const [remoteLogs, setRemoteLogs] = useState<Array<Record<string, unknown>> | null>(null);
  const [backendRuns, setBackendRuns] = useState<EngineeringRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [uiRefreshToken, setUiRefreshToken] = useState(0);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [backendLoadState, setBackendLoadState] = useState<UiLoadState>("loading");
  const [approvalLoadState, setApprovalLoadState] = useState<UiLoadState>("loading");
  const [backendSettings, setBackendSettings] = useState<BackendSettings | null>(null);
  const [notice, setNotice] = useState<AppNotice | null>(null);
  const [tokenHistory, setTokenHistory] = useState(() =>
    Array.from({ length: 30 }, () => 0)
  );

  const showNotice = (nextNotice: AppNotice) => {
    setNotice(nextNotice);
    window.setTimeout(() => setNotice(current => current === nextNotice ? null : current), 4500);
  };

  useEffect(() => {
    let cancelled = false;

    const loadRuntime = async () => {
      try {
        const response = await fetch("/api/runtime-monitor/state", { cache: "no-store" });
        if (!response.ok) throw new Error(`runtime monitor returned ${response.status}`);
        const payload = await response.json();
        if (cancelled) return;
        const nextRuntime: RuntimeData = {
          gpu: payload.compute?.gpuPercent ?? 0,
          cpu: payload.compute?.cpuPercent ?? 0,
          gpuSource: payload.compute?.gpuSource ?? "unknown",
          gpuCuda: payload.compute?.gpuCudaPercent ?? 0,
          vramUsed: payload.memory?.vramUsedGb ?? 0,
          vramTotal: payload.memory?.vramTotalGb ?? 0,
          ramUsed: payload.memory?.ramUsedGb ?? 0,
          ramTotal: payload.memory?.ramTotalGb ?? 0,
          tokensPerSec: payload.inference?.tokensPerSec ?? 0,
          activeModel: payload.inference?.activeModel ?? "No model loaded",
          activeStage: payload.inference?.activeStage ?? "Idle",
          uptime: payload.system?.uptime ?? "—",
          gpuModel: payload.system?.gpuModel ?? "Unavailable",
          pipelineId: payload.system?.pipelineId ?? "Idle",
          status: payload.status ?? "partial",
          loadedModels: payload.inference?.loadedModels ?? [],
          errors: payload.errors ?? [],
        };
        setRuntime(nextRuntime);
        setTokenHistory(prev => [...prev.slice(1), nextRuntime.tokensPerSec]);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "runtime telemetry unavailable";
        setRuntime(prev => ({
          ...prev,
          status: "unavailable",
          activeModel: "Runtime monitor unavailable",
          activeStage: "Telemetry fetch failed",
          errors: [message],
        }));
      }
    };

    void loadRuntime();
    const interval = setInterval(loadRuntime, 1000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadUiState = async () => {
      try {
        const payload = await localJson<UiState>("/api/ui/state");
        if (cancelled) return;
        setUiState(payload);
        setUiLoadState("ready");
      } catch {
        if (cancelled) return;
        setUiLoadState("error");
      }
    };

    void loadUiState();
    const interval = setInterval(loadUiState, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [uiRefreshToken]);

  useEffect(() => {
    let cancelled = false;

    const loadBackendState = async () => {
      const [officeResult, eventsResult, logsResult, settingsResult, runsResult, approvalsResult] = await Promise.allSettled([
        api.agentOfficeState(),
        api.agentOfficeEvents(20),
        api.logs(),
        api.settings(),
        api.runs(25),
        api.approvals(),
      ]);
      if (cancelled) return;
      if (officeResult.status === "fulfilled") setAgentOffice(officeResult.value);
      if (eventsResult.status === "fulfilled") setAgentEvents(eventsResult.value.events);
      if (logsResult.status === "fulfilled") setRemoteLogs(logsResult.value);
      if (settingsResult.status === "fulfilled") setBackendSettings(settingsResult.value);
      if (runsResult.status === "fulfilled") {
        setBackendRuns(runsResult.value);
        setBackendLoadState("ready");
      } else {
        setBackendLoadState("error");
      }
      if (approvalsResult.status === "fulfilled") {
        setApprovals(approvalsResult.value);
        setApprovalLoadState("ready");
      } else {
        setApprovalLoadState("error");
      }
    };

    void loadBackendState();
    const interval = setInterval(loadBackendState, 7500);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const refreshApprovalsAndRuns = async () => {
    const [approvalsResult, runsResult] = await Promise.allSettled([
      api.approvals(),
      api.runs(25),
    ]);
    if (approvalsResult.status === "fulfilled") {
      setApprovals(approvalsResult.value);
      setApprovalLoadState("ready");
    } else {
      setApprovalLoadState("error");
      showNotice({
        title: "Approvals unavailable",
        message: approvalsResult.reason instanceof Error ? approvalsResult.reason.message : "ANN could not reach the approvals API.",
        tone: "error",
      });
    }
    if (runsResult.status === "fulfilled") {
      setBackendRuns(runsResult.value);
      setBackendLoadState("ready");
    } else {
      setBackendLoadState("error");
    }
  };

  const activeRun = backendRuns.find(run => run.run_id === selectedRunId) ?? latestRun(backendRuns);
  const stages = pipelineStages(agentOffice, activeRun);
  const pipelineRunning = latestRun(backendRuns)?.status === "running";
  const logs = logRows(remoteLogs, uiState);

  const renderPage = () => {
    switch (activePage) {
      case "dashboard":  return <DashboardPage runtime={runtime} uiState={uiState} runs={backendRuns} agentOffice={agentOffice} agentEvents={agentEvents} uiLoadState={backendLoadState === "loading" ? "loading" : uiLoadState} onSelectRun={(runId) => { setSelectedRunId(runId); setActivePage("pipeline"); }} />;
      case "pipeline":   return <PipelinePage stages={stages} activeRun={activeRun} logs={logs} agentEvents={agentEvents} loadState={backendLoadState} onNotice={showNotice} />;
      case "models":     return <ModelsPage runtime={runtime} uiState={uiState} onRefresh={() => {
        setUiRefreshToken(token => token + 1);
        showNotice({ title: "Inventory refreshed", message: "ANN is rescanning declared local models and active model processes.", tone: "info" });
      }} />;
      case "logs":       return <LogsPage logs={logs} />;
      case "projects":   return <WorkspaceListPage title="Projects" icon={FolderOpen} description="Manage your engineering projects, repositories, and team workspaces." entries={uiState?.projects ?? []} loadState={uiLoadState} />;
      case "knowledge":  return <WorkspaceListPage title="Knowledge Base" icon={Database} description="Curated context, documentation, and domain knowledge for agent grounding." entries={uiState?.docs ?? []} loadState={uiLoadState} accent="#7c3aed" />;
      case "runtime":    return <RuntimeDetailPage runtime={runtime} tokenHistory={tokenHistory} />;
      case "artifacts":  return <WorkspaceListPage title="Artifacts" icon={Archive} description="Browse and download all generated code, specs, and reports from pipeline runs." entries={uiState?.artifacts ?? []} loadState={uiLoadState} accent="#f5a623" />;
      case "approvals":  return <ApprovalCenterPage approvals={approvals} activeRun={activeRun} loadState={approvalLoadState} onRefresh={refreshApprovalsAndRuns} onNotice={showNotice} />;
      case "settings":   return <SettingsPage uiState={uiState} settings={backendSettings} />;
      default:           return null;
    }
  };

  return (
    <div className="w-screen h-screen overflow-hidden flex flex-col bg-background" style={{ fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="flex flex-1 overflow-hidden">
        <LeftNav active={activePage} onNav={setActivePage} />
        <div className="flex-1 flex flex-col overflow-hidden">
          <TopBar
            page={activePage}
            pipelineRunning={pipelineRunning}
            onTogglePipeline={() => {
              setActivePage("pipeline");
              if (!pipelineRunning) setTerminalOpen(true);
              showNotice({
                title: pipelineRunning ? "Live pipeline" : "Start a new run",
                message: pipelineRunning ? "Showing the active engineering run." : "Describe the project in ANN Terminal to start its real pipeline.",
                tone: "info",
              });
            }}
            terminalOpen={terminalOpen}
            onToggleTerminal={() => setTerminalOpen(p => !p)}
            onNav={setActivePage}
            onNotice={showNotice}
          />
          <NoticeToast notice={notice} onClose={() => setNotice(null)} />
          <div className="flex-1 flex overflow-hidden">
            <main className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-y-auto">
                {renderPage()}
              </div>
              {terminalOpen && <TerminalPanel onClose={() => setTerminalOpen(false)} onRunSelected={(runId) => {
                setSelectedRunId(runId);
                setActivePage("pipeline");
                void refreshApprovalsAndRuns();
              }} />}
            </main>
            <RuntimePanel data={runtime} tokenHistory={tokenHistory} />
          </div>
        </div>
      </div>
      <StatusBar runtime={runtime} pipelineRunning={pipelineRunning} />
    </div>
  );
}
