from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Protocol

from agentic_engineering_network.logs.audit import AuditLogger


AgentStatus = str


STATUSES: tuple[AgentStatus, ...] = (
    "idle",
    "thinking",
    "planning",
    "coding",
    "testing",
    "reviewing",
    "blocked",
    "waiting approval",
    "completed",
    "failed",
)


@dataclass(frozen=True)
class OfficePosition:
    x: int
    y: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class AgentOfficeEvent:
    id: str
    agentId: str
    agentName: str
    type: str
    message: str
    createdAt: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "agentId": self.agentId,
            "agentName": self.agentName,
            "type": self.type,
            "message": self.message,
            "createdAt": self.createdAt,
        }


@dataclass(frozen=True)
class AgentOfficeAgent:
    id: str
    name: str
    role: str
    status: AgentStatus
    currentTask: str
    progress: int
    position: OfficePosition
    deskId: str
    lastActivityAt: str
    events: tuple[AgentOfficeEvent, ...]
    confidence: float
    blockedReason: str | None
    approvalRequired: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "currentTask": self.currentTask,
            "progress": self.progress,
            "position": self.position.to_dict(),
            "deskId": self.deskId,
            "lastActivityAt": self.lastActivityAt,
            "events": [event.to_dict() for event in self.events],
            "confidence": self.confidence,
            "blockedReason": self.blockedReason,
            "approvalRequired": self.approvalRequired,
        }


class AgentOfficeProvider(Protocol):
    def state(self) -> dict[str, Any]:
        ...

    def events(self, limit: int = 50) -> list[dict[str, str]]:
        ...


OFFICE_LAYOUT: tuple[dict[str, Any], ...] = (
    {"id": "product-manager", "name": "Product Manager", "role": "Product strategy", "position": OfficePosition(120, 118)},
    {"id": "requirements-agent", "name": "Requirements Agent", "role": "Requirements analysis", "position": OfficePosition(286, 118)},
    {"id": "planner", "name": "Planner", "role": "Task decomposition", "position": OfficePosition(452, 118)},
    {"id": "architect", "name": "Architect", "role": "System architecture", "position": OfficePosition(618, 118)},
    {"id": "database-engineer", "name": "Database Engineer", "role": "Data modeling", "position": OfficePosition(120, 300)},
    {"id": "backend-engineer", "name": "Backend Engineer", "role": "API engineering", "position": OfficePosition(286, 300)},
    {"id": "frontend-engineer", "name": "Frontend Engineer", "role": "UI engineering", "position": OfficePosition(452, 300)},
    {"id": "devops-engineer", "name": "DevOps Engineer", "role": "Sandbox and release automation", "position": OfficePosition(618, 300)},
    {"id": "qa-engineer", "name": "QA Engineer", "role": "Verification", "position": OfficePosition(120, 482)},
    {"id": "security-engineer", "name": "Security Engineer", "role": "Security review", "position": OfficePosition(286, 482)},
    {"id": "compliance-agent", "name": "Compliance Agent", "role": "Compliance evidence", "position": OfficePosition(452, 482)},
    {"id": "documentation-agent", "name": "Documentation Agent", "role": "Technical writing", "position": OfficePosition(618, 482)},
    {"id": "release-agent", "name": "Release Agent", "role": "Packaging and release", "position": OfficePosition(784, 300)},
    {"id": "meta-review-agent", "name": "Meta Review Agent", "role": "Cross-agent review", "position": OfficePosition(784, 482)},
)


ACTOR_ALIASES: dict[str, str] = {
    "Product Manager Agent": "product-manager",
    "Product Manager": "product-manager",
    "Requirements Agent": "requirements-agent",
    "Planner Agent": "planner",
    "Planner": "planner",
    "Solution Architect Agent": "architect",
    "Architect": "architect",
    "Frontend Engineer Agent": "frontend-engineer",
    "Frontend Engineer": "frontend-engineer",
    "Backend Engineer Agent": "backend-engineer",
    "Backend Engineer": "backend-engineer",
    "Database Engineer Agent": "database-engineer",
    "Database Engineer": "database-engineer",
    "DevOps Agent": "devops-engineer",
    "DevOps Engineer": "devops-engineer",
    "QA Agent": "qa-engineer",
    "QA Engineer": "qa-engineer",
    "Security Agent": "security-engineer",
    "Security Engineer": "security-engineer",
    "Compliance Agent": "compliance-agent",
    "Documentation Agent": "documentation-agent",
    "Documentation Engineer": "documentation-agent",
    "Release Agent": "release-agent",
    "Meta Review Agent": "meta-review-agent",
    "ProjectLifecycleRunner": "qa-engineer",
    "approval-mode:full": "release-agent",
}


