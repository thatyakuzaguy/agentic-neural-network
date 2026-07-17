from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

import agentic_network.project_self_healing_agent.runtime as self_healing_runtime
from agentic_network.project_self_healing_agent.run import main as self_healing_main
from agentic_network.project_self_healing_agent.runtime import run_project_self_healing


def _project_root(tmp_path: Path, *, repairable: bool = True) -> Path:
    root = tmp_path / "generated_project"
    app = root / "apps" / "api" / "app"
    tests = root / "tests" / "python"
    app.mkdir(parents=True)
    tests.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    if repairable:
        (app / "main.py").write_text("def healthy():\n    return False\n", encoding="utf-8")
        (tests / "test_health.py").write_text(
            "from apps.api.app.main import healthy\n\n\ndef test_healthy():\n    assert healthy()\n",
            encoding="utf-8",
        )
    else:
        (tests / "test_permanent.py").write_text("def test_permanent():\n    assert False\n", encoding="utf-8")
    return root


def _allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_SELF_HEALING_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_PATCH_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS", "1")
    monkeypatch.setenv("ANN_PROJECT_PATCH_TOKEN", "local-test-token")


def test_failure_generates_failure_analysis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert any(path.endswith("53_project_failure_analysis.md") for path in result.artifacts)


def test_failure_generates_root_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert "assertion" in result.root_cause.lower() or "remaining" in result.root_cause.lower()
    assert any(path.endswith("54_project_root_cause.md") for path in result.artifacts)


def test_retry_patch_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.retry_patch_files
    assert Path(result.retry_patch_files[0]).is_file()


def test_retry_patch_modifies_only_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert all(Path(path).resolve().is_relative_to(root.resolve()) for path in result.retry_patch_files)


def test_retry_apply_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.status == "REPAIRED"
    assert "return True" in (root / "apps" / "api" / "app" / "main.py").read_text(encoding="utf-8")


def test_retry_verification_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.verification_status == "PASSED"


def test_retry_pass_updates_consensus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.consensus["consensus_decision"] == "SELF_HEALING_REPAIRED"
    assert (root / "outputs" / "runs" / "self_heal" / "58_retry_consensus.json").is_file()


def test_retry_fail_generates_next_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path, repairable=False)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 2, "local-test-token", True)

    assert result.status == "FAILED_PERMANENTLY"
    assert len(result.retry_patch_files) == 2


def test_max_attempts_produces_failed_permanently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path, repairable=False)

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.status == "FAILED_PERMANENTLY"
    assert result.attempts == 1


def test_ann_repo_blocked() -> None:
    result = run_project_self_healing(
        self_healing_runtime.REPO_ROOT,
        "outputs/runs/self_heal",
        approval_token="local-test-token",
        confirm_retry=True,
    )

    assert result.status == "BLOCKED"
    assert any("ANN repository" in error for error in result.validation_errors)


def test_repo_child_generated_project_self_healing_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    repo = tmp_path / "AgenticEngineeringNetwork"
    root = repo / "outputs" / "autonomous_capability_projects" / "crm" / "crm"
    app = root / "apps" / "api" / "app"
    tests = root / "tests" / "python"
    app.mkdir(parents=True)
    tests.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text("def healthy():\n    return False\n", encoding="utf-8")
    (tests / "test_health.py").write_text(
        "from apps.api.app.main import healthy\n\n\ndef test_healthy():\n    assert healthy()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(self_healing_runtime, "REPO_ROOT", repo.resolve())

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.status == "REPAIRED"


def test_mnt_c_blocked() -> None:
    result = run_project_self_healing(
        "/mnt/c/ANNProjects/crm",
        "outputs/runs/self_heal",
        approval_token="local-test-token",
        confirm_retry=True,
    )

    assert result.status == "BLOCKED"


def test_c_drive_blocked() -> None:
    result = run_project_self_healing(
        "C:\\ANNProjects\\crm",
        "outputs/runs/self_heal",
        approval_token="local-test-token",
        confirm_retry=True,
    )

    assert result.status == "BLOCKED"


def test_git_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = tmp_path / ".git"
    root.mkdir()

    result = run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert result.status == "BLOCKED"


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Project self-healing must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True).status == "REPAIRED"


def test_no_installs_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)

    run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True)

    assert not (root / "node_modules").exists()
    assert not (root / ".venv").exists()


def test_no_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)
    original_run = subprocess.run

    def guarded_run(*args: object, **kwargs: object):
        assert kwargs.get("shell") is False
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)

    assert run_project_self_healing(root, "outputs/runs/self_heal", 1, "local-test-token", True).status == "REPAIRED"


def test_desktop_still_has_self_healing_view() -> None:
    from agentic_network.desktop_app.navigation import navigation_labels
    from agentic_network.desktop_app.views.project_self_healing_view import PROJECT_SELF_HEALING_MESSAGE

    assert "Project Self Healing" in navigation_labels()
    assert "max attempts" in PROJECT_SELF_HEALING_MESSAGE


def test_no_touches_ann(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    readme = self_healing_runtime.REPO_ROOT / "README.md"
    before = readme.read_text(encoding="utf-8")

    test_ann_repo_blocked()

    assert readme.read_text(encoding="utf-8") == before


def test_cli_run_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _allow_all(monkeypatch)
    root = _project_root(tmp_path)
    exit_code = self_healing_main(
        [
            "--project-root",
            str(root),
            "--run-dir",
            "outputs/runs/self_heal",
            "--max-attempts",
            "1",
            "--approval-token",
            "local-test-token",
            "--confirm-retry",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "REPAIRED"
