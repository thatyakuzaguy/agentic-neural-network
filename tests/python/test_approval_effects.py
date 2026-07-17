from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentic_engineering_network.security.approvals import ApprovalRequest, ApprovalStatus, ApprovalType

from app.api.routes import _apply_approval_effect


def test_file_approval_effect_writes_content() -> None:
    target = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\approval-effect\SPEC.md")
    if target.exists():
        target.unlink()
    item = ApprovalRequest(
        approval_id=str(uuid4()),
        approval_type=ApprovalType.FILE_CREATE,
        title="Write test SPEC",
        description="test",
        requested_by="test",
        payload={
            "path": str(target),
            "display_path": str(target),
            "content": "# Written after approval\n",
        },
        status=ApprovalStatus.APPROVED,
        created_at=datetime.now(timezone.utc).isoformat(),
        resolved_at=datetime.now(timezone.utc).isoformat(),
    )

    _apply_approval_effect(item)

    assert target.read_text(encoding="utf-8") == "# Written after approval\n"
    assert asdict(item)["status"] == ApprovalStatus.APPROVED
