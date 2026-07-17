from pathlib import Path

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.shared.config import Settings

from app.services import project_lifecycle
from app.services.project_lifecycle import LifecycleStep, ProjectLifecycleRunner


def test_live_sandbox_uses_compose_project_env_instead_of_dash_p(monkeypatch) -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\project-lifecycle-compose")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    runner = ProjectLifecycleRunner(settings, AuditLogger(settings.audit_log_path))
    commands: list[list[str]] = []
    envs: list[dict[str, str]] = []

    monkeypatch.setattr(runner, "_compose_command", lambda project_root=None, env=None: ["docker", "compose"])

    def fake_run_command(name, command, cwd, env, timeout):  # noqa: ANN001
        commands.append(command)
        envs.append(env)
        status = "failed" if name == "docker_compose_build" else "passed"
        return LifecycleStep(name, status, "stop after compose build", command)

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    steps = runner._run_live_sandbox(scratch, "0039c970-09ce-4c6f-a2c8-d950fcc8e88d")  # noqa: SLF001

    assert commands
    assert all("-p" not in command for command in commands)
    assert all("--quiet" not in command for command in commands)
    assert all("--rmi" not in command for command in commands)
    assert steps[0].name == "docker_compose_config"
    assert steps[0].status == "passed"
    assert steps[0].command == ["docker", "compose", "config"]
    assert commands[0] == ["docker", "compose", "build"]
    assert envs[0]["COMPOSE_PROJECT_NAME"] == "aen-0039c970"
    assert any(
        step.name == "docker_compose_remove_sandbox_images" and step.status == "skipped"
        for step in steps
    )


def test_live_sandbox_can_use_standalone_docker_compose(monkeypatch) -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\project-lifecycle-compose-standalone")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    runner = ProjectLifecycleRunner(settings, AuditLogger(settings.audit_log_path))
    commands: list[list[str]] = []

    monkeypatch.setattr(runner, "_compose_command", lambda project_root=None, env=None: ["docker-compose"])

    def fake_run_command(name, command, cwd, env, timeout):  # noqa: ANN001
        commands.append(command)
        status = "failed" if name == "docker_compose_build" else "passed"
        return LifecycleStep(name, status, "stop after compose build", command)

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    runner._run_live_sandbox(scratch, "a8781282-fe67-4dc5-b001-b0b1c0f10b21")  # noqa: SLF001

    assert commands
    assert commands[0] == ["docker-compose", "build"]
    assert all("-p" not in command for command in commands)
    assert all("--quiet" not in command for command in commands)
    assert all("--rmi" not in command for command in commands)


