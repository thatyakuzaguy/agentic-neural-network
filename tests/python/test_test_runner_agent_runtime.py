import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from agentic_network.test_runner_agent.runtime import (
    STATUS_FAILED,
    STATUS_NO_TESTS_DETECTED,
    STATUS_PASSED,
    STATUS_REJECTED,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    TEST_RUN_OUTPUT_FILE,
    detect_test_frameworks,
    run_tests_for_run,
    select_test_command,
    validate_allowed_command,
)


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps({"output_files": {}}), encoding="utf-8")
    (run_dir / "13_patch_apply.md").write_text(
        "TEST PREREQUISITE\nPatch apply was skipped.\n",
        encoding="utf-8",
    )


def test_no_run_tests_flag_skips_and_executes_nothing(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)

    def explode(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called without --run-tests")

    result = run_tests_for_run(run_dir, run_tests=False, subprocess_runner=explode)

    assert result.status == STATUS_SKIPPED
    assert result.commands_executed == []
    assert (run_dir / TEST_RUN_OUTPUT_FILE).exists()
    assert "TEST STATUS\nSkipped" in result.report
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["test_runner_status"] == STATUS_SKIPPED
    assert summary["test_runner_run_tests_flag"] is False


def test_no_framework_detected_does_not_execute(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)

    def explode(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called when no framework is detected")

    result = run_tests_for_run(run_dir, run_tests=True, subprocess_runner=explode)

    assert result.status == STATUS_NO_TESTS_DETECTED
    assert result.commands_selected == []
    assert result.commands_executed == []
    assert "TEST STATUS\nNo Tests Detected" in result.report


def test_detects_pytest_from_tests_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)

    frameworks = detect_test_frameworks(repo)

    assert frameworks == ["python-pytest"]
    assert select_test_command(frameworks) == ["python", "-m", "pytest"]


def test_selects_only_allowlisted_commands() -> None:
    assert validate_allowed_command(["python", "-m", "pytest"]) == []
    assert validate_allowed_command(["python", "-m", "unittest"]) == []
    assert validate_allowed_command(["npm", "test"]) == []
    assert validate_allowed_command(["npm", "run", "test"]) == []
    assert validate_allowed_command(["go", "test", "./..."]) == []
    assert validate_allowed_command(["cargo", "test"]) == []


def test_rejects_dangerous_command_attempts() -> None:
    errors = validate_allowed_command(["bash", "-lc", "rm -rf /mnt/d/AgenticEngineeringNetwork"])

    assert "dangerous_command_rejected" in errors
    assert "command_not_allowlisted" in errors


def test_rejects_c_drive_command_attempts() -> None:
    errors = validate_allowed_command(["python", "-m", "pytest", "C:\\tmp"])

    assert "forbidden_c_path_present" in errors
    assert "command_not_allowlisted" in errors


def test_run_tests_executes_allowlisted_pytest_with_shell_false(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    result = run_tests_for_run(run_dir, run_tests=True, subprocess_runner=fake_run)

    assert result.status == STATUS_PASSED
    assert result.exit_code == 0
    assert result.commands_selected == [["python", "-m", "pytest"]]
    assert result.commands_executed == [["python", "-m", "pytest"]]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == str(repo)
    assert calls[0][1]["timeout"] == 300
    assert "1 passed" in result.stdout_summary


def test_run_tests_records_failed_exit_code(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="1 failed\n")

    result = run_tests_for_run(run_dir, run_tests=True, subprocess_runner=fake_run)

    assert result.status == STATUS_FAILED
    assert result.exit_code == 1
    assert "1 failed" in result.stderr_summary


def test_timeout_handling_with_mocked_subprocess(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)

    def fake_run(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1, output="partial stdout", stderr="partial stderr")

    result = run_tests_for_run(run_dir, run_tests=True, timeout_seconds=1, subprocess_runner=fake_run)

    assert result.status == STATUS_TIMEOUT
    assert result.commands_executed == [["python", "-m", "pytest"]]
    assert "partial stdout" in result.stdout_summary
    assert "partial stderr" in result.stderr_summary


def test_invalid_timeout_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.PROJECT_ROOT", repo)

    result = run_tests_for_run(run_dir, run_tests=True, timeout_seconds=0)

    assert result.status == STATUS_REJECTED
    assert "timeout_seconds_invalid" in result.validation_errors
