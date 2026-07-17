from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import agentic_network.project_builder_orchestrator.runtime as orchestrator_runtime
from agentic_network.project_builder_orchestrator.run import main as orchestrator_main
from agentic_network.project_builder_orchestrator.runtime import run_end_to_end_project


def _allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_CREATION_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_SCAFFOLD_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_PATCH_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_SELF_HEALING_TARGETS", "1")
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    monkeypatch.setenv("ANN_PROJECT_PATCH_TOKEN", "local-test-token")


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_all(monkeypatch)
    return run_end_to_end_project(
        idea="Create a local CRM for small businesses",
        target_root=tmp_path / "targets",
        approval_token="local-test-token",
        max_features=2,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
    )


def test_idea_to_project_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.status == "NEEDS_TESTS"
    assert result.completion_quality == "REVIEW_REQUIRED"
    assert result.recommended_next_action == "add_project_tests"
    assert Path(result.project_root).is_dir()


def test_scaffold_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.scaffold_status == "APPLIED"
    assert (Path(result.project_root) / "README.md").is_file()


def test_implementation_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.implementation_status == "PLANNED"
    assert any(path.endswith("44_project_implementation_plan.json") for path in result.artifacts)


def test_patches_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert any("patch_001.diff" in path for path in result.artifacts)


def test_patch_apply_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.patch_status == "APPLIED"
    assert (Path(result.project_root) / "docs" / "features").is_dir()


def test_verification_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.verification_status in {"PASSED", "SKIPPED"}


def test_self_healing_status_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.self_healing_status in {"SKIPPED", "REPAIRED", "FAILED_PERMANENTLY"}


def test_consensus_updated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.consensus["consensus_decision"] == "PROJECT_NEEDS_TESTS"
    assert result.consensus["completion_quality"] == "REVIEW_REQUIRED"
    assert any(path.endswith("63_end_to_end_consensus.json") for path in result.artifacts)


def test_action_plan_updated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.next_action == "add_project_tests"
    assert result.recommended_next_action == "add_project_tests"
    assert any(path.endswith("64_end_to_end_action_plan.json") for path in result.artifacts)


def test_passed_commands_complete_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)

    class Verification:
        status = "PASSED"
        commands_selected = [["python", "-m", "pytest", "tests/python", "-q"]]
        commands_executed = [["python", "-m", "pytest", "tests/python", "-q"]]
        stdout_artifacts = ["stdout.log"]
        stderr_artifacts = ["stderr.log"]
        artifacts: list[str] = []

    monkeypatch.setattr(orchestrator_runtime, "run_project_verification", lambda *_a, **_k: Verification())

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
    )

    assert result.status == "COMPLETED_VERIFIED"
    assert result.completion_quality == "VERIFIED"
    assert result.verification_evidence["evidence_level"] == "STRONG"
    assert result.recommended_next_action == "completed_verified"


def test_skipped_after_patches_is_not_completed_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.patch_status == "APPLIED"
    assert result.verification_status == "SKIPPED"
    assert result.status != "COMPLETED_VERIFIED"
    assert result.verification_evidence["evidence_level"] == "NONE"


def test_generate_tests_if_missing_false_remains_needs_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch)

    assert result.status == "NEEDS_TESTS"
    assert result.recommended_next_action == "add_project_tests"


def test_generate_tests_if_missing_true_generates_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_all(monkeypatch)
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_GENERATION_TARGETS", "1")

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
        generate_tests_if_missing=True,
    )

    assert result.status == "COMPLETED_VERIFIED"
    assert result.completion_quality == "VERIFIED"
    assert any(path.endswith("67_project_test_generation_plan.md") for path in result.artifacts)
    assert any("test_patch_001.diff" in path for path in result.artifacts)
    assert result.verification_evidence["commands_executed"]


