from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.security.approvals import ApprovalRequest, ApprovalType
from agentic_engineering_network.shared.config import Settings


def apply_approval_effect(item: ApprovalRequest, settings: Settings, audit: AuditLogger) -> None:
    if item.approval_type in {ApprovalType.FILE_CREATE, ApprovalType.FILE_MODIFY}:
        target = _validated_effect_path(item.payload, settings)
        content = str(item.payload.get("content", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        audit.record(
            "file.applied",
            "approval-center",
            f"Applied {item.approval_type} to {target}",
            {"approval_id": item.approval_id, "path": str(target), "display_path": item.payload.get("display_path")},
        )
        return

    if item.approval_type == ApprovalType.FILE_DELETE:
        target = _validated_effect_path(item.payload, settings)
        if target.exists():
            target.unlink()
        audit.record(
            "file.deleted",
            "approval-center",
            f"Deleted {target}",
            {"approval_id": item.approval_id, "path": str(target), "display_path": item.payload.get("display_path")},
        )
        return

    audit.record(
        "approval.effect.recorded",
        "approval-center",
        f"Approved gated action: {item.title}",
        {"approval_id": item.approval_id, "approval_type": str(item.approval_type), "payload": item.payload},
    )


def _validated_effect_path(payload: dict[str, Any], settings: Settings) -> Path:
    raw_path = payload.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise HTTPException(status_code=400, detail="Approval payload does not contain a valid path.")
    target = Path(raw_path).resolve()
    allowed_roots = [settings.generated_projects_path.parent.resolve(), settings.workspace_drive_mount.resolve()]
    for allowed_root in allowed_roots:
        try:
            target.relative_to(allowed_root)
            return target
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail=f"Approval path is outside allowed workspaces: {target}")
