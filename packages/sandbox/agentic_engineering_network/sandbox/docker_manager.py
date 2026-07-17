from __future__ import annotations

from dataclasses import dataclass

from agentic_engineering_network.security.approvals import ApprovalCenter, ApprovalType


@dataclass(frozen=True)
class SandboxCommand:
    command: tuple[str, ...]
    approval_id: str


class DockerSandboxManager:
    def __init__(self, approvals: ApprovalCenter) -> None:
        self.approvals = approvals

    def propose_command(self, command: tuple[str, ...], requested_by: str) -> SandboxCommand:
        approval = self.approvals.request(
            ApprovalType.SHELL_EXECUTION,
            title=f"Execute sandbox command: {' '.join(command)}",
            description="Command will run inside Docker after approval.",
            requested_by=requested_by,
            payload={"command": list(command), "execution": "docker"},
        )
        return SandboxCommand(command=command, approval_id=approval.approval_id)

