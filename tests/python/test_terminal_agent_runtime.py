import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_network.terminal_agent.runtime import run_terminal_command
from agentic_network.ui_backend.runtime import create_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", str(root))
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", str(tmp_path / "blocked"))
    monkeypatch.setenv("PYTHONPATH", str(root))
    return root


def test_executes_allowed_pytest_and_returns_passed(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    _write(root / "tests" / "test_sample.py", "def test_ok():\n    assert True\n")

    result = run_terminal_command(
        ["pytest", "tests/test_sample.py", "-q"],
        ".",
        project_root=root,
        artifact_root=root / "outputs" / "terminal",
    )

    assert result.status == "PASSED"
    assert result.exit_code == 0
    assert "passed" in result.stdout.lower()


def test_executes_allowed_ruff_and_returns_passed(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    _write(root / "sample.py", "VALUE = 1\n")

    result = run_terminal_command(
        ["ruff", "check", "sample.py"],
        ".",
        project_root=root,
        artifact_root=root / "outputs" / "terminal",
    )

    assert result.status == "PASSED"
    assert result.exit_code == 0


def test_blocks_rm_rf(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    result = run_terminal_command(["rm", "-rf", "."], ".", project_root=root)

    assert result.status == "BLOCKED"
    assert "destructive_command_blocked" in result.validation_errors


def test_blocks_pip_install(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    result = run_terminal_command(["pip", "install", "requests"], ".", project_root=root)

    assert result.status == "BLOCKED"
    assert "install_command_blocked" in result.validation_errors


def test_blocks_curl_and_wget(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    curl = run_terminal_command(["curl", "https://example.com"], ".", project_root=root)
    wget = run_terminal_command(["wget", "https://example.com"], ".", project_root=root)

    assert curl.status == "BLOCKED"
    assert wget.status == "BLOCKED"
    assert "network_command_blocked" in curl.validation_errors
    assert "network_command_blocked" in wget.validation_errors


def test_blocks_git_push_pull_clone(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    for subcommand in ("push", "pull", "clone"):
        result = run_terminal_command(["git", subcommand], ".", project_root=root)
        assert result.status == "BLOCKED"
        assert "git_network_command_blocked" in result.validation_errors


def test_blocks_bash_c_and_sh_c(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    bash = run_terminal_command(["bash", "-c", "echo unsafe"], ".", project_root=root)
    sh = run_terminal_command(["sh", "-c", "echo unsafe"], ".", project_root=root)

    assert bash.status == "BLOCKED"
    assert sh.status == "BLOCKED"
    assert "shell_command_blocked" in bash.validation_errors
    assert "shell_command_blocked" in sh.validation_errors


def test_blocks_cwd_outside_allowed_root(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()

    result = run_terminal_command(["pytest", "-q"], str(outside), project_root=root)

    assert result.status == "BLOCKED"
    assert "cwd_must_be_inside_repo" in result.validation_errors


def test_blocks_mnt_c_by_default(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    result = run_terminal_command(["pytest", "-q"], "/mnt/c/Users", project_root=root)

    assert result.status == "BLOCKED"
    assert "cwd_c_drive_blocked" in result.validation_errors


def test_timeout_produces_timeout(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(kwargs.get("args", ["python"]), timeout=1, output="partial out", stderr="partial err")

    result = run_terminal_command(
        ["python", "--version"],
        ".",
        timeout_seconds=1,
        subprocess_runner=fake_run,
        project_root=root,
    )

    assert result.status == "TIMEOUT"
    assert "partial out" in result.stdout
    assert "partial err" in result.stderr


def test_captures_stdout(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    result = run_terminal_command(["python", "--version"], ".", project_root=root)

    assert result.status == "PASSED"
    assert "Python" in (result.stdout + result.stderr)


def test_captures_stderr(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="sample stderr")

    result = run_terminal_command(
        ["pytest", "-q"],
        ".",
        subprocess_runner=fake_run,
        project_root=root,
    )

    assert result.status == "FAILED"
    assert "sample stderr" in result.stderr


def test_creates_terminal_artifact(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    artifact_root = root / "outputs" / "terminal"

    result = run_terminal_command(
        ["python", "--version"],
        ".",
        project_root=root,
        artifact_root=artifact_root,
    )

    artifact = Path(result.artifact_path)
    assert artifact.exists()
    assert artifact.is_relative_to(artifact_root)


def test_subprocess_runner_receives_shell_false(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    seen = {}

    def fake_run(*args, **kwargs):
        seen["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    result = run_terminal_command(
        ["pytest", "-q"],
        ".",
        subprocess_runner=fake_run,
        project_root=root,
    )

    assert result.status == "PASSED"
    assert seen["shell"] is False


def test_ui_endpoint_requires_confirm_execute(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    runs_root = root / "outputs" / "runs"
    runs_root.mkdir(parents=True)
    client = TestClient(create_app(runs_root=runs_root))

    response = client.post(
        "/api/terminal/run",
        json={"cwd": ".", "command": ["python", "--version"], "confirm_execute": False},
    )

    assert response.status_code == 400


def test_ui_endpoint_blocks_dangerous_command(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path, monkeypatch)
    runs_root = root / "outputs" / "runs"
    runs_root.mkdir(parents=True)
    client = TestClient(create_app(runs_root=runs_root))

    response = client.post(
        "/api/terminal/run",
        json={"cwd": str(root), "command": ["rm", "-rf", "."], "confirm_execute": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "BLOCKED"
    assert "destructive_command_blocked" in payload["validation_errors"]
