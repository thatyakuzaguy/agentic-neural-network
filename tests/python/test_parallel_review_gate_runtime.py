import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_network.autonomous_loop.runtime import (
    STATUS_BLOCKED,
    STATUS_FAILED_APPROVAL,
    STATUS_PASSED,
    run_autonomous_engineering_loop,
)
from agentic_network.human_approval_agent.runtime import APPROVAL_TOKEN, DECISION_DENIED, authorize_apply
from agentic_network.patch_apply_agent.runtime import (
    APPLY_STATUS_DRY_RUN_PASSED,
    APPLY_STATUS_REJECTED,
    APPLY_STATUS_SKIPPED,
    apply_approved_patches,
)
from agentic_network.pipeline.parallel_gate_runtime import (
    DECISION_APPROVED,
    DECISION_BLOCKED,
    DECISION_NEEDS_REVISION,
    evaluate_parallel_review_gate,
)


@pytest.fixture(autouse=True)
def _safe_local_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", "/mnt/c,/mnt/d,/mnt/e")
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "")

    class Policy:
        def is_path_blocked(self, path: Path) -> bool:
            return False

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.load_filesystem_policy", lambda: Policy())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_parallel(run_dir: Path, decision: str, *, summary: str = "") -> None:
    _write(
        run_dir / "37_parallel_review.json",
        json.dumps(
            {
                "status": "VALID",
                "decision": decision,
                "consensus_summary": summary or f"Parallel review decision: {decision}.",
                "validation_errors": [],
            },
            indent=2,
        ),
    )


def _write_human_ready_run(run_dir: Path) -> None:
    payload = {
        "final_decision": "Approved",
        "patch_approval_decision": "Approved",
        "patch_approval_validation_passed": True,
        "patch_approval_validation_errors": [],
        "merge_readiness_decision": "READY TO APPLY",
        "merge_readiness_validation_passed": True,
        "patch_apply_status": "SKIPPED",
        "output_files": {},
    }
    _write(run_dir / "summary.json", json.dumps(payload, indent=2))
    _write(run_dir / "12_patch_approval.md", "APPROVAL DECISION\nApproved\n")
    _write(run_dir / "15_merge_readiness.md", "MERGE DECISION\nREADY TO APPLY\n")


def _write_patch_ready_run(run_dir: Path, repo: Path) -> Path:
    payload = {
        "final_decision": "Approved",
        "patch_approval_decision": "Approved",
        "patch_approval_validation_passed": True,
        "human_approval_decision": "Approved",
        "human_approval_validation_passed": True,
        "output_files": {},
    }
    target = repo / "app" / "safe.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    _write(run_dir / "summary.json", json.dumps(payload, indent=2))
    _write(run_dir / "12_patch_approval.md", "APPROVAL DECISION\nApproved\n")
    _write(run_dir / "16_human_approval.md", "AUTHORIZATION DECISION\nApproved\n")
    _write(
        run_dir / "patches" / "patch_001.diff",
        "--- a/app/safe.txt\n"
        "+++ b/app/safe.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-old value\n"
        "+new value\n"
        " unchanged\n",
    )
    return target


def _write_autonomous_run(run_dir: Path, *, test_status: str = "FAILED") -> None:
    payload = {
        "final_decision": "Approved",
        "patch_apply_status": "APPLIED",
        "test_runner_status": test_status,
        "output_files": {},
    }
    _write(run_dir / "summary.json", json.dumps(payload, indent=2))
    _write(run_dir / "13_patch_apply.md", "APPLY STATUS\nApplied\n")
    _write(run_dir / "14_test_run.md", f"TEST STATUS\n{test_status}\n")


