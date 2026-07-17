from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

import agentic_network.project_test_runner_agent.runtime as test_runner_runtime
from agentic_network.project_test_runner_agent.run import main as verification_main
from agentic_network.project_test_runner_agent.runtime import (
    detect_project_test_commands,
    run_project_verification,
)


def _project_root(tmp_path: Path, *, with_tests: bool = True, test_body: str = "def test_ok():\n    assert True\n") -> Path:
    root = tmp_path / "generated_project"
    root.mkdir(parents=True)
    if with_tests:
        tests = root / "tests" / "python"
        tests.mkdir(parents=True)
        (tests / "test_sample.py").write_text(test_body, encoding="utf-8")
    return root


def _allow_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS", "1")


def test_without_confirm_run_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tests must not execute without confirm_run.")

    monkeypatch.setattr(subprocess, "run", fail_run)

    result = run_project_verification(root, confirm_run=False)

    assert result.status == "SKIPPED"
    assert result.commands_executed == []


def test_python_pytest_command_detected_when_tests_python_exists(tmp_path: Path) -> None:
    root = _project_root(tmp_path)

    commands, warnings = detect_project_test_commands(root)

    assert ["python", "-m", "pytest", "tests/python", "-q"] in commands
    assert warnings == []


def test_no_commands_selected_when_no_tests_exist(tmp_path: Path) -> None:
    root = _project_root(tmp_path, with_tests=False)

    commands, _warnings = detect_project_test_commands(root)

    assert commands == []


def test_captures_stdout_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path, test_body='def test_ok():\n    print("hello stdout")\n    assert True\n')

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "PASSED"
    assert "1 passed" in Path(result.stdout_artifacts[0]).read_text(encoding="utf-8")


def test_captures_stderr_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    class Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = "hello stderr\n"

    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: Completed())

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "PASSED"
    assert "hello stderr" in Path(result.stderr_artifacts[0]).read_text(encoding="utf-8")


def test_failed_tests_produce_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path, test_body="def test_fail():\n    assert False\n")

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "FAILED"
    assert result.retry_recommended is True


def test_passed_tests_produce_passed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "PASSED"
    assert result.retry_recommended is False


def test_timeout_produces_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path, test_body="import time\n\ndef test_slow():\n    time.sleep(2)\n")

    result = run_project_verification(root, timeout_seconds=1, confirm_run=True)

    assert result.status == "TIMEOUT"


def test_mnt_c_blocked() -> None:
    result = run_project_verification("/mnt/c/ANNProjects/crm", confirm_run=True)

    assert result.status == "BLOCKED"
    assert any("blocked" in error.lower() for error in result.validation_errors)


def test_c_drive_blocked() -> None:
    result = run_project_verification("C:\\ANNProjects\\crm", confirm_run=True)

    assert result.status == "BLOCKED"


def test_path_traversal_blocked(tmp_path: Path) -> None:
    result = run_project_verification(tmp_path / "safe" / ".." / "escape", confirm_run=True)

    assert result.status == "BLOCKED"
    assert any("traversal" in error.lower() for error in result.validation_errors)


def test_git_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = tmp_path / ".git"
    root.mkdir()

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "BLOCKED"


def test_no_npm_install_ever(tmp_path: Path) -> None:
    root = _project_root(tmp_path, with_tests=False)
    (root / "package.json").write_text('{"scripts":{"test":"echo ok"}}', encoding="utf-8")

    commands, warnings = detect_project_test_commands(root)

    assert not any("install" in " ".join(command) for command in commands)
    assert any("npm test skipped" in warning for warning in warnings)


def test_npm_test_skipped_if_node_modules_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path, with_tests=False)
    (root / "package.json").write_text('{"scripts":{"test":"echo ok"}}', encoding="utf-8")

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "SKIPPED"
    assert any("node_modules is missing" in warning for warning in result.validation_warnings)


def test_does_not_use_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)
    original_run = subprocess.run

    def guarded_run(*args: object, **kwargs: object):
        assert kwargs.get("shell") is False
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)

    assert run_project_verification(root, confirm_run=True).status == "PASSED"


def test_generates_47_project_verification_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_verification(root, confirm_run=True)

    assert any(path.endswith("47_project_verification.md") for path in result.artifacts)
    assert any(path.endswith("47_project_verification.json") for path in result.artifacts)


def test_generates_retry_context_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path, test_body="def test_fail():\n    assert False\n")

    result = run_project_verification(root, confirm_run=True)

    assert result.retry_context_artifact is not None
    assert Path(result.retry_context_artifact).is_file()
    assert any(path.endswith("51_project_failure_analysis.md") for path in result.artifacts)
    assert (Path(result.retry_context_artifact).parent / "52_project_retry_recommendation.md").is_file()


def test_does_not_modify_ann_repo() -> None:
    readme = test_runner_runtime.REPO_ROOT / "README.md"
    before = readme.read_text(encoding="utf-8")

    result = run_project_verification(test_runner_runtime.REPO_ROOT, confirm_run=True)

    assert result.status == "BLOCKED"
    assert readme.read_text(encoding="utf-8") == before


def test_repo_child_generated_project_verification_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    repo = tmp_path / "AgenticEngineeringNetwork"
    root = repo / "outputs" / "autonomous_capability_projects" / "crm" / "crm"
    tests = root / "tests" / "python"
    tests.mkdir(parents=True)
    (tests / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(test_runner_runtime, "REPO_ROOT", repo.resolve())

    result = run_project_verification(root, confirm_run=True)

    assert result.status == "PASSED"
    assert result.commands_executed


def test_does_not_call_patch_apply_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    import agentic_network.patch_apply_agent.runtime as patch_apply_runtime

    monkeypatch.setattr(
        patch_apply_runtime,
        "apply_patch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Patch Apply core called.")),
        raising=False,
    )

    assert run_project_verification(root, confirm_run=True).status == "PASSED"


def test_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Project Test Runner must not use network.")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    root = _project_root(tmp_path)

    assert run_project_verification(root, confirm_run=True).status == "PASSED"


def test_cli_run_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _allow_temp(monkeypatch)
    root = _project_root(tmp_path)

    exit_code = verification_main(["--project-root", str(root), "--confirm-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASSED"
