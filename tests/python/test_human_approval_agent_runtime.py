import json
from pathlib import Path

from agentic_network.human_approval_agent.runtime import (
    APPROVAL_TOKEN,
    DECISION_APPROVED,
    DECISION_DENIED,
    HUMAN_APPROVAL_OUTPUT_FILE,
    authorize_apply,
    parse_human_approval_sections,
)


def _write_run(
    run_dir: Path,
    *,
    final_decision: str = "Approved",
    patch_approval_decision: str = "Approved",
    patch_approval_validation_passed: bool = True,
    patch_approval_validation_errors: list[str] | None = None,
    patch_approval_validation_warnings: list[str] | None = None,
    patch_apply_status: str = "SKIPPED",
    merge_readiness_decision: str = "READY TO APPLY",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "final_decision": final_decision,
        "patch_approval_decision": patch_approval_decision,
        "patch_approval_validation_passed": patch_approval_validation_passed,
        "patch_approval_validation_errors": patch_approval_validation_errors or [],
        "patch_approval_validation_warnings": patch_approval_validation_warnings or [],
        "patch_apply_status": patch_apply_status,
        "merge_readiness_decision": merge_readiness_decision,
        "merge_readiness_validation_passed": True,
        "output_files": {},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "12_patch_approval.md").write_text(
        f"APPROVAL DECISION\n{patch_approval_decision}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "15_merge_readiness.md").write_text(
        f"MERGE DECISION\n{merge_readiness_decision}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )


def test_denied_by_default(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = authorize_apply(tmp_path)

    assert result.decision == DECISION_DENIED
    assert result.token_status == "missing"
    assert result.validation_passed is True
    assert (tmp_path / HUMAN_APPROVAL_OUTPUT_FILE).exists()
    assert "AUTHORIZATION DECISION\nDenied" in result.report


def test_denied_if_token_missing(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = authorize_apply(tmp_path, approve_apply=True)

    assert result.decision == DECISION_DENIED
    assert "Approval token is missing or invalid." in result.parsed_sections["reasoning"]


def test_denied_if_flag_missing(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = authorize_apply(tmp_path, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Explicit approve apply flag is missing." in result.parsed_sections["reasoning"]


def test_denied_if_token_wrong(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = authorize_apply(tmp_path, approve_apply=True, approval_token="wrong")

    assert result.decision == DECISION_DENIED
    assert result.token_status == "invalid"


def test_denied_if_final_not_approved(tmp_path: Path) -> None:
    _write_run(tmp_path, final_decision="Rejected")

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Final Reviewer did not approve the run." in result.parsed_sections["reasoning"]


def test_denied_if_patch_approval_not_approved(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_approval_decision="Rejected")

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Patch Approval Agent did not approve the patch set." in result.parsed_sections["reasoning"]


def test_denied_if_merge_readiness_blocked(tmp_path: Path) -> None:
    _write_run(tmp_path, merge_readiness_decision="BLOCKED")

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Merge readiness does not allow apply authorization." in result.parsed_sections["reasoning"]


def test_denied_if_patch_approval_has_errors(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_approval_validation_errors=["dangerous_command_present"])

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Patch Approval validation errors are present." in result.parsed_sections["reasoning"]


def test_denied_if_protected_path_findings_exist(tmp_path: Path) -> None:
    _write_run(tmp_path, patch_approval_validation_warnings=["protected_path_modified:training/datasets/data.jsonl"])

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "Protected path findings are present." in result.parsed_sections["reasoning"]


def test_approved_when_all_gates_pass(tmp_path: Path) -> None:
    _write_run(tmp_path)

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_APPROVED
    assert result.token_status == "valid"
    assert result.validation_passed is True
    parsed = parse_human_approval_sections(result.report)
    assert parsed["authorization_decision"] == DECISION_APPROVED
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["human_approval_decision"] == DECISION_APPROVED
    assert summary["human_approval_validation_passed"] is True
    assert summary["human_approval_token_status"] == "valid"
    assert "human_approval" in summary["output_files"]


def test_no_model_loading(monkeypatch, tmp_path: Path) -> None:
    _write_run(tmp_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("Human Approval Agent must not load a model")

    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", explode, raising=False)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", explode, raising=False)

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_APPROVED


def test_missing_required_artifact_is_denied_and_invalid(tmp_path: Path) -> None:
    _write_run(tmp_path)
    (tmp_path / "15_merge_readiness.md").unlink()

    result = authorize_apply(tmp_path, approve_apply=True, approval_token=APPROVAL_TOKEN)

    assert result.decision == DECISION_DENIED
    assert "missing_artifact:15_merge_readiness.md" in result.validation_errors