def test_blocked_blocks_human_approval(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_human_ready_run(run_dir)
    _write_parallel(run_dir, DECISION_BLOCKED)

    result = authorize_apply(run_dir, approval_token=APPROVAL_TOKEN, approve_apply=True)

    assert result.decision == DECISION_DENIED
    assert "parallel_review_gate_blocks_human_approval" in result.validation_errors


def test_blocked_blocks_patch_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    run_dir = tmp_path / "run"
    target = _write_patch_ready_run(run_dir, repo)
    _write_parallel(run_dir, DECISION_BLOCKED)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "parallel_review_gate_blocks_patch_apply:BLOCKED" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"


def test_blocked_blocks_autonomous_loop(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_autonomous_run(run_dir)
    _write_parallel(run_dir, DECISION_BLOCKED)

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_BLOCKED
    assert "parallel_review_gate_blocks_autonomous_loop:BLOCKED" in result.validation_errors
    assert result.attempts == []


def test_needs_revision_blocks_normal_patch_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    run_dir = tmp_path / "run"
    target = _write_patch_ready_run(run_dir, repo)
    _write_parallel(run_dir, DECISION_NEEDS_REVISION)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "parallel_review_gate_blocks_patch_apply:NEEDS_REVISION" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"


def test_needs_revision_permits_retry_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    _write_autonomous_run(run_dir)
    _write_parallel(run_dir, DECISION_NEEDS_REVISION)

    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.run_self_healing",
        lambda run_dir, max_attempts: _fake_healing(run_dir),
    )
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_quality", _fake_quality)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_approval", _fake_approval)

    result = run_autonomous_engineering_loop(run_dir, run_tests=True, max_attempts=1)

    assert result.status == STATUS_FAILED_APPROVAL
    assert result.attempts
    assert "parallel_review_gate_blocks_autonomous_loop:NEEDS_REVISION" not in result.validation_errors


def test_approved_permits_normal_patch_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    run_dir = tmp_path / "run"
    target = _write_patch_ready_run(run_dir, repo)
    _write_parallel(run_dir, DECISION_APPROVED)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_PASSED
    assert result.validation_errors == []
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"


def test_missing_parallel_review_json_does_not_break_pipeline(tmp_path: Path) -> None:
    decision = evaluate_parallel_review_gate(tmp_path / "run")

    assert decision.decision == DECISION_APPROVED
    assert decision.allowed is True
    assert decision.blocks_human_approval is False
    assert decision.blocks_patch_apply is False
    assert decision.blocks_autonomous_loop is False


def test_invalid_parallel_review_decision_fails_closed(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write(run_dir / "37_parallel_review.json", json.dumps({"decision": "MAYBE"}))

    decision = evaluate_parallel_review_gate(run_dir)

    assert decision.decision == DECISION_BLOCKED
    assert decision.blocks_human_approval is True
    assert decision.blocks_patch_apply is True
    assert decision.blocks_autonomous_loop is True
    assert "parallel_review_decision_invalid:MAYBE" in decision.validation_errors


def test_autonomous_loop_v4_regression_when_no_parallel_review(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_autonomous_run(run_dir, test_status="PASSED")

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_PASSED
    assert result.attempts == []


def test_patch_apply_no_approval_still_does_not_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    run_dir = tmp_path / "run"
    target = _write_patch_ready_run(run_dir, repo)
    _write_parallel(run_dir, DECISION_APPROVED)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=False, dry_run=False)

    assert result.status == APPLY_STATUS_SKIPPED
    assert "approve_patches_flag_missing" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"


def test_parallel_review_gate_does_not_touch_protected_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    protected = tmp_path / "models" / "model.gguf"
    _write_parallel(run_dir, DECISION_APPROVED)
    _write(protected, "do not touch\n")

    before = protected.read_text(encoding="utf-8")
    decision = evaluate_parallel_review_gate(run_dir)
    after = protected.read_text(encoding="utf-8")

    assert decision.decision == DECISION_APPROVED
    assert after == before


def _fake_healing(run_dir: Path):
    retry = run_dir / "19_retry_patch_001.diff"
    _write(
        retry,
        "--- a/agentic_network/config.py\n"
        "+++ b/agentic_network/config.py\n"
        "@@ -1,1 +1,2 @@\n"
        " APP_NAME = 'ANN'\n"
        "+PARALLEL_GATE_RETRY = True\n",
    )
    return SimpleNamespace(
        status="RETRY_PATCH_GENERATED",
        retry_patch_path=str(retry),
        validation_errors=[],
        validation_warnings=[],
    )


def _fake_quality(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "29_retry_patch_quality.md")
    _write(artifact, "QUALITY\nIMPLEMENTATION_READY\n")
    return SimpleNamespace(
        decision="IMPLEMENTATION_READY",
        validation_passed=True,
        validation_errors=[],
        warnings=[],
        score=100,
        artifact_path=str(artifact),
    )


def _fake_approval(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "30_retry_patch_approval.md")
    _write(artifact, "APPROVAL DECISION\nApproved\n")
    return SimpleNamespace(
        decision="Approved",
        validation_passed=True,
        validation_errors=[],
        warnings=[],
        artifact_path=str(artifact),
    )
