"use client";

import {
  CheckCircle2,
  CircleAlert,
  CirclePlus,
  Code2,
  FlaskConical,
  LayoutGrid,
  Minus,
  MousePointerClick,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  ZoomIn,
  ZoomOut
} from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AgentOfficeAgent, AgentOfficeEvent, AgentOfficeState, AgentOfficeStatus } from "../lib/api";

const statusColors: Record<AgentOfficeStatus, string> = {
  idle: "#7f8da3",
  thinking: "#a78bfa",
  planning: "#60a5fa",
  coding: "#34d399",
  testing: "#fbbf24",
  reviewing: "#22d3ee",
  blocked: "#fb923c",
  "waiting approval": "#f472b6",
  completed: "#4ade80",
  failed: "#f87171"
};

const statusLabels: AgentOfficeStatus[] = [
  "idle",
  "thinking",
  "planning",
  "coding",
  "testing",
  "reviewing",
  "blocked",
  "waiting approval",
  "completed",
  "failed"
];

function statusIcon(status: AgentOfficeStatus) {
  if (status === "coding") return <Code2 size={14} aria-hidden />;
  if (status === "testing") return <FlaskConical size={14} aria-hidden />;
  if (status === "blocked") return <CircleAlert size={14} aria-hidden />;
  if (status === "waiting approval") return <MousePointerClick size={14} aria-hidden />;
  if (status === "completed") return <CheckCircle2 size={14} aria-hidden />;
  if (status === "failed") return <CircleAlert size={14} aria-hidden />;
  if (status === "reviewing") return <ShieldCheck size={14} aria-hidden />;
  return <Sparkles size={14} aria-hidden />;
}

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function AgentStatusBubble({ status }: { status: AgentOfficeStatus }) {
  return (
    <span className={`agent-status-bubble agent-status-${status.replace(/\s+/g, "-")}`} style={{ borderColor: statusColors[status] }}>
      {statusIcon(status)}
      {status}
    </span>
  );
}

export function AgentAvatar({ agent }: { agent: AgentOfficeAgent }) {
  return (
    <div className={`agent-avatar agent-avatar-${agent.status.replace(/\s+/g, "-")}`} aria-hidden>
      <div className="agent-avatar-head">{initials(agent.name)}</div>
      <div className="agent-avatar-body" />
      <div className="agent-avatar-shadow" />
    </div>
  );
}

export function AgentDesk({ agent, selected, onSelect }: { agent: AgentOfficeAgent; selected: boolean; onSelect: () => void }) {
  return (
    <button
      aria-label={`${agent.name}, ${agent.status}, ${agent.currentTask}`}
      className={`agent-desk ${selected ? "agent-desk-selected" : ""}`}
      onClick={onSelect}
      style={{ left: agent.position.x, top: agent.position.y }}
      title={agent.currentTask}
      type="button"
    >
      <span className="agent-nameplate">{agent.name}</span>
      <AgentStatusBubble status={agent.status} />
      <span className="desk-top">
        <span className="desk-monitor">
          <span className="monitor-lines" />
        </span>
        <span className="desk-keyboard" />
        <span className="desk-mug" />
        {agent.status === "coding" ? <span className="typing-dots" aria-hidden><i /><i /><i /></span> : null}
        {agent.status === "testing" ? <span className="test-badge" aria-hidden>✓</span> : null}
        {agent.status === "blocked" ? <span className="warning-badge" aria-hidden>!</span> : null}
        {agent.approvalRequired ? <span className="approval-badge" aria-hidden>OK?</span> : null}
        {agent.status === "completed" ? <span className="success-badge" aria-hidden>✓</span> : null}
        {agent.status === "failed" ? <span className="error-badge" aria-hidden>×</span> : null}
      </span>
      <AgentAvatar agent={agent} />
      <span className="progress-track" aria-label={`${agent.name} progress ${agent.progress}%`}>
        <span className="progress-fill" style={{ width: `${agent.progress}%`, background: statusColors[agent.status] }} />
      </span>
    </button>
  );
}

export function AgentOfficeToolbar({
  zoom,
  onZoomIn,
  onZoomOut,
  onLayout,
  onSettings,
  onAddAgent
}: {
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onLayout: () => void;
  onSettings: () => void;
  onAddAgent: () => void;
}) {
  return (
    <div className="agent-office-toolbar" aria-label="Agent office controls">
      <button type="button" onClick={onAddAgent}><CirclePlus size={16} /> Add Agent</button>
      <button type="button" onClick={onLayout}><LayoutGrid size={16} /> Layout</button>
      <button type="button" onClick={onSettings}><Settings size={16} /> Settings</button>
      <span className="toolbar-spacer" />
      <button type="button" onClick={onZoomOut} aria-label="Zoom out"><ZoomOut size={16} /><Minus size={12} /></button>
      <span className="zoom-readout">{Math.round(zoom * 100)}%</span>
      <button type="button" onClick={onZoomIn} aria-label="Zoom in"><ZoomIn size={16} /><Plus size={12} /></button>
    </div>
  );
}

export function AgentOfficeLegend() {
  return (
    <section className="agent-office-legend" aria-label="Agent status legend">
      {statusLabels.map((status) => (
        <span key={status}>
          <i style={{ background: statusColors[status] }} />
          {status}
        </span>
      ))}
    </section>
  );
}

