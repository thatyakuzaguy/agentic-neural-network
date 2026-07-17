"""Safe test runner for generated ANN projects.

The runner executes only deterministic allowlisted commands inside project_root
after explicit confirmation. It never installs dependencies, uses shell=True, or
executes arbitrary terminal commands.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import normalize_workspace_path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


@dataclass(frozen=True)
class ProjectVerificationResult:
    """Project verification result with stdout/stderr artifacts."""

    status: str
    project_root: str
    commands_selected: list[list[str]]
    commands_executed: list[list[str]]
    exit_codes: list[int | None]
    stdout_artifacts: list[str]
    stderr_artifacts: list[str]
    duration_seconds: float
    test_summary: str
    failed_commands: list[list[str]]
    retry_recommended: bool
    retry_context_artifact: str | None
    consensus_artifact: str | None
    action_plan_artifact: str | None
    validation_errors: list[str]
    validation_warnings: list[str]
    artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_project_test_commands(project_root: str | Path) -> tuple[list[list[str]], list[str]]:
    """Detect safe test commands for a generated project."""

    root = normalize_workspace_path(project_root)
    warnings: list[str] = []
    commands: list[list[str]] = []
    if _has_python_tests(root / "tests" / "python"):
        commands.append(["python", "-m", "pytest", "tests/python", "-q"])
    elif _has_pytest_config(root):
        commands.append(["python", "-m", "pytest", "-q"])
    elif _has_python_tests(root / "tests") and (root / "apps" / "api").is_dir():
        commands.append(["python", "-m", "pytest", "tests", "-q"])
    package_json = root / "package.json"
    if package_json.is_file() or (root / "apps" / "web" / "package.json").is_file():
        if not (root / "node_modules").is_dir():
            warnings.append("npm test skipped because node_modules is missing.")
        else:
            warnings.append("npm test detected but skipped in v8.6 unless explicitly enabled later.")
    if _has_ruff_config(root):
        commands.append(["python", "-m", "ruff", "check", "."])
    return commands, warnings


def run_project_verification(
    project_root: str | Path,
    run_dir: str | Path | None = None,
    timeout_seconds: int = 120,
    confirm_run: bool = False,
) -> ProjectVerificationResult:
    """Run allowlisted project tests and generate verification artifacts."""

    started = time.monotonic()
    root = normalize_workspace_path(project_root)
    errors, warnings = _validate_project_root(project_root, root)
    selected, detection_warnings = detect_project_test_commands(root)
    warnings.extend(detection_warnings)
    resolved_run_dir = _resolve_run_dir(root, run_dir)
    stdout_artifacts: list[str] = []
    stderr_artifacts: list[str] = []
    artifacts: list[str] = []
    commands_executed: list[list[str]] = []
    exit_codes: list[int | None] = []
    failed_commands: list[list[str]] = []

    if not confirm_run:
        warnings.append("confirm_run is required before executing project tests.")
        resolved_run_dir.mkdir(parents=True, exist_ok=True)
        return _finalize(
            status="SKIPPED",
            root=root,
            run_dir=resolved_run_dir,
            selected=selected,
            executed=commands_executed,
            exit_codes=exit_codes,
            stdout_artifacts=stdout_artifacts,
            stderr_artifacts=stderr_artifacts,
            duration=time.monotonic() - started,
            failed_commands=failed_commands,
            errors=errors,
            warnings=warnings,
            artifacts=artifacts,
        )
    if errors:
        resolved_run_dir.mkdir(parents=True, exist_ok=True)
        return _finalize(
            status="BLOCKED",
            root=root,
            run_dir=resolved_run_dir,
            selected=selected,
            executed=commands_executed,
            exit_codes=exit_codes,
            stdout_artifacts=stdout_artifacts,
            stderr_artifacts=stderr_artifacts,
            duration=time.monotonic() - started,
            failed_commands=failed_commands,
            errors=errors,
            warnings=warnings,
            artifacts=artifacts,
        )
    if not selected:
        resolved_run_dir.mkdir(parents=True, exist_ok=True)
        return _finalize(
            status="SKIPPED",
            root=root,
            run_dir=resolved_run_dir,
            selected=selected,
            executed=commands_executed,
            exit_codes=exit_codes,
            stdout_artifacts=stdout_artifacts,
            stderr_artifacts=stderr_artifacts,
            duration=time.monotonic() - started,
            failed_commands=failed_commands,
            errors=errors,
            warnings=[*warnings, "No safe test commands detected."],
            artifacts=artifacts,
        )

    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    timed_out = False
    for index, command in enumerate(selected, start=1):
        if not _command_allowed(command):
            warnings.append(f"Skipped non-allowlisted command: {' '.join(command)}")
            continue
        commands_executed.append(command)
        stdout_path = resolved_run_dir / f"48_project_test_stdout_{index}.log"
        stderr_path = resolved_run_dir / f"49_project_test_stderr_{index}.log"
        try:
            completed = subprocess.run(  # noqa: S603 - command is allowlisted and shell=False.
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
            exit_codes.append(completed.returncode)
            stdout_path.write_text(completed.stdout, encoding="utf-8", errors="replace")
            stderr_path.write_text(completed.stderr, encoding="utf-8", errors="replace")
            if completed.returncode != 0:
                failed_commands.append(command)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_codes.append(None)
            stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
            stderr_path.write_text(exc.stderr or "Command timed out.", encoding="utf-8", errors="replace")
            failed_commands.append(command)
        stdout_artifacts.append(str(stdout_path))
        stderr_artifacts.append(str(stderr_path))
        artifacts.extend([str(stdout_path), str(stderr_path)])
        if timed_out:
            break

    status = "TIMEOUT" if timed_out else ("FAILED" if failed_commands else "PASSED")
    return _finalize(
        status=status,
        root=root,
        run_dir=resolved_run_dir,
        selected=selected,
        executed=commands_executed,
        exit_codes=exit_codes,
        stdout_artifacts=stdout_artifacts,
        stderr_artifacts=stderr_artifacts,
        duration=time.monotonic() - started,
        failed_commands=failed_commands,
        errors=errors,
        warnings=warnings,
        artifacts=artifacts,
    )


def _finalize(
    *,
    status: str,
    root: Path,
    run_dir: Path,
    selected: list[list[str]],
    executed: list[list[str]],
    exit_codes: list[int | None],
    stdout_artifacts: list[str],
    stderr_artifacts: list[str],
    duration: float,
    failed_commands: list[list[str]],
    errors: list[str],
    warnings: list[str],
    artifacts: list[str],
) -> ProjectVerificationResult:
    retry_context = _write_retry_context(run_dir, status, failed_commands)
    consensus_path, action_path = _write_consensus_action(run_dir, status, failed_commands)
    verification_json = run_dir / "47_project_verification.json"
    verification_md = run_dir / "47_project_verification.md"
    passed_or_failed = _write_status_artifact(run_dir, status)
    all_artifacts = [str(verification_md), str(verification_json), *artifacts, retry_context, consensus_path, action_path, passed_or_failed]
    result = ProjectVerificationResult(
        status=status,
        project_root=str(root),
        commands_selected=selected,
        commands_executed=executed,
        exit_codes=exit_codes,
        stdout_artifacts=stdout_artifacts,
        stderr_artifacts=stderr_artifacts,
        duration_seconds=round(duration, 3),
        test_summary=_summary(status, executed, failed_commands),
        failed_commands=failed_commands,
        retry_recommended=status in {"FAILED", "TIMEOUT"},
        retry_context_artifact=retry_context,
        consensus_artifact=consensus_path,
        action_plan_artifact=action_path,
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
        artifacts=all_artifacts,
    )
    verification_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    verification_md.write_text(_verification_markdown(result), encoding="utf-8")
    return result


def _validate_project_root(raw_root: str | Path, root: Path) -> tuple[list[str], list[str]]:
    raw = str(raw_root).strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not raw:
        errors.append("project_root is required.")
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        errors.append("Path traversal is not allowed.")
    if _is_blocked_system_root(raw, root) and not _allow_temp_targets(root):
        errors.append("C: and /mnt/c project roots are blocked by default.")
    if _has_protected_part(root):
        errors.append("Protected ANN directories cannot be verified.")
    if (root == REPO_ROOT or _is_relative_to(root, REPO_ROOT)) and not _is_allowed_repo_project_root(root):
        errors.append("ANN repository cannot be verified by Project Test Runner.")
    if not root.exists():
        errors.append("project_root must exist.")
    elif not root.is_dir():
        errors.append("project_root must be a directory.")
    return errors, warnings


def _resolve_run_dir(root: Path, run_dir: str | Path | None) -> Path:
    if run_dir is None:
        return root / "project_runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw = str(run_dir)
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        raise ValueError("Path traversal is not allowed for run_dir.")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, root):
        raise ValueError("run_dir must stay inside project_root.")
    if _has_protected_part(resolved.relative_to(root)):
        raise ValueError("run_dir cannot target protected project paths.")
    return resolved


def _command_allowed(command: list[str]) -> bool:
    allowed = {
        ("python", "-m", "pytest", "tests/python", "-q"),
        ("python", "-m", "pytest", "-q"),
        ("python", "-m", "pytest", "tests", "-q"),
        ("python", "-m", "ruff", "check", "."),
    }
    return tuple(command) in allowed


def _has_pytest_config(root: Path) -> bool:
    if (root / "pytest.ini").is_file():
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "pytest" in pyproject.read_text(encoding="utf-8", errors="replace").lower()


def _has_python_tests(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(candidate.is_file() for candidate in path.rglob("test_*.py")) or any(
        candidate.is_file() for candidate in path.rglob("*_test.py")
    )


def _has_ruff_config(root: Path) -> bool:
    if (root / "ruff.toml").is_file():
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "ruff" in pyproject.read_text(encoding="utf-8", errors="replace").lower()


def _write_retry_context(run_dir: Path, status: str, failed_commands: list[list[str]]) -> str:
    path = run_dir / "50_project_retry_context.md"
    lines = [
        "# Project Retry Context",
        "",
        f"Verification status: {status}",
        "",
        "## Failed Commands",
        *[f"- {' '.join(command)}" for command in failed_commands],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status in {"FAILED", "TIMEOUT"}:
        (run_dir / "51_project_failure_analysis.md").write_text(
            "# Project Failure Analysis\n\nTests failed or timed out. Inspect stdout/stderr artifacts.\n",
            encoding="utf-8",
        )
        (run_dir / "52_project_retry_recommendation.md").write_text(
            "# Project Retry Recommendation\n\nGenerate a focused retry patch using captured test output.\n",
            encoding="utf-8",
        )
    return str(path)


def _write_status_artifact(run_dir: Path, status: str) -> str:
    if status == "PASSED":
        path = run_dir / "51_project_verification_passed.md"
        path.write_text("# Project Verification Passed\n\nAll executed allowlisted commands passed.\n", encoding="utf-8")
        return str(path)
    if status in {"FAILED", "TIMEOUT"}:
        return str(run_dir / "51_project_failure_analysis.md")
    path = run_dir / "51_project_verification_skipped.md"
    path.write_text(f"# Project Verification {status}\n\nNo tests completed successfully.\n", encoding="utf-8")
    return str(path)


def _write_consensus_action(run_dir: Path, status: str, failed_commands: list[list[str]]) -> tuple[str, str]:
    consensus_path = run_dir / "38_consensus_decision.json"
    action_path = run_dir / "39_action_plan.json"
    consensus = {
        "status": status,
        "consensus_decision": "VERIFY_PASSED" if status == "PASSED" else "VERIFY_NEEDS_REVIEW",
        "confidence": "Medium",
        "failed_commands": failed_commands,
    }
    action = {
        "status": "VALID",
        "recommended_next_action": "review_retry_context" if failed_commands else "review_verification_results",
        "blocked": status in {"FAILED", "TIMEOUT", "BLOCKED"},
        "executable": False,
        "requires_human": True,
        "allowed_actions": ["inspect_artifacts", "prepare_retry_patch"],
        "blocked_actions": ["install_packages", "execute_arbitrary_terminal", "deploy"],
    }
    consensus_path.write_text(json.dumps(consensus, indent=2), encoding="utf-8")
    action_path.write_text(json.dumps(action, indent=2), encoding="utf-8")
    return str(consensus_path), str(action_path)


def _verification_markdown(result: ProjectVerificationResult) -> str:
    lines = [
        "# Project Verification",
        "",
        f"Status: {result.status}",
        f"Duration: {result.duration_seconds}s",
        "",
        "## Commands Executed",
        *[f"- {' '.join(command)}" for command in result.commands_executed],
        "",
        "## Summary",
        result.test_summary,
    ]
    return "\n".join(lines) + "\n"


def _summary(status: str, executed: list[list[str]], failed: list[list[str]]) -> str:
    if status == "SKIPPED":
        return "Verification skipped."
    if status == "BLOCKED":
        return "Verification blocked by safety validation."
    if status == "TIMEOUT":
        return "Verification timed out."
    if status == "FAILED":
        return f"{len(failed)} of {len(executed)} command(s) failed."
    return f"{len(executed)} command(s) passed."


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    return normalized.anchor.lower().replace("\\", "/").startswith("c:")


def _allow_temp_targets(path: Path) -> bool:
    if os.environ.get("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS") != "1":
        return False
    temp = os.environ.get("TEMP")
    if not temp:
        return False
    return _is_relative_to(path, Path(temp).resolve())


def _is_allowed_repo_project_root(root: Path) -> bool:
    allowed_roots = [
        REPO_ROOT / "generated-projects",
        REPO_ROOT / "outputs" / "autonomous_capability_projects",
    ]
    return any(root == allowed.resolve() or _is_relative_to(root, allowed.resolve()) for allowed in allowed_roots)


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result
