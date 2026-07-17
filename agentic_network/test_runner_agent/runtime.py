"""Guarded Test Runner Agent runtime.

This stage never executes tests unless explicitly authorized with run_tests=True.
It detects known test frameworks from repository files and selects only commands
from a fixed allowlist.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Sequence

from agentic_network.safety.filesystem_policy import load_filesystem_policy

TEST_RUN_OUTPUT_FILE = "14_test_run.md"
SUMMARY_FILE = "summary.json"
PROJECT_ROOT = load_filesystem_policy().project_root

STATUS_SKIPPED = "SKIPPED"
STATUS_NO_TESTS_DETECTED = "NO_TESTS_DETECTED"
STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_REJECTED = "REJECTED"

STATUS_LABELS = {
    STATUS_SKIPPED: "Skipped",
    STATUS_NO_TESTS_DETECTED: "No Tests Detected",
    STATUS_PASSED: "Passed",
    STATUS_FAILED: "Failed",
    STATUS_TIMEOUT: "Timeout",
    STATUS_REJECTED: "Rejected",
}

ALLOWED_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("python", "-m", "pytest"),
    ("python", "-m", "unittest"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("go", "test", "./..."),
    ("cargo", "test"),
)
DANGEROUS_TOKENS = {
    "sudo",
    "rm",
    "del",
    "chmod",
    "curl",
    "wget",
    "powershell",
    "pwsh",
    "bash",
    "sh",
}

SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class TestRunnerResult:
    """Structured result for a guarded test runner stage."""

    run_dir: str
    status: str
    artifact_path: str
    detected_frameworks: list[str]
    commands_selected: list[list[str]]
    commands_executed: list[list[str]]
    exit_code: int | None
    duration_seconds: float
    stdout_summary: str
    stderr_summary: str
    warnings: list[str]
    validation_errors: list[str]
    run_tests_flag: bool
    report: str

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def run_tests_for_run(
    run_dir: Path,
    run_tests: bool = False,
    timeout_seconds: int = 300,
    *,
    subprocess_runner: SubprocessRunner | None = None,
    artifact_name: str = TEST_RUN_OUTPUT_FILE,
    summary_prefix: str = "test_runner",
) -> TestRunnerResult:
    """Write a test-run report and optionally execute one allowlisted test command."""

    resolved_run_dir = run_dir.resolve()
    artifact_path = resolved_run_dir / artifact_name
    warnings: list[str] = []
    errors: list[str] = []
    started = perf_counter()
    detected_frameworks = detect_test_frameworks(PROJECT_ROOT)
    selected_commands: list[list[str]] = []
    commands_executed: list[list[str]] = []
    exit_code: int | None = None
    stdout_summary = "None"
    stderr_summary = "None"

    scoped_policy = load_filesystem_policy(
        project_root=PROJECT_ROOT,
        allowed_roots=(PROJECT_ROOT, resolved_run_dir),
    )
    if _touches_forbidden_path(resolved_run_dir, policy=scoped_policy):
        errors.append("run_dir_forbidden_path")
    if _touches_forbidden_path(PROJECT_ROOT, policy=scoped_policy):
        errors.append("project_root_forbidden_path")
    if timeout_seconds <= 0:
        errors.append("timeout_seconds_invalid")

    if not run_tests:
        status = STATUS_SKIPPED
    elif errors:
        status = STATUS_REJECTED
    elif not detected_frameworks:
        status = STATUS_NO_TESTS_DETECTED
    else:
        selected = select_test_command(detected_frameworks)
        selected_commands = [selected] if selected else []
        command_errors = validate_allowed_command(selected)
        if command_errors:
            errors.extend(command_errors)
            status = STATUS_REJECTED
        else:
            runner = subprocess_runner or subprocess.run
            try:
                completed = runner(
                    selected,
                    cwd=_subprocess_cwd(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False,
                )
                commands_executed.append(selected)
                exit_code = int(completed.returncode)
                stdout_summary = _summarize_stream(completed.stdout)
                stderr_summary = _summarize_stream(completed.stderr)
                status = STATUS_PASSED if completed.returncode == 0 else STATUS_FAILED
            except subprocess.TimeoutExpired as exc:
                commands_executed.append(selected)
                status = STATUS_TIMEOUT
                stdout_summary = _summarize_stream(_decode_timeout_stream(exc.stdout))
                stderr_summary = _summarize_stream(_decode_timeout_stream(exc.stderr))
            except OSError as exc:
                errors.append(f"command_execution_failed:{type(exc).__name__}")
                status = STATUS_FAILED

    duration_seconds = round(perf_counter() - started, 3)
    report = _render_report(
        status=status,
        detected_frameworks=detected_frameworks,
        commands_selected=selected_commands,
        commands_executed=commands_executed,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        warnings=warnings,
        errors=errors,
    )
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    result = TestRunnerResult(
        run_dir=str(resolved_run_dir),
        status=status,
        artifact_path=str(artifact_path),
        detected_frameworks=detected_frameworks,
        commands_selected=selected_commands,
        commands_executed=commands_executed,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        warnings=_dedupe(warnings),
        validation_errors=_dedupe(errors),
        run_tests_flag=run_tests,
        report=report,
    )
    _update_summary(resolved_run_dir, result, summary_prefix=summary_prefix)
    return result


def detect_test_frameworks(project_root: Path) -> list[str]:
    """Detect available test frameworks using repository files only."""

    frameworks: list[str] = []
    if any((project_root / name).exists() for name in ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini")) or (project_root / "tests").is_dir():
        frameworks.append("python-pytest")
    if (project_root / "package.json").exists():
        frameworks.append("node-npm")
    if (project_root / "go.mod").exists():
        frameworks.append("go")
    if (project_root / "Cargo.toml").exists():
        frameworks.append("rust-cargo")
    return frameworks


def select_test_command(detected_frameworks: Sequence[str]) -> list[str]:
    """Select one safe test command from detected frameworks."""

    if "python-pytest" in detected_frameworks:
        return ["python", "-m", "pytest"]
    if "node-npm" in detected_frameworks:
        return ["npm", "test"]
    if "go" in detected_frameworks:
        return ["go", "test", "./..."]
    if "rust-cargo" in detected_frameworks:
        return ["cargo", "test"]
    return []


def validate_allowed_command(command: Sequence[str]) -> list[str]:
    """Reject any command outside the static allowlist or containing dangerous tokens."""

    if not command:
        return ["command_missing"]
    command_tuple = tuple(command)
    errors: list[str] = []
    lowered = [part.lower() for part in command]
    if any(part in DANGEROUS_TOKENS for part in lowered):
        errors.append("dangerous_command_rejected")
    if any(_touches_forbidden_path_text(part) for part in command):
        errors.append("forbidden_c_path_present")
    if command_tuple not in ALLOWED_COMMANDS:
        errors.append("command_not_allowlisted")
    return _dedupe(errors)


def test_runner_summary_fields(
    result: TestRunnerResult | None,
    *,
    prefix: str = "test_runner",
) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        f"{prefix}_status": result.status,
        f"{prefix}_artifact": result.artifact_path,
        f"{prefix}_commands_selected": result.commands_selected,
        f"{prefix}_commands_executed": result.commands_executed,
        f"{prefix}_exit_code": result.exit_code,
        f"{prefix}_duration_seconds": result.duration_seconds,
        f"{prefix}_validation_passed": result.validation_passed,
        f"{prefix}_validation_errors": result.validation_errors,
        f"{prefix}_validation_warnings": result.warnings,
        f"{prefix}_run_tests_flag": result.run_tests_flag,
    }


def _render_report(
    *,
    status: str,
    detected_frameworks: list[str],
    commands_selected: list[list[str]],
    commands_executed: list[list[str]],
    exit_code: int | None,
    duration_seconds: float,
    stdout_summary: str,
    stderr_summary: str,
    warnings: list[str],
    errors: list[str],
) -> str:
    summary_items = [
        f"Test Runner Agent completed with status: {STATUS_LABELS[status]}.",
        f"Duration seconds: {duration_seconds}.",
        "No commands were executed." if not commands_executed else "Allowlisted test command execution was requested and completed.",
    ]
    results = [f"Exit code: {exit_code if exit_code is not None else 'None'}."]
    return "\n".join(
        [
            "TEST RUN SUMMARY",
            *_bullets(summary_items),
            "",
            "DETECTED FRAMEWORKS",
            *_bullets(detected_frameworks or ["None"]),
            "",
            "COMMANDS SELECTED",
            *_bullets(_format_commands(commands_selected) or ["None"]),
            "",
            "COMMANDS EXECUTED",
            *_bullets(_format_commands(commands_executed) or ["None"]),
            "",
            "RESULTS",
            *_bullets(results),
            "",
            "STDOUT SUMMARY",
            *_bullets([stdout_summary or "None"]),
            "",
            "STDERR SUMMARY",
            *_bullets([stderr_summary or "None"]),
            "",
            "TEST STATUS",
            STATUS_LABELS[status],
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _format_commands(commands: list[list[str]]) -> list[str]:
    return [" ".join(command) for command in commands]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _summarize_stream(content: str | None, *, max_chars: int = 1200) -> str:
    text = (content or "").strip()
    if not text:
        return "None"
    text = "\n".join(line.rstrip() for line in text.splitlines()[-20:])
    return text[-max_chars:]


def _decode_timeout_stream(content: str | bytes | None) -> str:
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def _load_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / SUMMARY_FILE
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _update_summary(run_dir: Path, result: TestRunnerResult, *, summary_prefix: str) -> None:
    summary = _load_summary(run_dir)
    summary.update(test_runner_summary_fields(result, prefix=summary_prefix))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files[summary_prefix] = result.artifact_path
    (run_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _touches_forbidden_path(path: Path, *, policy: Any | None = None) -> bool:
    return _touches_forbidden_path_text(str(path), policy=policy)


def _touches_forbidden_path_text(text: str, *, policy: Any | None = None) -> bool:
    return (policy or load_filesystem_policy()).is_path_blocked(text)


def _subprocess_cwd(project_root: Path) -> str:
    text = str(project_root).replace("\\", "/")
    if text.startswith("/mnt/"):
        return text
    if text.startswith("//mnt/"):
        return text[1:]
    return str(project_root)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