export function AgentActivityFeed({ events }: { events: AgentOfficeEvent[] }) {
  return (
    <aside className="agent-activity-feed" aria-label="Agent office activity feed">
      <h2>Activity Feed</h2>
      <div className="feed-list">
        {events.length ? (
          events.slice(-18).reverse().map((event) => (
            <article key={event.id} className="feed-item">
              <span>{event.agentName}</span>
              <p>{event.message}</p>
              <time>{new Date(event.createdAt).toLocaleTimeString()}</time>
            </article>
          ))
        ) : (
          <p className="empty-feed">No recent office events.</p>
        )}
      </div>
    </aside>
  );
}

export function AgentDetailsPanel({ agent }: { agent: AgentOfficeAgent | null }) {
  if (!agent) {
    return (
      <aside className="agent-details-panel" aria-label="Agent details">
        <h2>Agent Details</h2>
        <p>Select an agent desk to inspect current work, confidence, approvals, and recent events.</p>
      </aside>
    );
  }

  return (
    <aside className="agent-details-panel" aria-label={`${agent.name} details`}>
      <div className="details-heading">
        <div>
          <h2>{agent.name}</h2>
          <p>{agent.role}</p>
        </div>
        <AgentStatusBubble status={agent.status} />
      </div>
      <dl>
        <dt>Current task</dt>
        <dd>{agent.currentTask}</dd>
        <dt>Progress</dt>
        <dd>{agent.progress}%</dd>
        <dt>Confidence</dt>
        <dd>{Math.round(agent.confidence * 100)}%</dd>
        <dt>Approval</dt>
        <dd>{agent.approvalRequired ? "Required" : "Not required"}</dd>
        {agent.blockedReason ? (
          <>
            <dt>Blocked reason</dt>
            <dd>{agent.blockedReason}</dd>
          </>
        ) : null}
      </dl>
      <h3>Recent agent events</h3>
      <ul>
        {agent.events.length ? agent.events.slice(-4).map((event) => <li key={event.id}>{event.message}</li>) : <li>No recent events.</li>}
      </ul>
    </aside>
  );
}

export function AgentOfficeMap({
  state,
  zoom,
  selectedId,
  onSelect
}: {
  state: AgentOfficeState;
  zoom: number;
  selectedId: string | null;
  onSelect: (agent: AgentOfficeAgent) => void;
}) {
  return (
    <section className="office-map-frame" aria-label="Pixel office map view">
      <div className="office-map-scroll">
        <div
          className="office-map"
          style={{
            width: state.office.width,
            height: state.office.height,
            transform: `scale(${zoom})`,
            transformOrigin: "top left"
          }}
        >
          <div className="office-room room-product" />
          <div className="office-room room-engineering" />
          <div className="office-room room-quality" />
          <div className="office-rug" />
          <div className="office-wall wall-top" />
          <div className="office-bookshelf shelf-left" />
          <div className="office-bookshelf shelf-right" />
          <div className="office-plant plant-a" />
          <div className="office-plant plant-b" />
          <div className="office-plant plant-c" />
          <div className="office-table" />
          {state.agents.map((agent) => (
            <AgentDesk key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent)} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function AgentOfficeVisualizer() {
  const [zoom, setZoom] = useState(0.92);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState("Live polling enabled");
  const { data, isLoading, error } = useQuery({
    queryKey: ["agent-office-state"],
    queryFn: api.agentOfficeState,
    refetchInterval: 2000
  });

  const selectedAgent = useMemo(
    () => data?.agents.find((agent) => agent.id === selectedId) ?? data?.agents[0] ?? null,
    [data?.agents, selectedId]
  );

  if (isLoading) {
    return <main className="agent-office-page"><div className="agent-office-loading">Loading agent office...</div></main>;
  }

  if (error || !data) {
    return <main className="agent-office-page"><div className="agent-office-loading">Agent office data is unavailable.</div></main>;
  }

  return (
    <main className="agent-office-page">
      <header className="agent-office-header">
        <div>
          <p>Agent Office Visualizer</p>
          <h1>Pixel office live operations</h1>
        </div>
        <a href="/" className="office-back-link">Workbench</a>
      </header>
      <AgentOfficeToolbar
        zoom={zoom}
        onZoomIn={() => setZoom((value) => Math.min(1.4, Number((value + 0.1).toFixed(2))))}
        onZoomOut={() => setZoom((value) => Math.max(0.65, Number((value - 0.1).toFixed(2))))}
        onLayout={() => setNotice("Layout reset to original office grid")}
        onSettings={() => setNotice("Settings are local UI controls in this version")}
        onAddAgent={() => setNotice("Add Agent is a placeholder for future custom agents")}
      />
      <div className="agent-office-notice" role="status">
        {data.provider === "live" ? "Live audit log provider" : "Mock demo provider"} · {notice}
      </div>
      <div className="agent-office-grid">
        <div className="agent-office-main">
          <AgentOfficeMap state={data} zoom={zoom} selectedId={selectedAgent?.id ?? null} onSelect={(agent) => setSelectedId(agent.id)} />
          <AgentOfficeLegend />
        </div>
        <div className="agent-office-side">
          <AgentDetailsPanel agent={selectedAgent} />
          <AgentActivityFeed events={data.events} />
        </div>
      </div>
    </main>
  );
}
