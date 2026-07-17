"""Safe allowlisted terminal execution for ANN.

The Terminal Agent is local-only, deny-by-default, audited, and never uses
``shell=True``. It is intended for controlled test/lint style commands, not
package installation, network access, deployment, or patch application.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agentic_network.safety.filesystem_policy import _canonical_path_key, load_filesystem_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "outputs" / "terminal"
OUTPUTS_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
MAX_CAPTURE_CHARS = 4000
COMMAND_MAX_ARGS = 40
COMMAND_MAX_ARG_LENGTH = 400
STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"
STATUS_TIMEOUT = "TIMEOUT"

NETWORK_COMMANDS = {"curl", "wget", "ssh", "scp"}
INSTALL_COMMANDS = {"install", "add", "update", "upgrade"}
DESTRUCTIVE_COMMANDS = {"rm", "rmdir", "del", "erase", "format", "mkfs"}
SHELL_COMMANDS = {"powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe", "bash", "sh"}
GIT_BLOCKED_SUBCOMMANDS = {"push", "pull", "clone", "fetch"}
PROTECTED_TEXT_PATTERN = re.compile(
    r"(?i)(?:^|[\s\"'])(?:c:[\\/]|/mnt/c\b|\.git\b|models\b|"
    r"training[\\/]datasets\b|training[\\/]adapters\b|memory\b|knowledge\b|"
    r"unsloth_compiled_cache\b)"
)
SECRET_PATTERN = re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*=\s*([^\s]+)")

SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class TerminalResult:
    status: str
    command: list[str]
    cwd: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    blocked_reason: str
    artifact_path: str
    files_modified_detected: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_terminal_command(
    command: list[str],
    cwd: str,
    timeout_seconds: int = 120,
    allow_write: bool = False,
    run_id: str | None = None,
    *,
    subprocess_runner: SubprocessRunner | None = None,
    project_root: Path | None = None,
    artifact_root: Path | None = None,
) -> TerminalResult:
    """Validate, execute, capture, and audit an allowlisted command."""

    started = time.perf_counter()
    root = (project_root or REPO_ROOT).resolve()
    errors, warnings, resolved_cwd = _validate_request(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        allow_write=allow_write,
        run_id=run_id,
        project_root=root,
    )
    artifact_path = _artifact_path(run_id, project_root=root, artifact_root=artifact_root)
    if errors:
        result = TerminalResult(
            status=STATUS_BLOCKED,
            command=_redact_command(command),
            cwd=str(resolved_cwd or cwd),
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=round(time.perf_counter() - started, 3),
            blocked_reason=";".join(errors),
            artifact_path=str(artifact_path),
            files_modified_detected=[],
            validation_errors=errors,
            validation_warnings=warnings,
        )
        _write_artifact(artifact_path, result)
        return result

    before = _snapshot_tree(resolved_cwd) if resolved_cwd else {}
    try:
        runner = subprocess_runner or subprocess.run
        completed = runner(
            _execution_command(command),
            cwd=str(resolved_cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=_safe_env(),
        )
        stdout = _truncate(_redact_text(completed.stdout or ""))
        stderr = _truncate(_redact_text(completed.stderr or ""))
        modified = _modified_files(before, _snapshot_tree(resolved_cwd)) if resolved_cwd else []
        if modified and not allow_write:
            warnings.append("files_modified_detected_without_allow_write")
        result = TerminalResult(
            status=STATUS_PASSED if completed.returncode == 0 else STATUS_FAILED,
            command=_redact_command(command),
            cwd=str(resolved_cwd),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=round(time.perf_counter() - started, 3),
            blocked_reason="",
            artifact_path=str(artifact_path),
            files_modified_detected=modified,
            validation_errors=[],
            validation_warnings=warnings,
        )
    except subprocess.TimeoutExpired as exc:
        result = TerminalResult(
            status=STATUS_TIMEOUT,
            command=_redact_command(command),
            cwd=str(resolved_cwd),
            exit_code=None,
            stdout=_truncate(_redact_text(_to_text(exc.stdout))),
            stderr=_truncate(_redact_text(_to_text(exc.stderr))),
            duration_seconds=round(time.perf_counter() - started, 3),
            blocked_reason="timeout_seconds_exceeded",
            artifact_path=str(artifact_path),
            files_modified_detected=[],
            validation_errors=["timeout_seconds_exceeded"],
            validation_warnings=warnings,
        )
    except OSError as exc:
        result = TerminalResult(
            status=STATUS_FAILED,
            command=_redact_command(command),
            cwd=str(resolved_cwd),
            exit_code=None,
            stdout="",
            stderr=_truncate(_redact_text(str(exc))),
            duration_seconds=round(time.perf_counter() - started, 3),
            blocked_reason="",
            artifact_path=str(artifact_path),
            files_modified_detected=[],
            validation_errors=["command_execution_failed"],
            validation_warnings=warnings,
        )
    _write_artifact(artifact_path, result)
    return result


def _validate_request(
    *,
    command: list[str],
    cwd: str,
    timeout_seconds: int,
    allow_write: bool,
    run_id: str | None,
    project_root: Path,
) -> tuple[list[str], list[str], Path | None]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(command, list) or not command:
        errors.append("command_missing")
    if len(command) > COMMAND_MAX_ARGS:
        errors.append("command_too_long")
    for arg in command:
        if not isinstance(arg, str) or not arg.strip():
            errors.append("command_arg_invalid")
        if len(str(arg)) > COMMAND_MAX_ARG_LENGTH:
            errors.append("command_arg_too_long")
        if PROTECTED_TEXT_PATTERN.search(str(arg)):
            errors.append("protected_path_or_c_drive_reference_present")
    if timeout_seconds <= 0 or timeout_seconds > 600:
        errors.append("timeout_seconds_invalid")
    if allow_write:
        warnings.append("allow_write_requested_but_terminal_agent_does_not_grant_apply_permissions")
    resolved_cwd = _resolve_cwd(cwd, errors, project_root=project_root)
    if run_id is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        errors.append("run_id_invalid")
    if command:
        errors.extend(_validate_command_shape(command))
    return _dedupe(errors), _dedupe(warnings), resolved_cwd


def _resolve_cwd(cwd: str, errors: list[str], *, project_root: Path) -> Path | None:
    if not cwd or ".." in str(cwd).replace("\\", "/").split("/"):
        errors.append("cwd_invalid_or_path_traversal")
        return None
    policy = load_filesystem_policy(project_root=project_root)
    if re.match(r"(?i)^(?:c:[\\/]|/mnt/c\b)", str(cwd).strip()):
        errors.append("cwd_c_drive_blocked")
    resolved = policy.normalize_path(cwd)
    if not policy.is_path_allowed(resolved):
        errors.append("cwd_outside_allowed_roots")
    if policy.is_path_blocked(resolved):
        errors.append("cwd_blocked")
    if policy.is_path_protected(resolved):
        errors.append("cwd_protected")
    if not _is_relative_to(resolved, project_root):
        errors.append("cwd_must_be_inside_repo")
    if not resolved.exists() or not resolved.is_dir():
        errors.append("cwd_missing")
    return resolved


def _validate_command_shape(command: list[str]) -> list[str]:
    executable = _exe(command[0])
    if executable in DESTRUCTIVE_COMMANDS:
        return ["destructive_command_blocked"]
    if executable in NETWORK_COMMANDS:
        return ["network_command_blocked"]
    if executable in SHELL_COMMANDS:
        return ["shell_command_blocked"]
    if executable == "git" and len(command) > 1 and command[1].lower() in GIT_BLOCKED_SUBCOMMANDS:
        return ["git_network_command_blocked"]
    if executable in {"pip", "conda", "npm", "apt", "apt-get"} and any(
        arg.lower() in INSTALL_COMMANDS for arg in command[1:]
    ):
        return ["install_command_blocked"]
    if executable == "ruff":
        return _validate_ruff(command)
    if executable == "pytest":
        return _validate_pytest(command)
    if executable == "python":
        return _validate_python(command)
    return ["command_not_allowlisted"]


def _validate_ruff(command: list[str]) -> list[str]:
    if len(command) >= 2 and command[1] == "check":
        return []
    return ["ruff_command_not_allowlisted"]


def _validate_pytest(command: list[str]) -> list[str]:
    if any(arg.startswith("-") or _safe_relative_arg(arg) for arg in command[1:]):
        return []
    return []


def _validate_python(command: list[str]) -> list[str]:
    if command == ["python", "--version"] or command == ["python", "-V"]:
        return []
    if len(command) >= 3 and command[1] == "-m":
        module = command[2]
        if module == "pytest":
            return []
        if module.startswith("agentic_network."):
            return []
        if module == "pip" and len(command) >= 4 and command[3] == "show":
            return []
    return ["python_command_not_allowlisted"]


def _safe_relative_arg(arg: str) -> bool:
    text = arg.replace("\\", "/")
    return not (text.startswith("/") or ":" in text or ".." in text.split("/"))


def _artifact_path(
    run_id: str | None,
    *,
    project_root: Path,
    artifact_root: Path | None,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    runs_root = project_root / "outputs" / "runs"
    if run_id:
        target = (runs_root / run_id / f"terminal_{stamp}.json").resolve()
        if _is_relative_to(target, runs_root / run_id):
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
    root = (artifact_root or project_root / "outputs" / "terminal").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"terminal_{stamp}.json"


def _execution_command(command: list[str]) -> list[str]:
    if command and _exe(command[0]) == "python":
        return [sys.executable, *command[1:]]
    return command


def _write_artifact(path: Path, result: TerminalResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def _snapshot_tree(cwd: Path) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for path in cwd.rglob("*"):
        if not path.is_file() or _is_skipped_snapshot_path(path):
            continue
        try:
            snapshot[path.relative_to(cwd).as_posix()] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snapshot


def _modified_files(before: dict[str, int], after: dict[str, int]) -> list[str]:
    changed = [path for path, mtime in after.items() if before.get(path) != mtime]
    return sorted(changed)[:100]


def _is_skipped_snapshot_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"})


def _safe_env() -> dict[str, str]:
    safe_keys = {
        "PATH",
        "PATHEXT",
        "PYTHONPATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in safe_keys}
    env.setdefault("PYTHONPATH", ".")
    return env


def _redact_command(command: list[str]) -> list[str]:
    return [_redact_text(arg) for arg in command]


def _redact_text(text: str) -> str:
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


def _truncate(text: str) -> str:
    if len(text) <= MAX_CAPTURE_CHARS:
        return text
    return text[:MAX_CAPTURE_CHARS] + "\n...[truncated]"


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _exe(value: str) -> str:
    return Path(value).name.lower().removesuffix(".exe")


def _is_relative_to(path: Path, parent: Path) -> bool:
    path_key = _canonical_path_key(path)
    parent_key = _canonical_path_key(parent)
    return path_key == parent_key or path_key.startswith(parent_key.rstrip("/") + "/")


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
