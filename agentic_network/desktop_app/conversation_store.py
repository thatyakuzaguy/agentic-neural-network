"""Persistent local conversation store for ANN Desktop Chat."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONVERSATIONS_ROOT = REPO_ROOT / "outputs" / "conversations"
CONVERSATION_ID_PATTERN = re.compile(r"^conversation_[0-9]{3,}$")
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


class ConversationStoreError(ValueError):
    """Raised when a conversation path or payload is unsafe."""


@dataclass(frozen=True)
class ConversationRecord:
    """Conversation metadata."""

    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    execution_mode: str
    project_id: str | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatMessage:
    """One persisted chat message."""

    role: str
    timestamp: str
    content: str
    agent: str | None = None
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConversationBundle:
    """Full persisted conversation payload."""

    conversation: ConversationRecord
    messages: list[dict[str, Any]]
    runs: list[dict[str, Any]]
    memory: dict[str, Any]
    artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation": self.conversation.to_dict(),
            "messages": self.messages,
            "runs": self.runs,
            "memory": self.memory,
            "artifacts": self.artifacts,
        }


class ConversationStore:
    """JSON-backed local conversation store under outputs/conversations."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or DEFAULT_CONVERSATIONS_ROOT).resolve()
        if not _is_outputs_conversations_root(self.root):
            raise ConversationStoreError("Conversation root must be an outputs/conversations directory.")
        if _has_protected_part(self.root):
            raise ConversationStoreError("Conversation root cannot be inside a protected ANN area.")
        self.root.mkdir(parents=True, exist_ok=True)

    def create_conversation(
        self,
        *,
        title: str = "ANN Conversation",
        execution_mode: str = "FAST",
        project_id: str | None = None,
    ) -> ConversationRecord:
        """Create a new persistent conversation."""

        now = _now()
        conversation_id = self._next_conversation_id()
        record = ConversationRecord(
            conversation_id=conversation_id,
            title=title.strip() or "ANN Conversation",
            created_at=now,
            updated_at=now,
            execution_mode=_normalize_mode(execution_mode),
            project_id=project_id,
            status="CREATED",
        )
        conversation_dir = self._conversation_dir(conversation_id)
        conversation_dir.mkdir(parents=True, exist_ok=False)
        _write_json(conversation_dir / "conversation.json", record.to_dict())
        _write_json(conversation_dir / "messages.json", {"messages": []})
        _write_json(conversation_dir / "runs.json", {"runs": []})
        _write_json(conversation_dir / "memory.json", {"items": []})
        _write_json(conversation_dir / "artifacts.json", {"artifacts": []})
        return record

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        agent: str | None = None,
        model: str | None = None,
    ) -> ChatMessage:
        """Append one message to a conversation."""

        conversation_dir = self._conversation_dir(conversation_id)
        if not conversation_dir.is_dir():
            raise ConversationStoreError(f"Unknown conversation: {conversation_id}")
        message = ChatMessage(
            role=_normalize_role(role),
            timestamp=_now(),
            content=content.strip(),
            agent=agent,
            model=model,
        )
        payload = _read_json(conversation_dir / "messages.json")
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        messages.append(message.to_dict())
        _write_json(conversation_dir / "messages.json", {"messages": messages})
        self._touch(conversation_id)
        return message

    def attach_run(
        self,
        conversation_id: str,
        run_id: str,
        status: str,
        artifacts: list[str],
    ) -> None:
        """Attach a run summary to a conversation."""

        conversation_dir = self._conversation_dir(conversation_id)
        if not conversation_dir.is_dir():
            raise ConversationStoreError(f"Unknown conversation: {conversation_id}")
        payload = _read_json(conversation_dir / "runs.json")
        runs = payload.get("runs") if isinstance(payload.get("runs"), list) else []
        runs.append(
            {
                "run_id": run_id,
                "status": status,
                "artifacts": artifacts,
                "attached_at": _now(),
            }
        )
        _write_json(conversation_dir / "runs.json", {"runs": runs})
        artifact_payload = _read_json(conversation_dir / "artifacts.json")
        existing = artifact_payload.get("artifacts") if isinstance(artifact_payload.get("artifacts"), list) else []
        _write_json(conversation_dir / "artifacts.json", {"artifacts": _dedupe([*existing, *artifacts])})
        self._touch(conversation_id)

    def list_conversations(self) -> list[ConversationRecord]:
        """Return persisted conversations newest first."""

        records: list[ConversationRecord] = []
        for path in self.root.iterdir():
            if not path.is_dir() or not CONVERSATION_ID_PATTERN.fullmatch(path.name):
                continue
            payload = _read_json(path / "conversation.json")
            record = _conversation_from_payload(payload)
            if record is not None:
                records.append(record)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def load_conversation(self, conversation_id: str) -> ConversationBundle:
        """Load a full conversation bundle."""

        conversation_dir = self._conversation_dir(conversation_id)
        if not conversation_dir.is_dir():
            raise ConversationStoreError(f"Unknown conversation: {conversation_id}")
        conversation = _conversation_from_payload(_read_json(conversation_dir / "conversation.json"))
        if conversation is None:
            raise ConversationStoreError("Conversation metadata is invalid.")
        messages = _read_json(conversation_dir / "messages.json").get("messages", [])
        runs = _read_json(conversation_dir / "runs.json").get("runs", [])
        memory = _read_json(conversation_dir / "memory.json")
        artifacts = _read_json(conversation_dir / "artifacts.json").get("artifacts", [])
        return ConversationBundle(
            conversation=conversation,
            messages=messages if isinstance(messages, list) else [],
            runs=runs if isinstance(runs, list) else [],
            memory=memory if isinstance(memory, dict) else {},
            artifacts=artifacts if isinstance(artifacts, list) else [],
        )

    def update_conversation_status(self, conversation_id: str, status: str) -> ConversationRecord:
        """Update conversation status and timestamp."""

        bundle = self.load_conversation(conversation_id)
        updated = ConversationRecord(
            conversation_id=bundle.conversation.conversation_id,
            title=bundle.conversation.title,
            created_at=bundle.conversation.created_at,
            updated_at=_now(),
            execution_mode=bundle.conversation.execution_mode,
            project_id=bundle.conversation.project_id,
            status=status.strip().upper() or "UNKNOWN",
        )
        _write_json(self._conversation_dir(conversation_id) / "conversation.json", updated.to_dict())
        return updated

    def conversation_dir(self, conversation_id: str) -> Path:
        """Return validated conversation directory path."""

        return self._conversation_dir(conversation_id)

    def _touch(self, conversation_id: str) -> None:
        bundle = self.load_conversation(conversation_id)
        updated = ConversationRecord(
            conversation_id=bundle.conversation.conversation_id,
            title=bundle.conversation.title,
            created_at=bundle.conversation.created_at,
            updated_at=_now(),
            execution_mode=bundle.conversation.execution_mode,
            project_id=bundle.conversation.project_id,
            status=bundle.conversation.status,
        )
        _write_json(self._conversation_dir(conversation_id) / "conversation.json", updated.to_dict())

    def _next_conversation_id(self) -> str:
        existing = [
            int(path.name.split("_")[1])
            for path in self.root.iterdir()
            if path.is_dir() and CONVERSATION_ID_PATTERN.fullmatch(path.name)
        ]
        return f"conversation_{(max(existing) + 1 if existing else 1):03d}"

    def _conversation_dir(self, conversation_id: str) -> Path:
        if not CONVERSATION_ID_PATTERN.fullmatch(conversation_id):
            raise ConversationStoreError("Invalid conversation id.")
        path = (self.root / conversation_id).resolve()
        if not _is_relative_to(path, self.root):
            raise ConversationStoreError("Conversation path traversal blocked.")
        return path


def _conversation_from_payload(payload: dict[str, Any]) -> ConversationRecord | None:
    required = ("conversation_id", "title", "created_at", "updated_at", "execution_mode", "status")
    if not all(isinstance(payload.get(key), str) and payload.get(key) for key in required):
        return None
    project_id = payload.get("project_id")
    return ConversationRecord(
        conversation_id=str(payload["conversation_id"]),
        title=str(payload["title"]),
        created_at=str(payload["created_at"]),
        updated_at=str(payload["updated_at"]),
        execution_mode=str(payload["execution_mode"]),
        project_id=str(project_id) if isinstance(project_id, str) and project_id else None,
        status=str(payload["status"]),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_mode(value: str) -> str:
    mode = value.strip().upper()
    return mode if mode in {"FAST", "POWERFUL"} else "FAST"


def _normalize_role(value: str) -> str:
    role = value.strip().lower()
    if role not in {"user", "assistant", "system"}:
        raise ConversationStoreError(f"Invalid message role: {value}")
    return role


def _is_outputs_conversations_root(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return len(parts) >= 2 and parts[-2:] == ["outputs", "conversations"]


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result

