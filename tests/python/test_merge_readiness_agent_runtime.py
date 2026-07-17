import json
from pathlib import Path

from agentic_network.merge_readiness_agent.runtime import (
    DECISION_BLOCKED,
    DECISION_READY_TO_APPLY,
    DECISION_READY_TO_MERGE,
    MERGE_READINESS_OUTPUT_FILE,
    evaluate_merge_readiness,
    parse_merge_readiness_sections,
    validate_merge_readiness_report,
)


def _write_run(
    run_dir: Path,
    *,
    final_decision: str = "Approved",
    patch_approval_decision: str = "Approved",
    patch_approval_validation_passed: bool = True,
    patch_apply_status: str = "SKIPPED",
    test_runner_status: str = "SKIPPED",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "final_decision": final_decision,
        "patch_approval_decision": patch_approval_decision,
        "patch_approval_validation_passed": patch_approval_validation_passed,
        "patch_apply_status": patch_apply_status,
        "test_runner_status": test_runner_status,
        "test_runner_run_tests_flag": test_runner_status == "PASSED",
        "output_files": {},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "08_final_review.md").write_text(
        f"FINAL DECISION\n{final_decision}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "11_execution_plan.md").write_text(
        "EXECUTION SUMMARY\n- Safe plan.\n\nEXECUTION CONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "12_patch_approval.md").write_text(
        f"APPROVAL DECISION\n{patch_approval_decision}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "13_patch_apply.md").write_text(
        f"APPLY STATUS\n{patch_apply_status}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "14_test_run.md").write_text(
        f"TEST STATUS\n{test_runner_status}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )


def test_ready_to_apply_when_approved_but_not_applied_or_tested(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_apply_status="SKIPPED", test_runner_status="SKIPPED")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_READY_TO_APPLY
    assert result.validation_passed is True
    assert (tmp_path / MERGE_READINESS_OUTPUT_FILE).exists()
    parsed = parse_merge_readiness_sections(result.report)
    assert parsed["merge_decision"] == DECISION_READY_TO_APPLY


def test_ready_to_apply_allows_dry_run_passed_and_skipped_tests(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_apply_status="DRY_RUN_PASSED", test_runner_status="SKIPPED")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_READY_TO_APPLY


def test_ready_to_merge_when_applied_and_tests_passed(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_apply_status="APPLIED", test_runner_status="PASSED")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_READY_TO_MERGE
    assert result.validation_errors == []
    assert result.validation_passed is True
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["merge_readiness_decision"] == DECISION_READY_TO_MERGE
    assert summary["merge_readiness_validation_passed"] is True


def test_blocked_final_review_not_approved(tmp_path: Path) -> None:
    _write_run(tmp_path, final_decision="Rejected")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert result.validation_passed is True
    assert "Final Reviewer did not approve the run." in result.parsed_sections["merge_summary"]


def test_blocked_patch_approval_not_approved(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_approval_decision="Rejected")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert "Patch Approval Agent did not approve the patch set." in result.parsed_sections["merge_summary"]


def test_blocked_patch_approval_validation_failed(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_approval_validation_passed=False)

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert "Patch Approval validation did not pass." in result.parsed_sections["merge_summary"]


def test_blocked_patch_apply_failure(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_apply_status="FAILED")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert "Patch Apply Agent reported an unsafe or failed state." in result.parsed_sections["merge_summary"]


def test_blocked_test_failure(tmp_path: Path) -> None:
    _write_run(tmp_path, test_runner_status="FAILED")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert "Test Runner Agent reported a failed, timed out, or rejected state." in result.parsed_sections["merge_summary"]


def test_blocked_test_timeout(tmp_path: Path) -> None:
    _write_run(tmp_path, test_runner_status="TIMEOUT")

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED


def test_missing_artifact_handling(tmp_path: Path) -> None:
    _write_run(tmp_path)
    (tmp_path / "14_test_run.md").unlink()

    result = evaluate_merge_readiness(tmp_path)

    assert result.decision == DECISION_BLOCKED
    assert "missing_artifact:14_test_run.md" in result.validation_errors


def test_summary_generation(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = evaluate_merge_readiness(tmp_path)

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["merge_readiness_status"] == "VALID"
    assert summary["merge_readiness_decision"] == result.decision
    assert summary["merge_readiness_artifact"] == result.artifact_path
    assert "merge_readiness" in summary["output_files"]



def test_invalid_decision_validates_false() -> None:
    report = """MERGE SUMMARY
- Summary.

ARTIFACT STATUS
- summary.json: present.

PATCH STATUS
- Patch status.

TEST STATUS
- Test status.

RISKS
- Risk.

MERGE DECISION
MAYBE

CONFIDENCE
High
"""

    parsed = parse_merge_readiness_sections(report)
    errors = validate_merge_readiness_report(report, parsed)

    assert "merge_decision_invalid" in errors


def test_report_with_command_string_validates_false() -> None:
    report = """MERGE SUMMARY
- Run python -m pytest before merge.

ARTIFACT STATUS
- summary.json: present.

PATCH STATUS
- Patch status.

TEST STATUS
- Test status.

RISKS
- Risk.

MERGE DECISION
BLOCKED

CONFIDENCE
High
"""

    parsed = parse_merge_readiness_sections(report)
    errors = validate_merge_readiness_report(report, parsed)

    assert "forbidden_content_present" in errors
