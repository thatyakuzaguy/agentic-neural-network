from pathlib import Path

from agentic_network.revision_agent.runtime import (
    CODE_REVISED_OUTPUT_FILE,
    REVISION_SUMMARY_OUTPUT_FILE,
    SECURITY_REVISED_OUTPUT_FILE,
    TEST_REVISED_OUTPUT_FILE,
    apply_revisions,
    parse_revision_sections,
    validate_revision_summary,
)


def _write_base_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "03_code.md").write_text(
        "FILES TO MODIFY\n"
        "- Candidate: password reset request handling module.\n\n"
        "CODE CHANGES\n"
        "- Add request tracking for repeated password reset attempts.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "04_tests.md").write_text(
        "TEST SCENARIOS\n"
        "- Verify excessive reset attempts are blocked.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "05_security.md").write_text(
        "SECURITY FINDINGS\n"
        "- Password reset abuse should be mitigated.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "06_review.md").write_text(
        "CONSISTENCY CHECK\n"
        "- Artifacts are mostly aligned.\n\n"
        "IMPLEMENTATION RISKS\n"
        "- Missing retry window.\n"
        "- Missing escalation thresholds.\n"
        "- Missing identifier rotation handling.\n\n"
        "TEST COVERAGE GAPS\n"
        "- Missing retry window tests.\n"
        "- Missing escalation threshold tests.\n\n"
        "SECURITY GAPS\n"
        "- Missing identifier rotation handling.\n\n"
        "APPROVAL STATUS\n"
        "Needs Fixes\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "07_fix_plan.md").write_text(
        "FIX SUMMARY\n"
        "- Add retry windows.\n"
        "- Add escalation thresholds.\n"
        "- Add identifier tracking.\n\n"
        "IMPLEMENTATION FIXES\n"
        "- Add retry windows.\n"
        "- Add escalation thresholds.\n"
        "- Add identifier tracking.\n\n"
        "TEST FIXES\n"
        "- Add retry window coverage.\n"
        "- Add escalation threshold coverage.\n\n"
        "SECURITY FIXES\n"
        "- Add identifier tracking.\n\n"
        "READY FOR RE-REVIEW\n"
        "Yes\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )


def test_apply_revisions_generates_revised_artifacts(tmp_path: Path) -> None:
    _write_base_run(tmp_path)

    result = apply_revisions(tmp_path)

    assert result.validation_errors == []
    assert result.validation_passed is True
    assert result.artifacts_generated == [
        CODE_REVISED_OUTPUT_FILE,
        TEST_REVISED_OUTPUT_FILE,
        SECURITY_REVISED_OUTPUT_FILE,
        REVISION_SUMMARY_OUTPUT_FILE,
    ]
    for filename in result.artifacts_generated:
        assert (tmp_path / filename).exists(), filename
    parsed = parse_revision_sections(result.revision_summary)
    assert parsed["confidence"] == "High"
    assert parsed["code_changes"]
    assert parsed["test_changes"]
    assert parsed["security_changes"]


def test_review_and_fixer_gaps_are_incorporated(tmp_path: Path) -> None:
    _write_base_run(tmp_path)

    result = apply_revisions(tmp_path)

    code = (tmp_path / CODE_REVISED_OUTPUT_FILE).read_text(encoding="utf-8")
    tests = (tmp_path / TEST_REVISED_OUTPUT_FILE).read_text(encoding="utf-8")
    security = (tmp_path / SECURITY_REVISED_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "Add configurable retry windows." in code
    assert "Add escalation thresholds for repeated or severe cases." in code
    assert "Account for identifier rotation handling." in code
    assert "Track relevant request identifiers consistently across the planned flow." in code
    assert "Add configurable retry windows." in tests
    assert "Add escalation thresholds for repeated or severe cases." in tests
    assert "Account for identifier rotation handling." in security
    assert "Track relevant request identifiers consistently across the planned flow." in security
    assert result.warnings == []


def test_validate_revision_summary_rejects_code_and_diff_markers() -> None:
    invalid = """CODE CHANGES
- def build_limit():

TEST CHANGES
- import pytest

SECURITY CHANGES
- +++ patched file

REVISION SUMMARY
- ```python

CONFIDENCE
High"""
    parsed = parse_revision_sections(invalid)

    errors = validate_revision_summary(invalid, parsed)

    assert "definition_present" in errors
    assert "import_present" in errors
    assert "patch_markers_present" in errors
    assert "code_fence_present" in errors


def test_revision_agent_has_no_model_runtime_dependency(monkeypatch, tmp_path: Path) -> None:
    _write_base_run(tmp_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("Revision Agent must not load a model")

    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", explode, raising=False)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", explode, raising=False)

    result = apply_revisions(tmp_path)

    assert result.validation_passed is True
