from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from agentic_engineering_network.orchestration.diff_manager import DiffManager
from agentic_engineering_network.security.approvals import ApprovalCenter, ApprovalType


@dataclass(frozen=True)
class ProposedFile:
    path: str
    content: str
    diff: str
    approval_id: str


class WorkspaceManager:
    def __init__(self, root: Path, approvals: ApprovalCenter, display_root: str | None = None) -> None:
        self.root = root.resolve()
        self.approvals = approvals
        self.diff_manager = DiffManager()
        self.display_root = display_root

    def propose_file(
        self,
        relative_path: str,
        content: str,
        requested_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProposedFile:
        target = (self.root / relative_path).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Generated file path escaped workspace: {relative_path}") from exc
        display_path = str(PureWindowsPath(self.display_root, relative_path)) if self.display_root else str(target)
        diff = self.diff_manager.build_diff(target, content)
        approval = self.approvals.request(
            ApprovalType.FILE_CREATE if not target.exists() else ApprovalType.FILE_MODIFY,
            title=f"Write {relative_path}",
            description="Review the unified diff before applying this generated file.",
            requested_by=requested_by,
            payload={
                "path": str(target),
                "display_path": display_path,
                "diff": diff,
                "content": content,
                **(metadata or {}),
            },
        )
        return ProposedFile(
            path=display_path,
            content=content,
            diff=diff,
            approval_id=approval.approval_id,
        )
