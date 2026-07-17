import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_network.autonomous_loop.runtime import (
    STATUS_BLOCKED,
    STATUS_FAILED_APPROVAL,
    STATUS_FAILED_TESTS,
    STATUS_FAILED_PERMANENTLY,
    STATUS_PASSED,
    STATUS_SKIPPED,
    run_autonomous_engineering_loop,
)
from agentic_network.handoff.runtime import build_handoff_bundle


@pytest.fixture(autouse=True)
def _allow_tmp_run_dirs(monkeypatch):
    class Policy:
        def is_path_blocked(self, path: Path) -> bool:
            return False

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.load_filesystem_policy", lambda: Policy())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_dir(tmp_path: Path, *, patch_apply_status: str = "APPLIED", test_status: str = "FAILED") -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write(run_dir / "summary.json", json.dumps({
        "final_decision": "Approved",
        "patch_apply_status": patch_apply_status,
        "test_runner_status": test_status,
        "output_files": {},
    }, indent=2))
    _write(run_dir / "08_final_review.md", "FINAL DECISION\nApproved\n")
    _write(run_dir / "11_execution_plan.md", "EXECUTION SUMMARY\n- Safe.\n")
    _write(run_dir / "12_patch_approval.md", "APPROVAL DECISION\nApproved\n")
    _write(run_dir / "13_patch_apply.md", f"APPLY STATUS\n{patch_apply_status}\n")
    _write(run_dir / "14_test_run.md", f"TEST STATUS\n{test_status}\n")
    return run_dir


def _fake_healing(run_dir: Path, *, status: str = "RETRY_PATCH_GENERATED"):
    retry = run_dir / "19_retry_patch_001.diff"
    if status == "RETRY_PATCH_GENERATED":
        _write(
            retry,
            "--- a/agentic_network/config.py\n"
            "+++ b/agentic_network/config.py\n"
            "@@ -1,1 +1,2 @@\n"
            " APP_NAME = 'ANN'\n"
            "+PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600\n",
        )
    _write(run_dir / "17_failure_analysis.md", "FAILURE SUMMARY\n- Failed.\n")
    _write(run_dir / "18_root_cause.md", "ROOT CAUSE SUMMARY\n- Missing constant.\n")
    _write(run_dir / "21_self_healing.md", f"ATTEMPT STATUS\n- {status}\n")
    return SimpleNamespace(
        status=status,
        retry_patch_path=str(retry) if status == "RETRY_PATCH_GENERATED" else "",
        validation_errors=[] if status == "RETRY_PATCH_GENERATED" else ["retry_patch_not_generated"],
        validation_warnings=[],
    )


def _fake_quality(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "29_retry_patch_quality.md")
    _write(artifact, "PATCH\nretry_patch_001.diff\nQUALITY\nIMPLEMENTATION_READY\n")
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


def _fake_human(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "31_retry_human_approval.md")
    _write(artifact, "AUTHORIZATION DECISION\nApproved\n")
    return SimpleNamespace(
        decision="Approved",
        validation_passed=True,
        validation_errors=[],
        warnings=[],
        artifact_path=str(artifact),
    )


