from pathlib import Path

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.security.approvals import (
    ApprovalCenter,
    ApprovalStatus,
    ApprovalType,
)


def test_approval_lifecycle(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    center = ApprovalCenter(audit)

    request = center.request(
        ApprovalType.FILE_CREATE,
        "Create file",
        "Create generated artifact.",
        "test",
        {"path": "generated-projects/example/SPEC.md"},
    )
    resolved = center.resolve(request.approval_id, approved=True)

    assert request.status == ApprovalStatus.PENDING
    assert resolved.status == ApprovalStatus.APPROVED
    assert len(audit.tail()) == 2


def test_approval_center_persists_local_state(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    storage_path = tmp_path / "approvals.json"
    center = ApprovalCenter(audit, storage_path)

    request = center.request(
        ApprovalType.SHELL_EXECUTION,
        "Run tests",
        "Run generated tests after review.",
        "QA Agent",
        {"run_id": "run-123", "gate": "qa"},
    )

    restored = ApprovalCenter(audit, storage_path)
    restored_items = restored.list()

    assert storage_path.exists()
    assert len(restored_items) == 1
    assert restored_items[0].approval_id == request.approval_id
    assert restored_items[0].status == ApprovalStatus.PENDING