def test_generated_tests_are_not_applied_without_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_all(monkeypatch)
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_GENERATION_TARGETS", "1")

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="wrong-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
        generate_tests_if_missing=True,
    )

    assert result.status == "BLOCKED"
    assert not (Path(result.project_root) / "tests" / "python" / "test_project_contract.py").exists()


def test_generated_tests_do_not_verify_without_confirm_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_all(monkeypatch)
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_GENERATION_TARGETS", "1")

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=False,
        generate_tests_if_missing=True,
    )

    assert result.status == "BLOCKED"
    assert result.next_action == "confirm_project_tests"
    assert result.verification_evidence["commands_executed"] == []


def test_failing_generated_tests_trigger_self_healing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_all(monkeypatch)
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_GENERATION_TARGETS", "1")

    class SkippedVerification:
        status = "SKIPPED"
        commands_selected: list[list[str]] = []
        commands_executed: list[list[str]] = []
        stdout_artifacts: list[str] = []
        stderr_artifacts: list[str] = []
        artifacts: list[str] = []

    class FailedVerification:
        status = "FAILED"
        commands_selected = [["python", "-m", "pytest", "tests/python", "-q"]]
        commands_executed = [["python", "-m", "pytest", "tests/python", "-q"]]
        stdout_artifacts: list[str] = []
        stderr_artifacts: list[str] = []
        artifacts: list[str] = []

    class SelfHealing:
        status = "FAILED_PERMANENTLY"
        verification_status = "FAILED"
        artifacts: list[str] = []
        validation_errors: list[str] = []
        next_action = "human_escalation_required"

    calls: list[int] = []

    def fake_verify(*_args: object, **_kwargs: object) -> object:
        calls.append(1)
        return SkippedVerification() if len(calls) == 1 else FailedVerification()

    monkeypatch.setattr(orchestrator_runtime, "run_project_verification", fake_verify)
    monkeypatch.setattr(orchestrator_runtime, "run_project_self_healing", lambda *_a, **_k: SelfHealing())

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
        generate_tests_if_missing=True,
    )

    assert result.status == "FAILED_PERMANENTLY"
    assert result.self_healing_status == "FAILED_PERMANENTLY"
    assert len(calls) == 2


def test_progress_json_includes_verification_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)
    progress_path = next(Path(path) for path in result.artifacts if path.endswith("62_end_to_end_progress.json"))
    payload = json.loads(progress_path.read_text(encoding="utf-8"))

    assert payload["verification_evidence"]["evidence_level"] == "NONE"
    assert payload["completion_quality"] == "REVIEW_REQUIRED"


def test_summary_explains_unverified_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)
    summary_path = next(Path(path) for path in result.artifacts if path.endswith("65_end_to_end_summary.md"))
    summary = summary_path.read_text(encoding="utf-8")

    assert "Project generated but not fully verified" in summary
    assert "Recommended next action: add_project_tests" in summary


def test_action_plan_recommends_tests_when_no_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)
    action_path = next(Path(path) for path in result.artifacts if path.endswith("64_end_to_end_action_plan.json"))
    action = json.loads(action_path.read_text(encoding="utf-8"))

    assert action["recommended_next_action"] == "add_project_tests"
    assert action["blocked"] is True


def test_verification_evidence_artifacts_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert any(path.endswith("66_end_to_end_verification_evidence.json") for path in result.artifacts)
    assert any(path.endswith("66_end_to_end_verification_evidence.md") for path in result.artifacts)


def test_failed_then_repaired_completes_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)

    class Verification:
        status = "FAILED"
        commands_selected = [["python", "-m", "pytest", "tests/python", "-q"]]
        commands_executed = [["python", "-m", "pytest", "tests/python", "-q"]]
        stdout_artifacts = ["stdout.log"]
        stderr_artifacts = ["stderr.log"]
        artifacts: list[str] = []

    class SelfHealing:
        status = "REPAIRED"
        verification_status = "PASSED"
        artifacts: list[str] = []
        validation_errors: list[str] = []
        next_action = "review_repaired_project"

    monkeypatch.setattr(orchestrator_runtime, "run_project_verification", lambda *_a, **_k: Verification())
    monkeypatch.setattr(orchestrator_runtime, "run_project_self_healing", lambda *_a, **_k: SelfHealing())

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
    )

    assert result.status == "COMPLETED_VERIFIED"
    assert result.completion_quality == "VERIFIED"
    assert result.self_healing_status == "REPAIRED"