MOCK_STATUS_BY_INDEX = (
    "thinking",
    "planning",
    "planning",
    "reviewing",
    "coding",
    "coding",
    "thinking",
    "testing",
    "testing",
    "reviewing",
    "waiting approval",
    "coding",
    "completed",
    "reviewing",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_event_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _status_from_event(event: dict[str, Any]) -> AgentStatus:
    event_type = str(event.get("event_type", "")).lower()
    message = str(event.get("message", "")).lower()
    if "failed" in event_type or "failed" in message or "exception" in event_type:
        return "failed"
    if "blocked" in event_type or "blocked" in message:
        return "blocked"
    if "approval" in event_type and "pending" in message:
        return "waiting approval"
    if "approval" in event_type:
        return "waiting approval"
    if "completed" in event_type or "completed" in message or "passed" in message:
        return "completed"
    if "test" in event_type or "pytest" in message or "build" in message:
        return "testing"
    if "review" in event_type or "security" in event_type:
        return "reviewing"
    if "plan" in event_type or "task" in message:
        return "planning"
    if "file" in event_type or "diff" in message or "patch" in message:
        return "coding"
    if "started" in event_type or "run." in event_type:
        return "thinking"
    return "thinking"


def _progress_for_status(status: AgentStatus, event_count: int) -> int:
    base = {
        "idle": 0,
        "thinking": 22,
        "planning": 38,
        "coding": 54,
        "testing": 68,
        "reviewing": 78,
        "blocked": 45,
        "waiting approval": 62,
        "completed": 100,
        "failed": 100,
    }[status]
    if status in {"completed", "failed", "blocked", "waiting approval"}:
        return base
    return min(96, base + min(event_count * 4, 24))


class MockAgentOfficeProvider:
    def state(self) -> dict[str, Any]:
        timestamp = _now()
        agents = []
        all_events = []
        for index, item in enumerate(OFFICE_LAYOUT):
            status = MOCK_STATUS_BY_INDEX[index % len(MOCK_STATUS_BY_INDEX)]
            event = AgentOfficeEvent(
                id=_stable_event_id(item["id"], status, timestamp[:13]),
                agentId=str(item["id"]),
                agentName=str(item["name"]),
                type=status,
                message=f"{item['name']} is {status} in demo office mode.",
                createdAt=timestamp,
            )
            all_events.append(event)
            agents.append(
                AgentOfficeAgent(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    role=str(item["role"]),
                    status=status,
                    currentTask=f"Demo: {item['role']}",
                    progress=_progress_for_status(status, index % 5),
                    position=item["position"],
                    deskId=f"desk-{index + 1:02d}",
                    lastActivityAt=timestamp,
                    events=(event,),
                    confidence=round(0.68 + (index % 5) * 0.06, 2),
                    blockedReason="Waiting for human approval" if status == "waiting approval" else None,
                    approvalRequired=status == "waiting approval",
                )
            )
        return {
            "provider": "mock",
            "generatedAt": timestamp,
            "office": {"width": 960, "height": 640, "theme": "pixel-office"},
            "agents": [agent.to_dict() for agent in agents],
            "events": [event.to_dict() for event in all_events[-30:]],
        }

    def events(self, limit: int = 50) -> list[dict[str, str]]:
        return self.state()["events"][-limit:]


class LiveAgentOfficeProvider:
    def __init__(self, audit: AuditLogger) -> None:
        self.audit = audit
        self.mock = MockAgentOfficeProvider()

    def state(self) -> dict[str, Any]:
        raw_events = self.audit.tail(300)
        latest_run_id = self._latest_run_id(raw_events)
        current_events = self._events_for_run(raw_events, latest_run_id)
        mapped_events = self._map_events(current_events)
        if not mapped_events:
            return self.mock.state()

        terminal_status = self._terminal_run_status(current_events)

        latest_by_agent = {event.agentId: event for event in mapped_events}
        events_by_agent: dict[str, list[AgentOfficeEvent]] = {}
        status_by_agent: dict[str, AgentStatus] = {}
        for raw in current_events:
            agent_id = self._agent_id_for_actor(str(raw.get("actor", "")))
            if not agent_id:
                continue
            status_by_agent[agent_id] = _status_from_event(raw)
        for event in mapped_events:
            events_by_agent.setdefault(event.agentId, []).append(event)

        timestamp = _now()
        agents = []
        for index, item in enumerate(OFFICE_LAYOUT):
            agent_id = str(item["id"])
            agent_events = tuple(events_by_agent.get(agent_id, [])[-5:])
            latest = latest_by_agent.get(agent_id)
            status = status_by_agent.get(agent_id, "idle" if not agent_events else "thinking")
            if latest and terminal_status == "completed" and status not in {"failed", "blocked"}:
                status = "completed"
            elif latest and terminal_status in {"failed", "blocked"} and status not in {
                "completed",
                "failed",
                "blocked",
            }:
                status = "blocked"
            agents.append(
                AgentOfficeAgent(
                    id=agent_id,
                    name=str(item["name"]),
                    role=str(item["role"]),
                    status=status,
                    currentTask=latest.message if latest else "No recent live task.",
                    progress=_progress_for_status(status, len(agent_events)),
                    position=item["position"],
                    deskId=f"desk-{index + 1:02d}",
                    lastActivityAt=latest.createdAt if latest else timestamp,
                    events=agent_events,
                    confidence=0.9 if agent_events else 0.55,
                    blockedReason=latest.message if status in {"blocked", "failed"} and latest else None,
                    approvalRequired=status == "waiting approval",
                )
            )
        return {
            "provider": "live",
            "runId": latest_run_id,
            "runStatus": terminal_status or "active",
            "generatedAt": timestamp,
            "office": {"width": 960, "height": 640, "theme": "pixel-office"},
            "agents": [agent.to_dict() for agent in agents],
            "events": [event.to_dict() for event in mapped_events[-50:]],
        }

    def events(self, limit: int = 50) -> list[dict[str, str]]:
        return self.state()["events"][-limit:]

    def _map_events(self, raw_events: list[dict[str, Any]]) -> list[AgentOfficeEvent]:
        mapped: list[AgentOfficeEvent] = []
        for raw in raw_events:
            actor = str(raw.get("actor", ""))
            agent_id = self._agent_id_for_actor(actor)
            if not agent_id:
                continue
            name = next(item["name"] for item in OFFICE_LAYOUT if item["id"] == agent_id)
            created_at = str(raw.get("created_at") or raw.get("createdAt") or _now())
            event_type = str(raw.get("event_type", "activity"))
            message = str(raw.get("message", "Agent activity updated."))
            mapped.append(
                AgentOfficeEvent(
                    id=str(raw.get("event_id") or _stable_event_id(agent_id, event_type, created_at, message)),
                    agentId=agent_id,
                    agentName=str(name),
                    type=_status_from_event(raw),
                    message=message,
                    createdAt=created_at,
                )
            )
        return mapped

    @staticmethod
    def _latest_run_id(raw_events: list[dict[str, Any]]) -> str | None:
        for event in reversed(raw_events):
            metadata = event.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("run_id"), str):
                return str(metadata["run_id"])
        return None

    @staticmethod
    def _events_for_run(raw_events: list[dict[str, Any]], run_id: str | None) -> list[dict[str, Any]]:
        if run_id is None:
            return raw_events
        return [
            event
            for event in raw_events
            if isinstance(event.get("metadata"), dict) and event["metadata"].get("run_id") == run_id
        ]

    @staticmethod
    def _terminal_run_status(raw_events: list[dict[str, Any]]) -> str | None:
        for event in reversed(raw_events):
            event_type = str(event.get("event_type", "")).lower()
            message = str(event.get("message", "")).lower()
            if event_type == "run.blocked" or "run blocked" in message:
                return "blocked"
            if event_type == "run.failed" or "run failed" in message:
                return "failed"
            if event_type == "run.completed" and "run completed" in message:
                return "completed"
        return None

    @staticmethod
    def _agent_id_for_actor(actor: str) -> str | None:
        if actor in ACTOR_ALIASES:
            return ACTOR_ALIASES[actor]
        lowered = actor.lower()
        for alias, agent_id in ACTOR_ALIASES.items():
            if alias.lower() in lowered:
                return agent_id
        return None


class AgentOfficeService:
    def __init__(self, audit: AuditLogger) -> None:
        self.live_provider = LiveAgentOfficeProvider(audit)

    def state(self) -> dict[str, Any]:
        return self.live_provider.state()

    def events(self, limit: int = 50) -> list[dict[str, str]]:
        return self.live_provider.events(limit)