def _fake_apply(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("output_artifact", "32_retry_patch_apply.md")
    _write(artifact, "APPLY STATUS\nApplied\n")
    return SimpleNamespace(
        status="APPLIED",
        validation_errors=[],
        artifact_path=str(artifact),
        files_modified=["agentic_network/config.py"],
    )


def _fake_test(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "33_retry_test_run.md")
    _write(artifact, "TEST STATUS\nPassed\n")
    return SimpleNamespace(
        status="PASSED",
        artifact_path=str(artifact),
        stdout_summary="1 passed",
        stderr_summary="",
        commands_executed=["pytest tests/python -q"],
    )


def _fake_failed_test(run_dir: Path, **kwargs):
    artifact = run_dir / kwargs.get("artifact_name", "33_retry_test_run.md")
    _write(artifact, "TEST STATUS\nFailed\nAssertionError: expected 2 got 1\n")
    return SimpleNamespace(
        status="FAILED",
        artifact_path=str(artifact),
        stdout_summary="tests/python/test_config.py::test_rate_limit FAILED",
        stderr_summary="AssertionError: expected 2 got 1",
        commands_executed=["pytest tests/python -q"],
    )


def test_skipped_when_run_tests_false(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    result = run_autonomous_engineering_loop(run_dir, run_tests=False)

    assert result.status == STATUS_SKIPPED
    assert result.attempts == []
    assert (run_dir / "27_autonomous_loop.md").exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["autonomous_loop_status"] == STATUS_SKIPPED
    assert "run_tests_flag_missing" in summary["autonomous_loop_validation_warnings"]
    assert summary["autonomous_loop_retry_failure_detected"] is False
    assert not list(run_dir.glob("34_retry_test_failure_analysis_attempt_*.md"))


def test_blocked_when_no_applied_patch_exists(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, patch_apply_status="SKIPPED")
    marker = tmp_path / "repo_file.py"
    marker.write_text("VALUE = 1\n", encoding="utf-8")

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_BLOCKED
    assert "patch_apply_must_happen_first" in result.validation_errors
    assert marker.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_passed_when_tests_already_passed(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, test_status="PASSED")

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_PASSED
    assert result.attempts == []


def test_failed_permanently_when_no_retry_patch_generated(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.run_self_healing",
        lambda run_dir, max_attempts: _fake_healing(run_dir, status="FAILED_ANALYSIS"),
    )

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_FAILED_PERMANENTLY
    assert result.attempts[0].self_healing_status == "FAILED_ANALYSIS"
    assert (run_dir / "28_autonomous_attempt_001.md").exists()


def test_retry_patch_must_pass_approval_before_apply(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_quality",
        lambda run_dir, **kwargs: calls.append("quality") or _fake_quality(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_approval",
        lambda run_dir, **kwargs: calls.append("approval") or _fake_approval(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.authorize_apply",
        lambda run_dir, **kwargs: calls.append("human") or _fake_human(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.apply_approved_patches",
        lambda run_dir, **kwargs: calls.append("apply") or _fake_apply(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.run_tests_for_run",
        lambda run_dir, *args, **kwargs: calls.append("test") or _fake_test(run_dir, **kwargs),
    )

    result = run_autonomous_engineering_loop(
        run_dir,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
        run_tests=True,
    )

    assert result.status == STATUS_PASSED
    assert calls == ["quality", "approval", "human", "apply", "test"]


def test_retry_flow_uses_dedicated_artifacts_and_retry_patch_dir(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    seen: dict[str, dict] = {}

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_quality",
        lambda run_dir, **kwargs: seen.setdefault("quality", kwargs) and _fake_quality(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_approval",
        lambda run_dir, **kwargs: seen.setdefault("approval", kwargs) and _fake_approval(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.authorize_apply",
        lambda run_dir, **kwargs: seen.setdefault("human", kwargs) and _fake_human(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.apply_approved_patches",
        lambda run_dir, **kwargs: seen.setdefault("apply", kwargs) and _fake_apply(run_dir, **kwargs),
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.run_tests_for_run",
        lambda run_dir, *args, **kwargs: seen.setdefault("test", kwargs) and _fake_test(run_dir, **kwargs),
    )

    result = run_autonomous_engineering_loop(
        run_dir,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
        run_tests=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert result.status == STATUS_PASSED
    assert seen["quality"]["patch_dir"] == "retry_patches"
    assert seen["quality"]["artifact_name"] == "29_retry_patch_quality.md"
    assert seen["approval"]["patch_dir"] == "retry_patches"
    assert seen["approval"]["artifact_name"] == "30_retry_patch_approval.md"
    assert seen["human"]["artifact_name"] == "31_retry_human_approval.md"
    assert seen["apply"]["patch_dir"] == "retry_patches"
    assert seen["apply"]["output_artifact"] == "32_retry_patch_apply.md"
    assert seen["test"]["artifact_name"] == "33_retry_test_run.md"
    assert (run_dir / "retry_patches" / "retry_patch_001.diff").exists()
    assert (run_dir / "29_retry_patch_quality.md").exists()
    assert (run_dir / "30_retry_patch_approval.md").exists()
    assert (run_dir / "31_retry_human_approval.md").exists()
    assert (run_dir / "32_retry_patch_apply.md").exists()
    assert (run_dir / "33_retry_test_run.md").exists()
    assert summary["autonomous_loop_retry_quality_decision"] == "IMPLEMENTATION_READY"
    assert summary["autonomous_loop_retry_approval_decision"] == "Approved"
    assert summary["autonomous_loop_retry_apply_status"] == "APPLIED"
    assert summary["autonomous_loop_retry_test_status"] == "PASSED"
    assert summary["autonomous_loop_retry_failure_detected"] is False
    assert summary["autonomous_loop_attempt_artifacts"] == [str(run_dir / "28_autonomous_attempt_001.md")]
    assert not list(run_dir.glob("34_retry_test_failure_analysis_attempt_*.md"))


def test_retry_apply_blocked_without_valid_approval_token(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_quality", _fake_quality)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_approval", _fake_approval)

    def denied_human(run_dir: Path, **kwargs):
        artifact = run_dir / kwargs.get("artifact_name", "31_retry_human_approval.md")
        _write(artifact, "AUTHORIZATION DECISION\nDenied\n")
        return SimpleNamespace(
            decision="Denied",
            validation_passed=True,
            validation_errors=[],
            warnings=[],
            artifact_path=str(artifact),
        )

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.authorize_apply", denied_human)

    def fail_apply(*_args, **_kwargs):
        raise AssertionError("Retry Patch Apply must not run after denied human approval")

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.apply_approved_patches", fail_apply)

    result = run_autonomous_engineering_loop(
        run_dir,
        approve_patches=True,
        approval_token="wrong-token",
        run_tests=True,
    )

    assert result.status == STATUS_FAILED_APPROVAL
    assert result.attempts[0].patch_apply_status == ""
    assert (run_dir / "31_retry_human_approval.md").exists()


def test_no_human_approval_means_apply_blocked(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_quality",
        _fake_quality,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_approval",
        _fake_approval,
    )

    def fail_apply(*_args, **_kwargs):
        raise AssertionError("Patch Apply must not run without approval mode")

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.apply_approved_patches", fail_apply)

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)

    assert result.status == STATUS_FAILED_APPROVAL
    assert result.attempts[0].patch_approval_decision == "Approved"
    assert "approve_patches_required_for_retry_apply" in result.attempts[0].validation_errors
    assert not list(run_dir.glob("34_retry_test_failure_analysis_attempt_*.md"))


def test_max_attempts_respected(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    counter = {"value": 0}

    def healing(run_dir: Path, max_attempts: int):
        counter["value"] += 1
        retry = run_dir / f"19_retry_patch_{counter['value']:03d}.diff"
        _write(
            retry,
            "--- a/agentic_network/config.py\n"
            "+++ b/agentic_network/config.py\n"
            "@@ -1,1 +1,2 @@\n"
            " APP_NAME = 'ANN'\n"
            f"+PASSWORD_RESET_RETRY_{counter['value']} = {counter['value']}\n",
        )
        return SimpleNamespace(status="RETRY_PATCH_GENERATED", retry_patch_path=str(retry), validation_errors=[], validation_warnings=[])

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", healing)
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_quality",
        _fake_quality,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_approval",
        _fake_approval,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.authorize_apply",
        _fake_human,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.apply_approved_patches",
        _fake_apply,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.run_tests_for_run",
        _fake_failed_test,
    )

    result = run_autonomous_engineering_loop(
        run_dir,
        max_attempts=2,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
        run_tests=True,
    )

    assert result.status == STATUS_FAILED_PERMANENTLY
    assert len(result.attempts) == 2
    assert counter["value"] == 2
    assert result.attempts[0].status == STATUS_FAILED_TESTS
    assert result.attempts[1].status == STATUS_FAILED_TESTS
    assert (run_dir / "34_retry_test_failure_analysis_attempt_001.md").exists()
    assert (run_dir / "34_retry_test_failure_analysis_attempt_002.md").exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["autonomous_loop_retry_failure_attempt"] == 2
    assert summary["autonomous_loop_retry_failure_next_action"] == "max_attempts_exhausted"


def test_retry_test_failure_loop_continues_after_failed_retry_tests(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    test_statuses = ["FAILED", "PASSED"]
    healing_counter = {"value": 0}

    def healing(run_dir: Path, max_attempts: int):
        healing_counter["value"] += 1
        retry = run_dir / f"19_retry_patch_{healing_counter['value']:03d}.diff"
        _write(
            retry,
            "--- a/agentic_network/config.py\n"
            "+++ b/agentic_network/config.py\n"
            "@@ -1,1 +1,2 @@\n"
            " APP_NAME = 'ANN'\n"
            f"+RETRY_FIX_{healing_counter['value']} = True\n",
        )
        return SimpleNamespace(
            status="RETRY_PATCH_GENERATED",
            retry_patch_path=str(retry),
            validation_errors=[],
            validation_warnings=[],
        )

    def tests(run_dir: Path, **kwargs):
        status = test_statuses.pop(0)
        if status == "FAILED":
            return _fake_failed_test(run_dir, **kwargs)
        return _fake_test(run_dir, **kwargs)

    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", healing)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_quality", _fake_quality)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_approval", _fake_approval)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.authorize_apply", _fake_human)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.apply_approved_patches", _fake_apply)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_tests_for_run", tests)

    result = run_autonomous_engineering_loop(
        run_dir,
        max_attempts=2,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
        run_tests=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert result.status == STATUS_PASSED
    assert len(result.attempts) == 2
    assert result.attempts[0].status == STATUS_FAILED_TESTS
    assert result.attempts[1].status == STATUS_PASSED
    assert healing_counter["value"] == 2
    analysis = run_dir / "34_retry_test_failure_analysis_attempt_001.md"
    plan = run_dir / "35_retry_failure_followup_plan_attempt_001.md"
    loop = run_dir / "36_retry_failure_loop_attempt_001.md"
    assert analysis.exists()
    assert plan.exists()
    assert loop.exists()
    assert (run_dir / "37_failure_context_attempt_001.json").exists()
    assert (run_dir / "37_failure_context_attempt_001.md").exists()
    assert "AssertionError: expected 2 got 1" in analysis.read_text(encoding="utf-8")
    assert "pytest tests/python -q" in analysis.read_text(encoding="utf-8")
    assert summary["autonomous_loop_retry_failure_detected"] is True
    assert summary["autonomous_loop_retry_failure_attempt"] == 1
    assert summary["autonomous_loop_retry_failure_next_action"] == "resolved"


def test_retry_failure_artifacts_are_included_in_handoff(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_quality", _fake_quality)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.evaluate_patch_approval", _fake_approval)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.authorize_apply", _fake_human)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.apply_approved_patches", _fake_apply)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_tests_for_run", _fake_failed_test)

    run_autonomous_engineering_loop(
        run_dir,
        max_attempts=1,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
        run_tests=True,
    )
    handoff = build_handoff_bundle(run_dir, task="Fix retry failure loop")

    assert "34_retry_test_failure_analysis_attempt_001.md" in handoff.included_artifacts
    assert "35_retry_failure_followup_plan_attempt_001.md" in handoff.included_artifacts
    assert "36_retry_failure_loop_attempt_001.md" in handoff.included_artifacts
    assert "37_failure_context_attempt_001.json" in handoff.included_artifacts
    assert "37_failure_context_attempt_001.md" in handoff.included_artifacts


def test_summary_updated_and_artifacts_written(tmp_path: Path, monkeypatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr("agentic_network.autonomous_loop.runtime.run_self_healing", lambda run_dir, max_attempts: _fake_healing(run_dir))
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_quality",
        _fake_quality,
    )
    monkeypatch.setattr(
        "agentic_network.autonomous_loop.runtime.evaluate_patch_approval",
        _fake_approval,
    )

    result = run_autonomous_engineering_loop(run_dir, run_tests=True)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert result.status == STATUS_FAILED_APPROVAL
    assert summary["autonomous_loop_enabled"] is True
    assert summary["autonomous_loop_attempts"] == 1
    assert "autonomous_loop" in summary["output_files"]
    assert (run_dir / "27_autonomous_loop.md").exists()
    assert (run_dir / "28_autonomous_attempt_001.md").exists()
    assert sorted(path.name for path in (run_dir / "retry_patches").glob("*.diff")) == ["retry_patch_001.diff"]