def test_max_retries_respected_failed_permanently_possible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_all(monkeypatch)

    class Verification:
        status = "FAILED"
        commands_selected = [["python", "-m", "pytest", "tests/python", "-q"]]
        commands_executed = [["python", "-m", "pytest", "tests/python", "-q"]]
        stdout_artifacts: list[str] = []
        stderr_artifacts: list[str] = []
        artifacts: list[str] = []

    class SelfHealing:
        status = "FAILED_PERMANENTLY"
        artifacts: list[str] = []
        validation_errors: list[str] = []
        next_action = "human_escalation_required"

    monkeypatch.setattr(orchestrator_runtime, "run_project_verification", lambda *_a, **_k: Verification())
    calls: list[int] = []

    def fake_self_healing(*_args: object, **kwargs: object) -> SelfHealing:
        calls.append(int(kwargs["max_attempts"]))
        return SelfHealing()

    monkeypatch.setattr(orchestrator_runtime, "run_project_self_healing", fake_self_healing)

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=2,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
    )

    assert result.status == "FAILED_PERMANENTLY"
    assert calls == [2]


def test_ann_blocked() -> None:
    result = run_end_to_end_project(
        "Create a local CRM",
        "D:\\AgenticEngineeringNetwork",
        approval_token="local-test-token",
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
    )

    assert result.status == "BLOCKED"


def test_git_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    target = tmp_path / ".git"
    target.mkdir()

    result = run_end_to_end_project("Create a CRM", target, approval_token="local-test-token")

    assert result.status == "BLOCKED"


def test_c_drive_blocked() -> None:
    result = run_end_to_end_project("Create a CRM", "C:\\ANNProjects", approval_token="local-test-token")

    assert result.status == "BLOCKED"


def test_mnt_c_blocked() -> None:
    result = run_end_to_end_project("Create a CRM", "/mnt/c/ANNProjects", approval_token="local-test-token")

    assert result.status == "BLOCKED"


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("End-to-end builder must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert _run(tmp_path, monkeypatch).status == "NEEDS_TESTS"


def test_no_installs_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch)

    assert not (Path(result.project_root) / "node_modules").exists()
    assert not (Path(result.project_root) / ".venv").exists()


def test_desktop_still_working() -> None:
    from agentic_network.desktop_app.navigation import navigation_labels
    from agentic_network.desktop_app.views.project_builder_orchestrator_view import (
        PROJECT_BUILDER_ORCHESTRATOR_MESSAGE,
    )

    assert "End-to-End Builder" in navigation_labels()
    assert "Completion quality" in PROJECT_BUILDER_ORCHESTRATOR_MESSAGE
    assert "Unverified warning" in PROJECT_BUILDER_ORCHESTRATOR_MESSAGE


def test_no_touches_ann(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = Path("D:\\AgenticEngineeringNetwork\\README.md").read_text(encoding="utf-8")

    _run(tmp_path, monkeypatch)

    assert Path("D:\\AgenticEngineeringNetwork\\README.md").read_text(encoding="utf-8") == before


def test_cli_run_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _allow_all(monkeypatch)
    exit_code = orchestrator_main(
        [
            "--idea",
            "Create a local CRM",
            "--target-root",
            str(tmp_path / "targets"),
            "--approval-token",
            "local-test-token",
            "--max-features",
            "1",
            "--max-retries",
            "1",
            "--confirm-create",
            "--confirm-apply",
            "--confirm-tests",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "NEEDS_TESTS"
