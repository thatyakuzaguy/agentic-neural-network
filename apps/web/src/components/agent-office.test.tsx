import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AgentAvatar, AgentDetailsPanel, AgentOfficeLegend, AgentStatusBubble } from "./agent-office";
import type { AgentOfficeAgent } from "../lib/api";

const agent: AgentOfficeAgent = {
  id: "frontend-engineer",
  name: "Frontend Engineer",
  role: "UI engineering",
  status: "coding",
  currentTask: "Building the pixel office.",
  progress: 64,
  position: { x: 120, y: 300 },
  deskId: "desk-05",
  lastActivityAt: "2026-06-06T00:00:00Z",
  events: [
    {
      id: "event-1",
      agentId: "frontend-engineer",
      agentName: "Frontend Engineer",
      type: "coding",
      message: "Building the pixel office.",
      createdAt: "2026-06-06T00:00:00Z"
    }
  ],
  confidence: 0.82,
  blockedReason: null,
  approvalRequired: false
};

describe("Agent Office Visualizer components", () => {
  it("renders status bubbles and avatar labels", () => {
    const html = renderToStaticMarkup(
      <>
        <AgentStatusBubble status="coding" />
        <AgentAvatar agent={agent} />
      </>
    );

    expect(html).toContain("coding");
    expect(html).toContain("FE");
  });

  it("renders details and legend content", () => {
    const html = renderToStaticMarkup(
      <>
        <AgentDetailsPanel agent={agent} />
        <AgentOfficeLegend />
      </>
    );

    expect(html).toContain("Frontend Engineer");
    expect(html).toContain("Building the pixel office.");
    expect(html).toContain("waiting approval");
    expect(html).toContain("completed");
  });
});
