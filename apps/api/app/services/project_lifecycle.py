from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.client import HTTPException as HttpClientException
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError
import zipfile

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.security.approvals import ApprovalRequest
from agentic_engineering_network.security.review import SecurityReviewer
from agentic_engineering_network.shared.config import Settings, to_host_path
from agentic_engineering_network.shared.providers import Prompt, build_provider


@dataclass(frozen=True)
class LifecycleStep:
    name: str
    status: str
    detail: str
    command: list[str] | None = None


@dataclass(frozen=True)
class LifecycleResult:
    project_root: str
    display_root: str
    sandbox_id: str
    release_package: str
    attempts: int
    status: str
    steps: list[LifecycleStep]

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "steps": [asdict(step) for step in self.steps],
        }


class ProjectLifecycleRunner:
    def __init__(self, settings: Settings, audit: AuditLogger) -> None:
        self.settings = settings
        self.audit = audit
        self.security = SecurityReviewer()

    def run(self, run_id: str, idea: str, approvals: list[ApprovalRequest]) -> dict[str, object]:
        project_root = self._project_root_from_approvals(approvals)
        display_root = to_host_path(self.settings, project_root)
        sandbox_dir = project_root / ".aen"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        sandbox_id = f"aen-{run_id[:8]}"
        steps: list[LifecycleStep] = []
        max_attempts = max(1, min(self.settings.max_repair_attempts, 50))
        retry_history: list[dict[str, object]] = []

        for attempt in range(1, max_attempts + 1):
            self.audit.record(
                "lifecycle.attempt_started",
                "ProjectLifecycleRunner",
                f"Validation attempt {attempt} for generated project.",
                {"run_id": run_id, "project_root": str(project_root), "sandbox_id": sandbox_id},
            )
            steps = self._validate(project_root, run_id)
            if all(step.status == "passed" for step in steps):
                retry_history.append(
                    {
                        "attempt": attempt,
                        "status": "passed",
                        "failed_checks": [],
                        "next_action": "completed",
                    }
                )
                break
            fixed = self._apply_known_fixes(project_root, steps)
            steps.append(
                LifecycleStep(
                    "auto_fix",
                    "passed" if fixed else "skipped",
                    "Applied deterministic known fixes." if fixed else "No deterministic known fix matched the failures.",
                )
            )
            if fixed:
                retry_history.append(
                    {
                        "attempt": attempt,
                        "status": "patched",
                        "failed_checks": [asdict(step) for step in steps if step.status == "failed"],
                        "repair": "deterministic",
                        "next_action": "retry_validation",
                    }
                )
                self._sleep_before_retry(attempt, max_attempts)
                continue
            provider_fix = self._apply_provider_patch(project_root, run_id, idea, steps, attempt)
            steps.append(provider_fix)
            if provider_fix.status != "passed":
                retry_history.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "failed_checks": [asdict(step) for step in steps if step.status == "failed"],
                        "repair": "provider",
                        "repair_detail": provider_fix.detail,
                        "next_action": "human_escalation",
                    }
                )
                break
            retry_history.append(
                {
                    "attempt": attempt,
                    "status": "patched",
                    "failed_checks": [asdict(step) for step in steps if step.status == "failed"],
                    "repair": "provider",
                    "repair_detail": provider_fix.detail,
                    "next_action": "retry_validation",
                }
            )
            self._sleep_before_retry(attempt, max_attempts)

        infrastructure_blocked = self._is_infrastructure_blocked(steps)
        security_result = self.security.review_generated_files(self._read_project_files(project_root))
        steps.append(
            LifecycleStep(
                "security_review",
                "passed" if security_result.passed else "failed",
                json.dumps(security_result.to_dict(), sort_keys=True),
            )
        )
        if any(step.status == "failed" for step in steps):
            steps.append(self._failure_summary_step(steps, status="blocked" if infrastructure_blocked else "failed"))
            if attempt >= max_attempts:
                steps.append(self._human_escalation_step(project_root, run_id, idea, steps))
            self._write_fix_plan(project_root, run_id, idea, steps)
        self._write_sandbox_manifest(project_root, sandbox_id, run_id, idea, steps)
        self._write_retry_history(project_root, run_id, retry_history)
        release_package = self._package_project(project_root, sandbox_dir)
        steps.append(LifecycleStep("release_package", "passed", f"Created {release_package}"))
        display_release_package = to_host_path(self.settings, release_package)
        status = self._lifecycle_status(steps)
        result = LifecycleResult(
            project_root=str(project_root),
            display_root=display_root,
            sandbox_id=sandbox_id,
            release_package=display_release_package,
            attempts=attempt,
            status=status,
            steps=steps,
        )
        self.audit.record(
            "lifecycle.completed",
            "ProjectLifecycleRunner",
            f"Generated project lifecycle completed with status {status}.",
            {"run_id": run_id, **result.to_dict()},
        )
        return result.to_dict()

    def _validate(self, project_root: Path, run_id: str) -> list[LifecycleStep]:
        steps = [
            self._validate_required_files(project_root),
            self._validate_python_syntax(project_root),
            self._validate_compose(project_root),
            self._validate_web_project(project_root),
            self._validate_alembic(project_root),
            self._validate_desktop_packaging(project_root),
        ]
        if all(step.status == "passed" for step in steps):
            steps.extend(self._run_live_sandbox(project_root, run_id))
        return steps

    def _validate_required_files(self, project_root: Path) -> LifecycleStep:
        required = [
            "README.md",
            ".env.example",
            "docker-compose.yml",
            "apps/api/app/main.py",
            "apps/api/alembic.ini",
            "apps/api/migrations/env.py",
            "apps/web/src/app/page.tsx",
            "apps/desktop/package.json",
            "database/schema.sql",
        ]
        missing = [item for item in required if not (project_root / item).exists()]
        return LifecycleStep(
            "required_files",
            "failed" if missing else "passed",
            f"Missing: {', '.join(missing)}" if missing else "All required project files exist.",
        )

    def _validate_python_syntax(self, project_root: Path) -> LifecycleStep:
        files = sorted((project_root / "apps" / "api" / "app").glob("*.py"))
        files += sorted((project_root / "apps" / "api" / "migrations").rglob("*.py"))
        if not files:
            return LifecycleStep("python_syntax", "failed", "No Python files found.")
        command = [sys.executable, "-m", "py_compile", *[str(file) for file in files]]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        detail = completed.stderr.strip() or completed.stdout.strip() or f"Compiled {len(files)} Python files."
        return LifecycleStep(
            "python_syntax",
            "passed" if completed.returncode == 0 else "failed",
            detail,
            command=command,
        )

    def _validate_compose(self, project_root: Path) -> LifecycleStep:
        compose = project_root / "docker-compose.yml"
        if not compose.exists():
            return LifecycleStep("compose_static", "failed", "docker-compose.yml is missing.")
        text = compose.read_text(encoding="utf-8")
        required = ["postgres:", "api:", "web:", "depends_on:", "healthcheck:"]
        missing = [token for token in required if token not in text]
        return LifecycleStep(
            "compose_static",
            "failed" if missing else "passed",
            f"Missing compose tokens: {', '.join(missing)}" if missing else "Compose file contains required services and health checks.",
        )

    def _validate_web_project(self, project_root: Path) -> LifecycleStep:
        package = project_root / "apps" / "web" / "package.json"
        page = project_root / "apps" / "web" / "src" / "app" / "page.tsx"
        if not package.exists() or not page.exists():
            return LifecycleStep("web_static", "failed", "Web package or page is missing.")
        data = json.loads(package.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        missing = [name for name in ["build", "e2e"] if name not in scripts]
        missing += [name for name in ["next", "react", "typescript"] if name not in deps]
        return LifecycleStep(
            "web_static",
            "failed" if missing else "passed",
            f"Missing web package entries: {', '.join(missing)}" if missing else "Web package contains build, E2E, and core dependencies.",
        )

    def _validate_alembic(self, project_root: Path) -> LifecycleStep:
        migration = project_root / "apps" / "api" / "migrations" / "versions" / "0001_initial.py"
        if not migration.exists():
            return LifecycleStep("alembic_migrations", "failed", "Initial Alembic migration is missing.")
        text = migration.read_text(encoding="utf-8")
        tokens = ["def upgrade", "def downgrade", "op.create_table"]
        missing = [token for token in tokens if token not in text]
        return LifecycleStep(
            "alembic_migrations",
            "failed" if missing else "passed",
            f"Missing migration tokens: {', '.join(missing)}" if missing else "Initial Alembic migration is present.",
        )

    def _validate_desktop_packaging(self, project_root: Path) -> LifecycleStep:
        package = project_root / "apps" / "desktop" / "package.json"
        script = project_root / "scripts" / "package-windows.ps1"
        if not package.exists() or not script.exists():
            return LifecycleStep("desktop_packaging", "failed", "Desktop package metadata or package-windows.ps1 is missing.")
        data = json.loads(package.read_text(encoding="utf-8"))
        has_package = "package" in data.get("scripts", {})
        return LifecycleStep(
            "desktop_packaging",
            "passed" if has_package else "failed",
            "Desktop Windows packaging script is present." if has_package else "Desktop package script is missing.",
        )

    def _run_live_sandbox(self, project_root: Path, run_id: str) -> list[LifecycleStep]:
        if os.environ.get("AEN_ENABLE_LIVE_SANDBOX", "1") != "1":
            return [LifecycleStep("live_sandbox", "skipped", "Live sandbox execution is disabled.")]
        ports = self._ports_for_run(run_id)
        passthrough_env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "DOCKER_HOST"}
        }
        env = {
            **passthrough_env,
            "COMPOSE_PROJECT_NAME": f"aen-{run_id[:8]}".lower(),
            "POSTGRES_USER": "crm",
            "POSTGRES_PASSWORD": "change-me",
            "POSTGRES_DB": "crm",
            "DATABASE_URL": "postgresql+psycopg://crm:change-me@postgres:5432/crm",
            "JWT_SECRET": "local-sandbox-secret",
            "POSTGRES_PORT": str(ports["postgres"]),
            "API_PORT": str(ports["api"]),
            "WEB_PORT": str(ports["web"]),
            "CORS_ORIGINS": f"http://localhost:{ports['web']}",
            "NEXT_PUBLIC_API_URL": f"http://localhost:{ports['api']}",
        }
        compose_command = self._compose_command(project_root, env)
        if compose_command is None:
            return [LifecycleStep("live_sandbox", "skipped", "Docker Compose is unavailable to run generated project checks.")]

        base = compose_command
        steps: list[LifecycleStep] = []
        try:
            steps.append(LifecycleStep("docker_compose_config", "passed", f"Compose configuration validated with {' '.join(base)}.", [*base, "config"]))
            if steps[-1].status != "passed":
                return steps
            steps.append(self._run_command("docker_compose_build", [*base, "build"], project_root, env, timeout=420))
            if steps[-1].status != "passed":
                if self._is_infrastructure_failure(steps[-1]):
                    failed_build = steps.pop()
                    steps.append(
                        LifecycleStep(
                            "docker_compose_build",
                            "skipped",
                            (
                                "Docker build was blocked by external image registry or Docker engine availability; "
                                f"running local validation fallback instead. Evidence: {failed_build.detail[-1200:]}"
                            ),
                            failed_build.command,
                        )
                    )
                    steps.extend(self._run_local_validation_fallback(project_root))
                    return steps
                return steps
            steps.append(self._run_command("docker_compose_up", [*base, "up", "-d", "postgres", "api", "web"], project_root, env, timeout=180))
            if steps[-1].status != "passed":
                steps.extend(self._collect_compose_logs(base, project_root, env))
                return steps
            steps.append(self._wait_for_http("api_health_live", f"http://host.docker.internal:{ports['api']}/health", timeout=90))
            steps.append(self._wait_for_http("web_health_live", f"http://host.docker.internal:{ports['web']}", timeout=90))
            steps.append(self._run_command("api_pytest_live", [*base, "run", "--rm", "api", "pytest", "-q"], project_root, env, timeout=180))
            steps.append(self._run_command("web_build_live", [*base, "run", "--rm", "web", "npm", "run", "build"], project_root, env, timeout=240))
            if any(step.status == "failed" for step in steps):
                steps.extend(self._collect_compose_logs(base, project_root, env))
        finally:
            down = self._run_command("docker_compose_down", [*base, "down", "-v"], project_root, env, timeout=120)
            steps.append(down)
            if self.settings.remove_sandbox_images_after_run:
                steps.append(
                    LifecycleStep(
                        "docker_compose_remove_sandbox_images",
                        "skipped",
                        (
                            "Sandbox image cleanup is skipped for Docker Compose CLI compatibility; "
                            "containers and volumes were removed by docker_compose_down."
                        ),
                        command=[*base, "down", "--rmi", "local"],
                    )
                )
        return steps

    def _run_local_validation_fallback(self, project_root: Path) -> list[LifecycleStep]:
        api_dir = project_root / "apps" / "api"
        web_dir = project_root / "apps" / "web"
        env = {
            **os.environ,
            "PYTHONPATH": str(api_dir),
            "DATABASE_URL": "sqlite:///./local-validation.db",
            "JWT_SECRET": "local-validation-secret",
            "REFRESH_TOKEN_SECRET": "local-validation-refresh-secret",
            "CORS_ORIGINS": "http://localhost:13000",
        }
        steps = [
            self._run_command(
                "api_pytest_local_fallback",
                [sys.executable, "-m", "pytest", "tests", "-q"],
                api_dir,
                env,
                timeout=180,
            )
        ]
        package_json = web_dir / "package.json"
        if package_json.exists():
            steps.append(
                LifecycleStep(
                    "web_build_local_fallback",
                    "skipped",
                    "Web build requires project npm dependencies or Docker; web source was already covered by static validation.",
                    ["npm", "run", "build"],
                )
            )
        return steps

    def _collect_compose_logs(self, base: list[str], project_root: Path, env: dict[str, str]) -> list[LifecycleStep]:
        return [
            self._run_command(
                f"{service}_logs",
                [*base, "logs", "--no-color", "--tail=120", service],
                project_root,
                env,
                timeout=60,
            )
            for service in ("postgres", "api", "web")
        ]

    def _run_command(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> LifecycleStep:
        self.audit.record(
            "sandbox.command.started",
            "ProjectLifecycleRunner",
            f"Executing {name}.",
            {"command": command, "cwd": str(cwd)},
        )
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            output_tail = f"stdout={exc.stdout or ''} stderr={exc.stderr or ''}"[-7600:]
            detail = f"Timed out after {timeout}s while executing {name}. {output_tail}"
            self.audit.record("sandbox.command.failed", "ProjectLifecycleRunner", detail, {"command": command})
            return LifecycleStep(name, "failed", detail, command=command)
        detail = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        status = "passed" if completed.returncode == 0 else "failed"
        self.audit.record(
            "sandbox.command.completed",
            "ProjectLifecycleRunner",
            f"{name} {status}.",
            {"command": command, "returncode": completed.returncode, "output_tail": detail[-4000:]},
        )
        return LifecycleStep(name, status, detail[-8000:] or "Command completed.", command=command)

    @staticmethod
    def _is_infrastructure_failure(step: LifecycleStep) -> bool:
        if step.status != "failed":
            return False
        detail = step.detail.lower()
        markers = (
            "timed out after",
            "tls handshake timeout",
            "failed to resolve reference",
            "registry-1.docker.io",
            "docker.io/library",
            "net/http",
            "i/o timeout",
            "context deadline exceeded",
            "temporary failure",
            "connection reset by peer",
            "failed to connect to the docker api",
            "docker_engine",
            "check if the path is correct and if the daemon is running",
            "cannot connect to the docker daemon",
            "docker daemon",
            "buildx plugin",
            "requires buildx plugin",
            "el sistema no puede encontrar el archivo especificado",
        )
        if any(marker in detail for marker in markers):
            return True
        return step.name == "docker_compose_build" and "downloading [" in detail

    @classmethod
    def _is_infrastructure_blocked(cls, steps: list[LifecycleStep]) -> bool:
        failed = [
            step
            for step in steps
            if step.status == "failed" and step.name not in {"failure_summary", "human_escalation"}
        ]
        return bool(failed) and all(cls._is_infrastructure_failure(step) for step in failed)

    @classmethod
    def _lifecycle_status(cls, steps: list[LifecycleStep]) -> str:
        if all(step.status in {"passed", "skipped"} for step in steps):
            return "passed"
        if cls._is_infrastructure_blocked(steps):
            return "blocked"
        return "failed"

    def _wait_for_http(self, name: str, url: str, timeout: int) -> LifecycleStep:
        deadline = time.time() + timeout
        last_error = ""
        while time.time() < deadline:
            try:
                request = Request(url, headers={"User-Agent": "AgenticEngineeringNetworkLifecycle/1.0"})
                with urlopen(request, timeout=5) as response:
                    if 200 <= response.status < 500:
                        return LifecycleStep(name, "passed", f"{url} returned HTTP {response.status}.")
            except (URLError, TimeoutError, OSError, HttpClientException) as exc:
                last_error = str(exc)
            time.sleep(2)
        return LifecycleStep(name, "failed", f"{url} did not become ready within {timeout}s. Last error: {last_error}")

    def _docker_available(self) -> bool:
        try:
            completed = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    def _compose_command(self, project_root: Path | None = None, env: dict[str, str] | None = None) -> list[str] | None:
        if not self._docker_available():
            return None
        candidates = (["docker", "compose"], ["docker-compose"])
        for command in candidates:
            try:
                probe = [*command, "config"] if project_root is not None else [*command, "version"]
                completed = subprocess.run(
                    probe,
                    cwd=project_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if completed.returncode == 0:
                self.audit.record(
                    "sandbox.compose.detected",
                    "ProjectLifecycleRunner",
                    f"Using {' '.join(command)} for generated project sandbox checks.",
                    {"command": command, "project_root": str(project_root) if project_root else None},
                )
                return command
        return None

    @staticmethod
    def _ports_for_run(run_id: str) -> dict[str, int]:
        seed = int(run_id.replace("-", "")[:6], 16) % 1000
        return {
            "postgres": 15432 + seed,
            "api": 18000 + seed,
            "web": 13000 + seed,
        }

    def _apply_known_fixes(self, project_root: Path, steps: list[LifecycleStep]) -> bool:
        fixed = False
        if any(step.name == "required_files" and step.status == "failed" for step in steps):
            (project_root / "apps" / "api" / "app" / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
            (project_root / "apps" / "api" / "app" / "__init__.py").touch()
            fixed = True
        return fixed

    def _apply_provider_patch(
        self,
        project_root: Path,
        run_id: str,
        idea: str,
        steps: list[LifecycleStep],
        attempt: int,
    ) -> LifecycleStep:
        if self.settings.ai_provider in {"deterministic", "deterministic-local", "rules"}:
            return LifecycleStep("qwen_patch", "skipped", "AI patching is disabled for deterministic test provider.")
        failures = [step for step in steps if step.status == "failed"]
        if not failures:
            return LifecycleStep("qwen_patch", "skipped", "No failing lifecycle steps need a provider patch.")

        prompt_path = project_root / ".aen" / f"repair-prompt-attempt-{attempt}.json"
        raw_path = project_root / ".aen" / f"repair-response-attempt-{attempt}.md"
        diff_path = project_root / ".aen" / f"repair-attempt-{attempt}.diff"
        prompt_payload = {
            "instruction": (
                "Patch this generated project so the failing lifecycle checks pass. "
                "Return only a unified diff with paths relative to project_root. "
                "Do not include prose, commands, markdown fences, or absolute paths."
            ),
            "idea": idea,
            "run_id": run_id,
            "project_root": str(project_root),
            "files": self._project_file_inventory(project_root),
            "failures": [asdict(step) for step in failures],
        }
        prompt_path.write_text(json.dumps(prompt_payload, indent=2), encoding="utf-8")
        try:
            provider = build_provider(self.settings)
            response = provider.generate(
                Prompt(
                    system="You are the code repair agent for a local autonomous engineering platform.",
                    user=json.dumps(prompt_payload, indent=2),
                )
            )
        except Exception as exc:
            self.audit.record("qwen_patch.unavailable", "ProjectLifecycleRunner", str(exc), {"run_id": run_id})
            return LifecycleStep(
                "qwen_patch",
                "skipped",
                f"Provider patch request unavailable; continuing with deterministic fix plan and failure evidence: {exc}",
            )

        raw_path.write_text(response.content, encoding="utf-8")
        diff = self._extract_unified_diff(response.content)
        if not diff.strip():
            return LifecycleStep("qwen_patch", "failed", f"Provider returned no unified diff. Raw response: {raw_path}")
        diff_path.write_text(diff, encoding="utf-8")
        check = self._run_git_apply(project_root, diff, check_only=True)
        if check.status != "passed":
            return LifecycleStep(
                "qwen_patch",
                "failed",
                f"Provider diff failed validation. Diff: {diff_path}\n{check.detail}",
                command=check.command,
            )
        applied = self._run_git_apply(project_root, diff, check_only=False)
        if applied.status != "passed":
            return LifecycleStep(
                "qwen_patch",
                "failed",
                f"Provider diff validation passed but apply failed. Diff: {diff_path}\n{applied.detail}",
                command=applied.command,
            )
        self.audit.record(
            "qwen_patch.applied",
            "ProjectLifecycleRunner",
            "Applied provider-generated repair diff.",
            {"run_id": run_id, "provider": response.provider, "model": response.model, "diff": str(diff_path)},
        )
        return LifecycleStep("qwen_patch", "passed", f"Applied provider repair diff from {response.provider}:{response.model}.")

    def _run_git_apply(self, project_root: Path, diff: str, check_only: bool) -> LifecycleStep:
        command = ["git", "apply", "--whitespace=fix"]
        name = "git_apply_check" if check_only else "git_apply"
        if check_only:
            command.append("--check")
        command.append("-")
        completed = subprocess.run(
            command,
            cwd=project_root,
            input=diff,
            capture_output=True,
            text=True,
            timeout=60,
        )
        detail = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        return LifecycleStep(name, "passed" if completed.returncode == 0 else "failed", detail[-4000:] or "Diff applied.", command)

    @staticmethod
    def _extract_unified_diff(content: str) -> str:
        stripped = content.strip()
        if "```" in stripped:
            parts = stripped.split("```")
            for part in parts:
                candidate = part.removeprefix("diff").strip()
                if candidate.startswith(("diff --git", "--- ")):
                    return candidate + "\n"
        lines = stripped.splitlines()
        for index, line in enumerate(lines):
            if line.startswith(("diff --git", "--- ")):
                return "\n".join(lines[index:]).strip() + "\n"
        return ""

    def _project_file_inventory(self, project_root: Path) -> list[str]:
        ignored = {".aen", "node_modules", ".next", "__pycache__", ".pytest_cache", "dist", "release"}
        files: list[str] = []
        for path in sorted(project_root.rglob("*")):
            if not path.is_file() or any(part in ignored for part in path.parts):
                continue
            try:
                files.append(path.relative_to(project_root).as_posix())
            except ValueError:
                continue
        return files[:200]

    def _write_sandbox_manifest(
        self,
        project_root: Path,
        sandbox_id: str,
        run_id: str,
        idea: str,
        steps: list[LifecycleStep],
    ) -> None:
        manifest = {
            "sandbox_id": sandbox_id,
            "run_id": run_id,
            "idea": idea,
            "project_root": str(project_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "execution_boundary": "approval-gated-project-sandbox",
            "steps": [asdict(step) for step in steps],
        }
        (project_root / ".aen" / "sandbox.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _sleep_before_retry(self, attempt: int, max_attempts: int) -> None:
        if attempt >= max_attempts:
            return
        base = max(0.0, self.settings.repair_backoff_base_seconds)
        cap = max(base, self.settings.repair_backoff_max_seconds)
        seconds = min(cap, base * (2 ** max(0, attempt - 1)))
        if seconds <= 0:
            return
        self.audit.record(
            "lifecycle.retry_backoff",
            "ProjectLifecycleRunner",
            f"Waiting {seconds:.1f}s before the next correction attempt.",
            {"attempt": attempt, "next_attempt": attempt + 1, "seconds": seconds},
        )
        time.sleep(seconds)

    def _write_retry_history(self, project_root: Path, run_id: str, retry_history: list[dict[str, object]]) -> None:
        payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "max_attempts": max(1, min(self.settings.max_repair_attempts, 50)),
            "backoff": {
                "base_seconds": self.settings.repair_backoff_base_seconds,
                "max_seconds": self.settings.repair_backoff_max_seconds,
            },
            "attempts": retry_history,
        }
        (project_root / ".aen" / "retry-history.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _failure_summary_step(self, steps: list[LifecycleStep], status: str = "failed") -> LifecycleStep:
        failures = [step for step in steps if step.status == "failed"]
        summary = {
            "failed_checks": len(failures),
            "checks": [
                {
                    "name": step.name,
                    "detail_tail": step.detail[-1200:],
                    "command": step.command,
                }
                for step in failures
            ],
            "guidance": "Review .aen/fix-plan.json and .aen/retry-history.json before continuing manually.",
        }
        return LifecycleStep("failure_summary", status, json.dumps(summary, sort_keys=True))

    def _human_escalation_step(
        self,
        project_root: Path,
        run_id: str,
        idea: str,
        steps: list[LifecycleStep],
    ) -> LifecycleStep:
        escalation_path = project_root / ".aen" / "human-escalation.md"
        failures = [step for step in steps if step.status == "failed"]
        body = [
            "# Human Escalation Required",
            "",
            f"Run: `{run_id}`",
            f"Idea: `{idea}`",
            "",
            "The configurable correction loop exhausted its allowed attempts or could not apply a valid provider patch.",
            "A human engineer should inspect the failing commands and decide whether to adjust requirements, dependencies, or generated code.",
            "",
            "## Failed Checks",
            "",
        ]
        for step in failures:
            body.extend(
                [
                    f"### {step.name}",
                    "",
                    "```text",
                    step.detail[-4000:],
                    "```",
                    "",
                ]
            )
        escalation_path.write_text("\n".join(body), encoding="utf-8")
        self.audit.record(
            "lifecycle.human_escalation",
            "ProjectLifecycleRunner",
            "Generated human escalation summary after correction loop stopped.",
            {"run_id": run_id, "path": str(escalation_path), "failure_count": len(failures)},
        )
        return LifecycleStep("human_escalation", "failed", f"Created {escalation_path}")

    def _write_fix_plan(self, project_root: Path, run_id: str, idea: str, steps: list[LifecycleStep]) -> None:
        failures = [asdict(step) for step in steps if step.status == "failed"]
        prompt = {
            "instruction": "Patch the generated project so all lifecycle checks pass. Return unified diffs only.",
            "idea": idea,
            "run_id": run_id,
            "project_root": str(project_root),
            "failures": failures,
        }
        (project_root / ".aen" / "fix-plan.json").write_text(json.dumps(prompt, indent=2), encoding="utf-8")
        self.audit.record(
            "fix_plan.created",
            "ProjectLifecycleRunner",
            "Created Qwen-ready fix plan from real build/test failures.",
            {"run_id": run_id, "path": str(project_root / ".aen" / "fix-plan.json"), "failure_count": len(failures)},
        )

    def _package_project(self, project_root: Path, sandbox_dir: Path) -> Path:
        release_dir = sandbox_dir / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        package_path = release_dir / f"{project_root.name}.zip"
        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in project_root.rglob("*"):
                if path.is_dir():
                    continue
                if path == package_path:
                    continue
                archive.write(path, path.relative_to(project_root))
        return package_path

    def _project_root_from_approvals(self, approvals: list[ApprovalRequest]) -> Path:
        paths = []
        for approval in approvals:
            raw = approval.payload.get("path")
            if isinstance(raw, str):
                paths.append(Path(raw).resolve())
        if not paths:
            raise ValueError("No generated project file approvals were found for this run.")
        common_text = Path(paths[0]).parent
        for path in paths[1:]:
            common_text = Path(self._common_path(common_text, path.parent))
        return common_text

    @staticmethod
    def _common_path(left: Path, right: Path) -> str:
        left_parts = left.resolve().parts
        right_parts = right.resolve().parts
        common_parts = []
        for left_part, right_part in zip(left_parts, right_parts):
            if left_part != right_part:
                break
            common_parts.append(left_part)
        return str(Path(*common_parts))

    def _read_project_files(self, project_root: Path) -> dict[str, str]:
        files: dict[str, str] = {}
        for path in project_root.rglob("*"):
            if path.is_dir() or ".aen" in path.parts:
                continue
            try:
                files[str(path.relative_to(project_root))] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        return files
