"""Approval-gated project scaffolding foundation for ANN v8.3.

This agent materializes only the deterministic starter scaffold proposed by
v8.2 artifacts. It never executes terminal commands, installs packages, applies
patches, or mutates approval tokens.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import (
    ProjectManager,
    normalize_workspace_path,
)


PLAN_BRIEF_JSON = "40_project_creation_brief.json"
PLAN_STRUCTURE_JSON = "41_project_structure_plan.json"
PREVIEW_MD = "42_project_scaffold_preview.md"
PREVIEW_JSON = "42_project_scaffold_preview.json"
APPLY_MD = "43_project_scaffold_apply.md"
APPLY_JSON = "43_project_scaffold_apply.json"
SAFE_RELATIVE_PATTERN = re.compile(r"^[A-Za-z0-9_.\-/]+$")
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
class ProjectScaffoldPreview:
    """Read-only scaffold preview generated from v8.2 project creation artifacts."""

    status: str
    project_name: str
    project_slug: str
    target_root: str
    project_path: str
    folders: list[str]
    files: list[dict[str, str]]
    would_create: list[str]
    would_overwrite: list[str]
    blocked_paths: list[str]
    warnings: list[str]
    validation_errors: list[str]
    artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectScaffoldApplyResult:
    """Result of an approval-gated scaffold apply attempt."""

    status: str
    project_path: str
    folders_created: list[str]
    files_created: list[str]
    files_skipped: list[str]
    files_overwritten: list[str]
    audit_artifact: str
    preview_artifact: str
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def preview_project_scaffold(plan_dir: str | Path) -> ProjectScaffoldPreview:
    """Create scaffold preview artifacts 42 from project creation artifacts 40/41."""

    resolved_plan_dir = _resolve_plan_dir(plan_dir)
    brief, structure = _read_plan_artifacts(resolved_plan_dir)
    preview = _build_preview(resolved_plan_dir, brief, structure)
    artifacts = _write_preview_artifacts(resolved_plan_dir, preview)
    return ProjectScaffoldPreview(**{**preview.to_dict(), "artifacts": artifacts})


def apply_project_scaffold(
    plan_dir: str | Path,
    approval_token: str | None = None,
    confirm_create: bool = False,
    dry_run: bool = True,
) -> ProjectScaffoldApplyResult:
    """Apply the approved scaffold, or produce a dry-run audit.

    Real writes require both confirm_create=True and a token matching
    ANN_PROJECT_SCAFFOLD_TOKEN. Dry-runs create only audit artifacts.
    """

    preview = preview_project_scaffold(plan_dir)
    errors = list(preview.validation_errors)
    warnings = list(preview.warnings)
    folders_created: list[str] = []
    files_created: list[str] = []
    files_skipped: list[str] = []
    files_overwritten: list[str] = []

    if preview.status != "VALID":
        status = "BLOCKED" if preview.status == "BLOCKED" else "INVALID"
        return _write_apply_result(
            plan_dir,
            status=status,
            preview=preview,
            folders_created=folders_created,
            files_created=files_created,
            files_skipped=files_skipped,
            files_overwritten=files_overwritten,
            errors=errors,
            warnings=warnings,
        )

    if dry_run:
        return _write_apply_result(
            plan_dir,
            status="DRY_RUN",
            preview=preview,
            folders_created=folders_created,
            files_created=files_created,
            files_skipped=[*preview.folders, *[item["path"] for item in preview.files]],
            files_overwritten=files_overwritten,
            errors=errors,
            warnings=warnings,
        )

    token_error = _approval_token_error(approval_token)
    if token_error:
        errors.append(token_error)
    if not confirm_create:
        errors.append("confirm_create must be true for real scaffold apply.")
    project_path = Path(preview.project_path).resolve()
    if project_path.exists():
        errors.append("Target project_path already exists; refusing to overwrite by default.")
    if errors:
        return _write_apply_result(
            plan_dir,
            status="BLOCKED",
            preview=preview,
            folders_created=folders_created,
            files_created=files_created,
            files_skipped=[*preview.folders, *[item["path"] for item in preview.files]],
            files_overwritten=files_overwritten,
            errors=errors,
            warnings=warnings,
        )

    for folder in preview.folders:
        target = _safe_project_child(project_path, folder)
        target.mkdir(parents=True, exist_ok=True)
        folders_created.append(str(target))
    project_path.mkdir(parents=True, exist_ok=True)
    for file_entry in preview.files:
        relative_file = file_entry["path"]
        target = _safe_project_child(project_path, relative_file)
        if target.exists():
            files_skipped.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_starter_content(relative_file, file_entry.get("purpose", "")), encoding="utf-8")
        files_created.append(str(target))

    return _write_apply_result(
        plan_dir,
        status="APPLIED",
        preview=preview,
        folders_created=folders_created,
        files_created=files_created,
        files_skipped=files_skipped,
        files_overwritten=files_overwritten,
        errors=errors,
        warnings=warnings,
    )


def _build_preview(
    plan_dir: Path,
    brief: dict[str, Any],
    structure: dict[str, Any],
) -> ProjectScaffoldPreview:
    errors: list[str] = []
    warnings: list[str] = []
    blocked_paths: list[str] = []
    project_name = _string_value(structure, "project_name") or _string_value(brief, "project_name")
    project_slug = _string_value(structure, "project_slug") or _slugify(project_name)
    target_root_raw = _string_value(structure, "target_root") or _string_value(brief, "target_root")
    if not project_name:
        errors.append("project_name is required.")
    if not project_slug or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project_slug):
        errors.append("project_slug is invalid.")
    if not target_root_raw:
        errors.append("target_root is required.")

    target_root = normalize_workspace_path(target_root_raw or ".")
    validation = ProjectManager(allow_temp_paths=_allow_temp_targets()).validate_project_root(target_root_raw)
    if not validation.valid:
        errors.extend(validation.errors)
    warnings.extend(validation.warnings)
    project_path = (target_root / project_slug).resolve()
    if not _is_relative_to(project_path, target_root):
        errors.append("Project path traversal blocked.")
        blocked_paths.append(str(project_path))
    if _has_protected_part(project_path):
        errors.append("Project path is inside a protected ANN directory.")
        blocked_paths.append(str(project_path))

    folders = _safe_relative_list(structure.get("folders_to_create"), blocked_paths)
    files = _safe_file_entries(structure.get("files_to_create"), blocked_paths)
    if blocked_paths:
        errors.append("Plan contains blocked or unsafe scaffold paths.")

    would_create: list[str] = []
    would_overwrite: list[str] = []
    for relative in [*folders, *[item["path"] for item in files]]:
        target = _safe_project_child(project_path, relative)
        if target.exists():
            would_overwrite.append(str(target))
        else:
            would_create.append(str(target))
    if project_path.exists():
        warnings.append("Target project_path already exists; real apply will be blocked by default.")

    status = "VALID"
    if any("blocked" in error.lower() or "protected" in error.lower() for error in errors):
        status = "BLOCKED"
    elif errors:
        status = "INVALID"

    return ProjectScaffoldPreview(
        status=status,
        project_name=project_name,
        project_slug=project_slug,
        target_root=str(target_root),
        project_path=str(project_path),
        folders=folders,
        files=files,
        would_create=would_create,
        would_overwrite=would_overwrite,
        blocked_paths=blocked_paths,
        warnings=_dedupe(warnings),
        validation_errors=_dedupe(errors),
        artifacts=[str(plan_dir / PREVIEW_MD), str(plan_dir / PREVIEW_JSON)],
    )


def _read_plan_artifacts(plan_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    brief_path = plan_dir / PLAN_BRIEF_JSON
    structure_path = plan_dir / PLAN_STRUCTURE_JSON
    if not brief_path.is_file() or not structure_path.is_file():
        raise FileNotFoundError("Plan directory must contain artifacts 40 and 41 JSON files.")
    return _read_json(brief_path), _read_json(structure_path)


def _write_preview_artifacts(plan_dir: Path, preview: ProjectScaffoldPreview) -> list[str]:
    preview_json = plan_dir / PREVIEW_JSON
    preview_md = plan_dir / PREVIEW_MD
    preview_json.write_text(json.dumps(preview.to_dict(), indent=2), encoding="utf-8")
    preview_md.write_text(_preview_markdown(preview), encoding="utf-8")
    return [str(preview_md), str(preview_json)]


def _write_apply_result(
    plan_dir: str | Path,
    *,
    status: str,
    preview: ProjectScaffoldPreview,
    folders_created: list[str],
    files_created: list[str],
    files_skipped: list[str],
    files_overwritten: list[str],
    errors: list[str],
    warnings: list[str],
) -> ProjectScaffoldApplyResult:
    resolved_plan_dir = _resolve_plan_dir(plan_dir)
    apply_json = resolved_plan_dir / APPLY_JSON
    apply_md = resolved_plan_dir / APPLY_MD
    result = ProjectScaffoldApplyResult(
        status=status,
        project_path=preview.project_path,
        folders_created=folders_created,
        files_created=files_created,
        files_skipped=files_skipped,
        files_overwritten=files_overwritten,
        audit_artifact=str(apply_json),
        preview_artifact=str(resolved_plan_dir / PREVIEW_JSON),
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
    )
    apply_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    apply_md.write_text(_apply_markdown(result), encoding="utf-8")
    return result


def _resolve_plan_dir(plan_dir: str | Path) -> Path:
    raw = str(plan_dir)
    if ".." in re.split(r"[\\/]+", raw):
        raise ValueError("Path traversal is not allowed for plan_dir.")
    resolved = Path(plan_dir).resolve()
    if _has_protected_part(resolved):
        raise ValueError("Protected ANN directories cannot be used as plan_dir.")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path.name}")
    return payload


def _safe_relative_list(value: Any, blocked_paths: list[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        relative = str(item).strip()
        if _relative_path_blocked(relative):
            blocked_paths.append(relative)
            continue
        result.append(relative)
    return _dedupe(result)


def _safe_file_entries(value: Any, blocked_paths: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    files: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        relative = str(item.get("path") or "").strip()
        if _relative_path_blocked(relative):
            blocked_paths.append(relative)
            continue
        files.append({"path": relative, "purpose": str(item.get("purpose") or "Starter file").strip()})
    return files


def _relative_path_blocked(relative: str) -> bool:
    if not relative or "\\" in relative or ":" in relative or relative.startswith("/"):
        return True
    if not SAFE_RELATIVE_PATTERN.fullmatch(relative):
        return True
    parts = Path(relative).parts
    return any(part in {"", ".", ".."} or part.lower() in PROTECTED_PARTS for part in parts)


def _safe_project_child(project_path: Path, relative: str) -> Path:
    target = (project_path / relative).resolve()
    if not _is_relative_to(target, project_path):
        raise ValueError("Scaffold path traversal blocked.")
    if _has_protected_part(target.relative_to(project_path)):
        raise ValueError("Protected scaffold path blocked.")
    return target


def _starter_content(relative_file: str, purpose: str) -> str:
    normalized = relative_file.lower()
    if normalized.endswith(".env.example"):
        return "APP_ENV=local\nDATABASE_URL=postgresql://user:password@localhost:5432/app\n"
    if normalized.endswith("readme.md"):
        return f"# Starter Project\n\nPurpose: {purpose or 'Project guide'}.\n\nGenerated by ANN v8.3 scaffold flow.\n"
    if normalized.endswith("package.json"):
        return '{\n  "name": "ann-starter",\n  "version": "0.1.0",\n  "private": true\n}\n'
    if normalized.endswith(".py"):
        return '"""Starter module generated by ANN v8.3 scaffold flow."""\n\n'
    if normalized.endswith(".tsx") or normalized.endswith(".ts"):
        return "// Starter file generated by ANN v8.3 scaffold flow.\n"
    if normalized.endswith(".sql"):
        return "-- Starter schema generated by ANN v8.3 scaffold flow.\n"
    if normalized.endswith(".yml") or normalized.endswith(".yaml"):
        return "# Starter YAML generated by ANN v8.3 scaffold flow.\n"
    return f"Starter file generated by ANN v8.3 scaffold flow.\nPurpose: {purpose}\n"


def _approval_token_error(approval_token: str | None) -> str | None:
    expected = os.environ.get("ANN_PROJECT_SCAFFOLD_TOKEN")
    if not approval_token:
        return "approval_token is required for real scaffold apply."
    if not expected:
        return "ANN_PROJECT_SCAFFOLD_TOKEN must be set for real scaffold apply."
    if approval_token != expected:
        return "approval_token does not match ANN_PROJECT_SCAFFOLD_TOKEN."
    return None


def _preview_markdown(preview: ProjectScaffoldPreview) -> str:
    lines = [
        "# Project Scaffold Preview",
        "",
        f"Status: {preview.status}",
        f"Project: {preview.project_name}",
        f"Project Path: {preview.project_path}",
        "",
        "## Folders",
        *[f"- {folder}" for folder in preview.folders],
        "",
        "## Files",
        *[f"- {item['path']}: {item['purpose']}" for item in preview.files],
        "",
        "## Would Create",
        *[f"- {item}" for item in preview.would_create],
        "",
        "## Would Overwrite",
        *[f"- {item}" for item in preview.would_overwrite],
    ]
    return "\n".join(lines) + "\n"


def _apply_markdown(result: ProjectScaffoldApplyResult) -> str:
    lines = [
        "# Project Scaffold Apply",
        "",
        f"Status: {result.status}",
        f"Project Path: {result.project_path}",
        "",
        "## Folders Created",
        *[f"- {item}" for item in result.folders_created],
        "",
        "## Files Created",
        *[f"- {item}" for item in result.files_created],
        "",
        "## Files Skipped",
        *[f"- {item}" for item in result.files_skipped],
        "",
        "## Validation Errors",
        *[f"- {item}" for item in result.validation_errors],
    ]
    return "\n".join(lines) + "\n"


def _string_value(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ann-project"


def _allow_temp_targets() -> bool:
    return os.environ.get("ANN_ALLOW_TEMP_SCAFFOLD_TARGETS") == "1"


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