def test_live_sandbox_uses_local_fallback_when_docker_build_is_registry_blocked(monkeypatch) -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\project-lifecycle-local-fallback")
    (scratch / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (scratch / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    runner = ProjectLifecycleRunner(settings, AuditLogger(settings.audit_log_path))

    monkeypatch.setattr(runner, "_compose_command", lambda project_root=None, env=None: ["docker-compose"])

    def fake_run_command(name, command, cwd, env, timeout):  # noqa: ANN001, ARG001
        if name == "docker_compose_build":
            return LifecycleStep(
                name,
                "failed",
                "failed to resolve reference docker.io/library/python:3.12-slim: net/http: TLS handshake timeout",
                command,
            )
        return LifecycleStep(name, "passed", "ok", command)

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    steps = runner._run_live_sandbox(scratch, "422d0a6e-10ff-4938-a18c-cc2187352d04")  # noqa: SLF001
    statuses = {step.name: step.status for step in steps}

    assert statuses["docker_compose_config"] == "passed"
    assert statuses["docker_compose_build"] == "skipped"
    assert statuses["api_pytest_local_fallback"] == "passed"
    assert statuses["web_build_local_fallback"] == "skipped"


def test_compose_command_prefers_project_validated_compose_plugin(monkeypatch) -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\project-lifecycle-compose-detect")
    scratch.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    runner = ProjectLifecycleRunner(settings, AuditLogger(settings.audit_log_path))
    probes: list[tuple[list[str], Path | None]] = []

    monkeypatch.setattr(runner, "_docker_available", lambda: True)

    def fake_subprocess_run(command, cwd=None, env=None, capture_output=True, text=True, timeout=20):  # noqa: ANN001, ARG001
        probes.append((command, cwd))

        class Completed:
            returncode = 0

        return Completed()

    monkeypatch.setattr(project_lifecycle.subprocess, "run", fake_subprocess_run)

    command = runner._compose_command(scratch, {"COMPOSE_PROJECT_NAME": "aen-test"})  # noqa: SLF001

    assert command == ["docker", "compose"]
    assert probes == [(["docker", "compose", "config"], scratch)]


def test_provider_unavailable_is_skipped_not_extra_lifecycle_failure(monkeypatch) -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\project-lifecycle-provider")
    project_root = scratch / "generated"
    (project_root / ".aen").mkdir(parents=True, exist_ok=True)
    settings = Settings(
        ai_provider="ollama",
        audit_log_path=scratch / "audit.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    runner = ProjectLifecycleRunner(settings, AuditLogger(settings.audit_log_path))

    def fail_provider(settings):  # noqa: ANN001
        raise RuntimeError("Ollama request failed: connection refused")

    monkeypatch.setattr(project_lifecycle, "build_provider", fail_provider)

    step = runner._apply_provider_patch(  # noqa: SLF001
        project_root,
        "run-123",
        "Build a task API",
        [LifecycleStep("docker_compose_config", "failed", "compose failed")],
        1,
    )

    assert step.name == "qwen_patch"
    assert step.status == "skipped"
    assert "Provider patch request unavailable" in step.detail


def test_lifecycle_status_blocks_on_docker_registry_timeout() -> None:
    steps = [
        LifecycleStep(
            "docker_compose_build",
            "failed",
            (
                'failed to resolve reference "docker.io/library/python:3.12-slim": '
                "failed to do request: Head https://registry-1.docker.io/v2/library/python/manifests/3.12-slim: "
                "net/http: TLS handshake timeout"
            ),
            ["docker-compose", "build"],
        ),
        LifecycleStep("security_review", "passed", "{}"),
        LifecycleStep("failure_summary", "blocked", "{}"),
        LifecycleStep("release_package", "passed", "Created package."),
    ]

    assert ProjectLifecycleRunner._lifecycle_status(steps) == "blocked"  # noqa: SLF001


def test_lifecycle_status_blocks_on_docker_layer_download_timeout() -> None:
    steps = [
        LifecycleStep(
            "docker_compose_build",
            "failed",
            "48347b15c85f: Downloading [==================================================>]  12.11MB/12.11MB",
            ["docker-compose", "build"],
        ),
        LifecycleStep("security_review", "passed", "{}"),
        LifecycleStep("failure_summary", "blocked", "{}"),
        LifecycleStep("release_package", "passed", "Created package."),
    ]

    assert ProjectLifecycleRunner._lifecycle_status(steps) == "blocked"  # noqa: SLF001


def test_lifecycle_status_blocks_when_docker_daemon_is_unavailable() -> None:
    steps = [
        LifecycleStep(
            "docker_compose_down",
            "failed",
            (
                "failed to connect to the docker API at npipe:////./pipe/docker_engine; "
                "check if the path is correct and if the daemon is running: "
                "El sistema no puede encontrar el archivo especificado."
            ),
            ["docker-compose", "down", "--volumes"],
        ),
        LifecycleStep("security_review", "passed", "{}"),
        LifecycleStep("release_package", "passed", "Created package."),
    ]

    assert ProjectLifecycleRunner._lifecycle_status(steps) == "blocked"  # noqa: SLF001


def test_lifecycle_status_blocks_when_docker_buildx_plugin_is_missing() -> None:
    steps = [
        LifecycleStep(
            "docker_compose_build",
            "failed",
            "Docker Compose requires buildx plugin to be installed.",
            ["docker-compose", "build"],
        ),
        LifecycleStep("security_review", "passed", "{}"),
    ]

    assert ProjectLifecycleRunner._lifecycle_status(steps) == "blocked"  # noqa: SLF001
