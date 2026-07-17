"""Project validation and run discovery for ANN Desktop."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
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
class ValidationResult:
    """Validation result for a proposed local ANN project root."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    runs_path: str | None


@dataclass(frozen=True)
class RunRecord:
    """One discovered ANN run."""

    run_id: str
    path: str
    has_summary: bool
    has_action_plan: bool
    patch_count: int


class ProjectManager:
    """Read-only local project manager for registered ANN workspaces."""

    def __init__(self, *, allow_temp_paths: bool = False) -> None:
        self.allow_temp_paths = allow_temp_paths

    def validate_project_root(self, path: str | Path) -> ValidationResult:
        raw_path = str(path).strip()
        errors: list[str] = []
        warnings: list[str] = []
        if not raw_path:
            return ValidationResult(False, ["Project path is required."], warnings, None)
        if _contains_traversal(raw_path):
            return ValidationResult(False, ["Path traversal is not allowed."], warnings, None)
        normalized = normalize_workspace_path(raw_path)
        if _is_blocked_system_root(raw_path, normalized) and not self._is_allowed_temp_path(normalized):
            errors.append("C: and /mnt/c workspaces are blocked by default.")
        if _has_protected_part(normalized):
            errors.append("Protected ANN directories cannot be registered as projects.")
        if errors:
            return ValidationResult(False, errors, warnings, None)
        runs_path = (normalized / "outputs" / "runs").resolve()
        if not runs_path.exists():
            warnings.append("Project does not contain outputs/runs yet.")
        elif not runs_path.is_dir():
            errors.append("outputs/runs exists but is not a directory.")
        return ValidationResult(not errors, errors, warnings, str(runs_path))

    def discover_runs(self, project: Any) -> list[RunRecord]:
        runs_path = normalize_workspace_path(str(project.runs_path))
        validation = self.validate_project_root(str(project.root_path))
        if not validation.valid:
            return []
        if not _is_relative_to(runs_path, normalize_workspace_path(str(project.root_path))):
            return []
        if not runs_path.is_dir():
            return []
        records = [self._run_record(path) for path in runs_path.iterdir() if self._is_run_dir(path)]
        return sorted(records, key=lambda record: record.run_id, reverse=True)

    def summarize_project(self, project: Any) -> dict[str, Any]:
        validation = self.validate_project_root(str(project.root_path))
        runs = self.discover_runs(project) if validation.valid else []
        return {
            "project_id": str(project.project_id),
            "name": str(project.name),
            "root_path": str(project.root_path),
            "runs_path": str(project.runs_path),
            "is_active": bool(project.is_active),
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "run_count": len(runs),
            "latest_run_id": runs[0].run_id if runs else None,
        }

    def _run_record(self, run_dir: Path) -> RunRecord:
        patches_dir = run_dir / "patches"
        patch_count = 0
        if patches_dir.is_dir():
            patch_count = sum(
                1
                for path in patches_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".diff", ".patch"}
            )
        return RunRecord(
            run_id=run_dir.name,
            path=str(run_dir.resolve()),
            has_summary=(run_dir / "summary.json").is_file(),
            has_action_plan=(run_dir / "39_action_plan.json").is_file(),
            patch_count=patch_count,
        )

    def _is_run_dir(self, path: Path) -> bool:
        return path.is_dir() and bool(RUN_ID_PATTERN.fullmatch(path.name)) and (
            (path / "summary.json").is_file() or (path / "patches").is_dir()
        )

    def _is_allowed_temp_path(self, path: Path) -> bool:
        if not self.allow_temp_paths:
            return False
        return _is_relative_to(path, Path(tempfile.gettempdir()).resolve())


def normalize_workspace_path(path: str | Path) -> Path:
    """Normalize Windows and WSL-style project paths without requiring existence."""

    raw = str(path).strip()
    unix_like = raw.replace("\\", "/")
    match = re.match(r"^/?mnt/([A-Za-z])(?:/(.*))?$", unix_like)
    if match:
        drive = match.group(1).upper()
        rest = (match.group(2) or "").replace("/", "\\")
        raw = f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return Path(raw).expanduser().resolve()


def _contains_traversal(path: str) -> bool:
    parts = re.split(r"[\\/]+", path)
    return any(part == ".." for part in parts)


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    anchor = normalized.anchor.lower().replace("\\", "/")
    return anchor.startswith("c:")


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
