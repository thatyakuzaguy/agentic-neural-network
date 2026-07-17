from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from agentic_engineering_network.logs.audit import AuditLogger


class ApprovalType(StrEnum):
    FILE_CREATE = "file_create"
    FILE_MODIFY = "file_modify"
    FILE_DELETE = "file_delete"
    SHELL_EXECUTION = "shell_execution"
    PACKAGE_INSTALLATION = "package_installation"
    DEPLOYMENT = "deployment"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    approval_type: ApprovalType
    title: str
    description: str
    requested_by: str
    payload: dict[str, Any]
    status: ApprovalStatus
    created_at: str
    resolved_at: str | None = None


class ApprovalCenter:
    def __init__(self, audit: AuditLogger, storage_path: Path | None = None) -> None:
        self.audit = audit
        self.storage_path = storage_path
        self._items: dict[str, ApprovalRequest] = {}
        self._lock = Lock()
        self._load()

    def request(
        self,
        approval_type: ApprovalType,
        title: str,
        description: str,
        requested_by: str,
        payload: dict[str, Any],
    ) -> ApprovalRequest:
        item = ApprovalRequest(
            approval_id=str(uuid4()),
            approval_type=approval_type,
            title=title,
            description=description,
            requested_by=requested_by,
            payload=payload,
            status=ApprovalStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._items[item.approval_id] = item
            self._save_locked()
        self.audit.record("approval.requested", requested_by, title, asdict(item))
        return item

    def resolve(self, approval_id: str, approved: bool, actor: str = "user") -> ApprovalRequest:
        with self._lock:
            current = self._items[approval_id]
            item = ApprovalRequest(
                **{
                    **asdict(current),
                    "status": ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._items[approval_id] = item
            self._save_locked()
        self.audit.record(
            "approval.resolved",
            actor,
            f"{item.title}: {item.status}",
            asdict(item),
        )
        return item

    def list(self) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._items.values())

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.audit.record(
                "approval.persistence_failed",
                "ApprovalCenter",
                f"Could not load approval state from {self.storage_path}",
            )
            return
        if not isinstance(payload, list):
            return
        loaded: dict[str, ApprovalRequest] = {}
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                item = ApprovalRequest(
                    approval_id=str(raw["approval_id"]),
                    approval_type=ApprovalType(str(raw["approval_type"])),
                    title=str(raw["title"]),
                    description=str(raw["description"]),
                    requested_by=str(raw["requested_by"]),
                    payload=dict(raw.get("payload", {})),
                    status=ApprovalStatus(str(raw["status"])),
                    created_at=str(raw["created_at"]),
                    resolved_at=str(raw["resolved_at"]) if raw.get("resolved_at") else None,
                )
            except (KeyError, TypeError, ValueError):
                continue
            loaded[item.approval_id] = item
        self._items = loaded

    def _save_locked(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
        payload = [asdict(item) for item in self._items.values()]
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.storage_path)
