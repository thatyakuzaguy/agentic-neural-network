from pathlib import Path

from fastapi.testclient import TestClient

from agentic_engineering_network.logs.audit import AuditLogger
from app.main import app
from app.services.agent_office import LiveAgentOfficeProvider, MockAgentOfficeProvider


def test_mock_agent_office_provider_returns_required_agents() -> None:
    state = MockAgentOfficeProvider().state()

    assert state["provider"] == "mock"
    assert len(state["agents"]) == 14
    assert {agent["name"] for agent in state["agents"]} >= {
        "Product Manager",
        "Frontend Engineer",
        "Compliance Agent",
        "Meta Review Agent",
    }
    for agent in state["agents"]:
        assert set(agent) >= {
            "id",
            "name",
            "role",
            "status",
            "currentTask",
            "progress",
            "position",
            "deskId",
            "lastActivityAt",
            "events",
            "confidence",
            "blockedReason",
            "approvalRequired",
        }


def test_live_agent_office_provider_maps_audit_events(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.record("agent.started", "Frontend Engineer Agent", "Building the interface.", {"run_id": "run-1"})
    audit.record("sandbox.command.completed", "QA Agent", "pytest passed.", {"run_id": "run-1"})

    state = LiveAgentOfficeProvider(audit).state()

    assert state["provider"] == "live"
    frontend = next(agent for agent in state["agents"] if agent["id"] == "frontend-engineer")
    qa = next(agent for agent in state["agents"] if agent["id"] == "qa-engineer")
    assert frontend["currentTask"] == "Building the interface."
    assert qa["status"] in {"testing", "completed"}


def test_live_agent_office_does_not_assign_orchestrator_failure_to_planner(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.record("agent.completed", "Planner Agent", "Created implementation plan.", {"run_id": "run-1"})
    audit.record("run.completed", "orchestrator", "Run failed after approval gates.", {"run_id": "run-1"})

    state = LiveAgentOfficeProvider(audit).state()

    planner = next(agent for agent in state["agents"] if agent["id"] == "planner")
    assert planner["status"] == "completed"
    assert planner["currentTask"] == "Created implementation plan."


def test_live_agent_office_closes_participating_agents_after_completed_run(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.record("agent.started", "Frontend Engineer Agent", "Building the interface.", {"run_id": "run-1"})
    audit.record("approval.resolved", "DevOps Agent", "Deployment approved.", {"run_id": "run-1"})
    audit.record("run.completed", "orchestrator", "Run completed after approval gates.", {"run_id": "run-1"})

    state = LiveAgentOfficeProvider(audit).state()

    frontend = next(agent for agent in state["agents"] if agent["id"] == "frontend-engineer")
    devops = next(agent for agent in state["agents"] if agent["id"] == "devops-engineer")
    assert state["runId"] == "run-1"
    assert state["runStatus"] == "completed"
    assert frontend["status"] == "completed"
    assert devops["status"] == "completed"
    assert frontend["progress"] == 100
    assert devops["approvalRequired"] is False


def test_live_agent_office_uses_only_latest_run_for_current_state(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.record("agent.started", "Frontend Engineer Agent", "Old work.", {"run_id": "run-old"})
    audit.record("run.completed", "orchestrator", "Run completed after approval gates.", {"run_id": "run-old"})
    audit.record("agent.started", "Planner Agent", "Planning current work.", {"run_id": "run-current"})

    state = LiveAgentOfficeProvider(audit).state()

    frontend = next(agent for agent in state["agents"] if agent["id"] == "frontend-engineer")
    planner = next(agent for agent in state["agents"] if agent["id"] == "planner")
    assert state["runId"] == "run-current"
    assert state["runStatus"] == "active"
    assert frontend["status"] == "idle"
    assert planner["status"] == "thinking"


def test_agent_office_api_endpoints() -> None:
    client = TestClient(app)

    state = client.get("/api/agent-office/state")
    events = client.get("/api/agent-office/events?limit=5")

    assert state.status_code == 200
    assert events.status_code == 200
    assert len(state.json()["agents"]) == 14
    assert "events" in events.json()
