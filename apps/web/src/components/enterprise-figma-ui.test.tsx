import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("Enterprise Figma UI integration", () => {
  it("uses the exported ANN OS shell as the home interface", () => {
    const page = readFileSync(join(process.cwd(), "src", "app", "page.tsx"), "utf-8");
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );

    expect(page).toContain("EnterpriseFigmaUI");
    expect(source).toContain("ANN OS v2.4.1");
    expect(source).toContain("RuntimePanel");
    expect(source).toContain("PipelinePage");
    expect(source).toContain("pipelineStages");
    expect(source).toContain("Recent Pipeline Runs");
  });

  it("connects runtime monitor to local telemetry instead of mock metrics", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );
    const route = readFileSync(
      join(process.cwd(), "src", "app", "api", "runtime-monitor", "state", "route.ts"),
      "utf-8"
    );

    expect(source).toContain('fetch("/api/runtime-monitor/state"');
    expect(source).toContain("data.gpuModel");
    expect(source).toContain("gpuSource:");
    expect(source).toContain("No active GPU model process");
    expect(source).not.toContain('value: "RTX 4090"');
    expect(route).toContain("nvidia-smi");
    expect(route).toContain("GPU Engine(*)\\\\Utilization Percentage");
    expect(route).toContain("windows-gpu-engine");
    expect(route).toContain("query-compute-apps");
    expect(route).toContain("os.totalmem()");
    expect(route).not.toContain("shell: true");
  });

  it("preserves the Figma shell while wiring the safe desktop terminal", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );
    const terminalRoute = readFileSync(
      join(process.cwd(), "src", "app", "api", "terminal", "run", "route.ts"),
      "utf-8"
    );

    expect(source).toContain('fetch("/api/conversation/message"');
    expect(source).toContain("Watching live run");
    expect(source).toContain("api.getRun(activeRunId)");
    expect(source).toContain("api.auditLogs(60)");
    expect(source).toContain('title="Projects" icon={FolderOpen}');
    expect(source).toContain("RuntimePanel");
    expect(source).toContain("TerminalPanel");
    expect(terminalRoute).toContain("Safe ANN terminal commands");
    expect(terminalRoute).toContain("Blocked:");
    expect(terminalRoute).not.toContain("exec(");
    expect(terminalRoute).not.toContain("spawn(");
    expect(terminalRoute).not.toContain("execFile(");
  });

  it("routes natural language through the conversation endpoint while preserving terminal safety", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );
    const conversationRoute = readFileSync(
      join(process.cwd(), "src", "app", "api", "conversation", "message", "route.ts"),
      "utf-8"
    );

    expect(source).toContain("Conversation classifier active");
    expect(source).toContain("Write naturally or enter ANN command");
    expect(conversationRoute).toContain("classifyTerminalInput");
    expect(conversationRoute).toContain("handleConversationMessage");
    expect(conversationRoute).toContain("blockedShellAttemptResponse");
    expect(conversationRoute).not.toContain("exec(");
    expect(conversationRoute).not.toContain("spawn(");
    expect(conversationRoute).not.toContain("execFile(");
  });

  it("wires Figma pages to local and backend data sources without touching styling setup", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );

    expect(source).toContain('localJson<UiState>("/api/ui/state")');
    expect(source).toContain("api.agentOfficeState()");
    expect(source).toContain("api.agentOfficeEvents(20)");
    expect(source).toContain("api.logs()");
    expect(source).toContain("api.settings()");
    expect(source).toContain("api.runs(25)");
    expect(source).toContain("api.approvals()");
    expect(source).toContain("WorkspaceListPage");
    expect(source).toContain("ApprovalCenterPage");
    expect(source).toContain("RuntimeDetailPage");
    expect(source).toContain("SettingsPage");
    expect(source).not.toContain("JWT Auth API");
    expect(source).not.toContain("STATIC_LOGS");
    expect(source).not.toContain("tailwind.config.js");
  });

  it("keeps visible controls functional inside the exact Figma shell", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );

    expect(source).toContain("runCommand(command)");
    expect(source).toContain("setStatusFilter");
    expect(source).toContain("downloadJson(\"ann-selected-stage-artifacts.json\"");
    expect(source).toContain("api.decideApproval");
    expect(source).toContain("Approve active run");
    expect(source).toContain("Refresh Inventory");
    expect(source).toContain("setSelectedRunId(runId)");
    expect(source).toContain("onRunSelected");
    expect(source).toContain("setLevelFilter");
    expect(source).toContain("NoticeToast");
    expect(source).toContain('aria-label="Execute ANN command"');
    expect(source).toContain('item.created_at ?? item.timestamp');
    expect(source).toContain('events.slice(-7).reverse()');
    expect(source).toContain("formatConfidence(stage.confidence)");
    expect(source).toContain("displayRunIdea(run.idea)");
    expect(source).toContain('latestRun(backendRuns)?.status === "running"');
    expect(source).toContain('run.status === "running"');
    expect(source).toContain('activeAgentStates.has(agent.status)');
  });

  it("does not render dependency-blocked pipeline stages as active errors", () => {
    const source = readFileSync(
      join(process.cwd(), "src", "components", "enterprise-figma-ui.tsx"),
      "utf-8"
    );

    expect(source).toContain('if (normalized === "blocked") return "blocked";');
    expect(source).toContain("effectiveTaskStatus");
    expect(source).not.toContain('if (["blocked", "skipped"].includes(normalized)) return "skipped";');
  });
});
