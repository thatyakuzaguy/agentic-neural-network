"""Approval-gated patch application for generated projects.

This agent applies project patches only inside the selected project_root. It is
independent from ANN core Patch Apply and never executes terminal commands,
installs dependencies, or uses network access.
"""

from __future__ import annotations

import json
import os
import re
import shutil
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
class ProjectPatchApplyResult:
    """Result of a project patch apply attempt."""

    status: str
    project_root: str
    patch_file: str
    files_modified: list[str]
    backups_created: list[str]
    files_skipped: list[str]
    test_commands: list[str]
    test_results: dict[str, Any]
    self_healing_triggered: bool
    retry_patch_generated: str | None
    consensus: dict[str, Any]
    next_action: str
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectPatchRollbackResult:
    """Result of restoring files from a project patch backup."""

    status: str
    project_root: str
    backup_dir: str
    files_restored: list[str]
    files_removed: list[str]
    validation_errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchFileChange:
    """A single file change parsed from a safe unified diff."""

    old_path: str | None
    new_path: str
    content: str
    is_new_file: bool


def apply_project_patch(
    project_root: str | Path,
    patch_file: str | Path,
    approval_token: str | None = None,
    confirm_apply: bool = False,
    backup: bool = True,
    dry_run: bool = True,
) -> ProjectPatchApplyResult:
    """Apply or preview one generated project patch."""

    root = normalize_workspace_path(project_root)
    patch_path = _resolve_patch_path(root, patch_file)
    errors, warnings = _validate_project_root(project_root, root)
    if patch_path is None:
        errors.append("patch_file is required.")
        patch_path_display = ""
    else:
        patch_path_display = str(patch_path)
        if not patch_path.is_file():
            errors.append("patch_file was not found.")
        elif not _is_relative_to(patch_path.resolve(), root):
            errors.append("patch_file must be inside project_root.")
    changes: list[PatchFileChange] = []
    if not errors and patch_path is not None:
        try:
            changes = _parse_patch(patch_path.read_text(encoding="utf-8", errors="replace"))
        except ValueError as exc:
            errors.append(str(exc))
    blocked_paths = _blocked_change_paths(root, changes)
    errors.extend(blocked_paths)
    test_commands = _test_commands_for(root)
    files = [_safe_project_child(root, change.new_path) for change in changes if not errors]

    if dry_run:
        status = "BLOCKED" if _blocked(errors) else ("FAILED" if errors else "DRY_RUN")
        return _result(
            status=status,
            root=root,
            patch_path=patch_path_display,
            files_modified=[],
            backups_created=[],
            files_skipped=[str(path) for path in files],
            test_commands=test_commands,
            errors=errors,
            warnings=warnings,
            retry_patch_generated=None,
        )

    token_error = _approval_token_error(approval_token)
    if token_error:
        errors.append(token_error)
    if not confirm_apply:
        errors.append("confirm_apply must be true for real project patch apply.")
    if errors:
        retry_patch = _write_retry_patch(root, patch_path, errors) if patch_path else None
        return _result(
            status="BLOCKED" if _blocked(errors) else "FAILED",
            root=root,
            patch_path=patch_path_display,
            files_modified=[],
            backups_created=[],
            files_skipped=[str(path) for path in files],
            test_commands=test_commands,
            errors=errors,
            warnings=warnings,
            retry_patch_generated=retry_patch,
        )

    backup_dir = _create_backup(root, patch_path, changes) if backup and patch_path is not None else None
    files_modified: list[str] = []
    files_skipped: list[str] = []
    for change in changes:
        target = _safe_project_child(root, change.new_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.content, encoding="utf-8")
        files_modified.append(str(target))
    if backup_dir is not None:
        _capture_new_files(backup_dir, root, changes)
    _write_project_review_artifacts(root, status="APPLIED", patch_path=patch_path_display)
    return _result(
        status="APPLIED",
        root=root,
        patch_path=patch_path_display,
        files_modified=files_modified,
        backups_created=[str(backup_dir)] if backup_dir is not None else [],
        files_skipped=files_skipped,
        test_commands=test_commands,
        errors=[],
        warnings=warnings,
        retry_patch_generated=None,
    )


def rollback_project_patch(
    backup_dir: str | Path,
    confirm_rollback: bool = False,
) -> ProjectPatchRollbackResult:
    """Restore files from a backup created by apply_project_patch."""

    resolved_backup = Path(backup_dir).resolve()
    manifest_path = resolved_backup / "manifest.json"
    errors: list[str] = []
    if not confirm_rollback:
        errors.append("confirm_rollback must be true.")
    if not manifest_path.is_file():
        errors.append("Backup manifest not found.")
        return ProjectPatchRollbackResult("BLOCKED", "", str(resolved_backup), [], [], errors)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(str(manifest.get("project_root") or "")).resolve()
    root_errors, _warnings = _validate_project_root(str(root), root)
    errors.extend(root_errors)
    if errors:
        return ProjectPatchRollbackResult("BLOCKED", str(root), str(resolved_backup), [], [], errors)
    restored: list[str] = []
    removed: list[str] = []
    for item in manifest.get("files", []):
        if not isinstance(item, dict):
            continue
        relative = str(item.get("relative") or "")
        target = _safe_project_child(root, relative)
        original = resolved_backup / "original" / relative
        if item.get("existed") is True and original.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            restored.append(str(target))
        elif target.exists():
            target.unlink()
            removed.append(str(target))
    return ProjectPatchRollbackResult("ROLLED_BACK", str(root), str(resolved_backup), restored, removed, [])


def _parse_patch(text: str) -> list[PatchFileChange]:
    changes: list[PatchFileChange] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("diff --git "):
            index += 1
            continue
        parts = line.split()
        if len(parts) < 4:
            raise ValueError("Invalid diff header.")
        old_path = _strip_diff_prefix(parts[2])
        new_path = _strip_diff_prefix(parts[3])
        is_new = False
        content: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith("diff --git "):
            current = lines[index]
            if current.startswith("new file mode") or current == "--- /dev/null":
                is_new = True
            elif current.startswith("+") and not current.startswith("+++ "):
                content.append(current[1:])
            elif current.startswith(" ") and not is_new:
                content.append(current[1:])
            index += 1
        if not new_path:
            raise ValueError("Patch target path is missing.")
        changes.append(PatchFileChange(old_path=old_path, new_path=new_path, content="\n".join(content) + "\n", is_new_file=is_new))
    if not changes:
        raise ValueError("No supported file changes found in patch.")
    return changes


def _strip_diff_prefix(value: str) -> str:
    if value in {"/dev/null", "dev/null"}:
        return ""
    if value.startswith("a/") or value.startswith("b/"):
        return value[2:]
    return value


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
        errors.append("Protected ANN directories cannot be patched.")
    if (root == REPO_ROOT or _is_relative_to(root, REPO_ROOT)) and not _is_allowed_repo_project_root(root):
        errors.append("ANN repository cannot be patched by Project Patch Apply.")
    if not root.exists():
        errors.append("project_root must exist.")
    elif not root.is_dir():
        errors.append("project_root must be a directory.")
    return errors, warnings


def _resolve_patch_path(root: Path, patch_file: str | Path) -> Path | None:
    if not str(patch_file).strip():
        return None
    raw = str(patch_file)
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        return Path(raw).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _is_allowed_repo_project_root(root: Path) -> bool:
    allowed_roots = [
        REPO_ROOT / "generated-projects",
        REPO_ROOT / "outputs" / "autonomous_capability_projects",
    ]
    return any(root == allowed.resolve() or _is_relative_to(root, allowed.resolve()) for allowed in allowed_roots)


def _blocked_change_paths(root: Path, changes: list[PatchFileChange]) -> list[str]:
    errors: list[str] = []
    for change in changes:
        relative = change.new_path
        if _relative_path_blocked(relative):
            errors.append(f"Patch path is blocked: {relative}")
            continue
        try:
            target = _safe_project_child(root, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not _is_relative_to(target, root):
            errors.append(f"Patch target leaves project_root: {relative}")
    return errors


def _relative_path_blocked(relative: str) -> bool:
    if not relative or relative.startswith("/") or "\\" in relative or ":" in relative:
        return True
    parts = Path(relative).parts
    return any(part in {"", ".", ".."} or part.lower() in PROTECTED_PARTS for part in parts)


def _safe_project_child(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not _is_relative_to(target, root):
        raise ValueError("Patch target path traversal blocked.")
    if _has_protected_part(target.relative_to(root)):
        raise ValueError("Protected project patch path blocked.")
    return target


def _create_backup(root: Path, patch_path: Path, changes: list[PatchFileChange]) -> Path:
    backup_dir = root / "project_backups" / f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    original_root = backup_dir / "original"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(patch_path, backup_dir / "patch_applied.diff")
    manifest_files: list[dict[str, Any]] = []
    for change in changes:
        target = _safe_project_child(root, change.new_path)
        existed = target.exists()
        manifest_files.append({"relative": change.new_path, "existed": existed})
        if existed and target.is_file():
            backup_target = original_root / change.new_path
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
    manifest = {"project_root": str(root), "patch_file": str(patch_path), "files": manifest_files}
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup_dir


def _capture_new_files(backup_dir: Path, root: Path, changes: list[PatchFileChange]) -> None:
    new_root = backup_dir / "new"
    for change in changes:
        target = _safe_project_child(root, change.new_path)
        if target.is_file():
            backup_target = new_root / change.new_path
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)


def _write_project_review_artifacts(root: Path, *, status: str, patch_path: str) -> None:
    run_dir = root / "outputs" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_patch_apply")
    run_dir.mkdir(parents=True, exist_ok=True)
    consensus = {
        "status": "PASSED" if status == "APPLIED" else status,
        "consensus_decision": "PATCH_APPLIED_REVIEW_TESTS_SKIPPED",
        "confidence": "Medium",
        "patch_file": patch_path,
    }
    action = {
        "status": "VALID",
        "recommended_next_action": "run_project_tests_or_review_patch",
        "blocked": False,
        "executable": False,
        "requires_human": True,
        "blocked_actions": ["install_packages", "execute_terminal", "deploy"],
        "allowed_actions": ["inspect_backup", "rollback", "review_project_patch"],
    }
    (run_dir / "38_consensus_decision.json").write_text(json.dumps(consensus, indent=2), encoding="utf-8")
    (run_dir / "39_action_plan.json").write_text(json.dumps(action, indent=2), encoding="utf-8")


def _write_retry_patch(root: Path, patch_path: Path | None, errors: list[str]) -> str | None:
    retry_dir = root / "outputs" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_retry")
    retry_dir.mkdir(parents=True, exist_ok=True)
    retry_patch = retry_dir / "retry_patch_001.diff"
    retry_patch.write_text(
        "\n".join(
            [
                "# Retry patch placeholder generated by ANN v8.5",
                f"# Original patch: {patch_path or 'unknown'}",
                "# Reasons:",
                *[f"# - {error}" for error in errors],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(retry_patch)


def _result(
    *,
    status: str,
    root: Path,
    patch_path: str,
    files_modified: list[str],
    backups_created: list[str],
    files_skipped: list[str],
    test_commands: list[str],
    errors: list[str],
    warnings: list[str],
    retry_patch_generated: str | None,
) -> ProjectPatchApplyResult:
    consensus = {
        "status": "PASSED" if status in {"APPLIED", "DRY_RUN"} else status,
        "consensus_decision": "PROJECT_PATCH_REVIEW_REQUIRED" if status == "DRY_RUN" else status,
        "confidence": "Medium",
        "terminal_execution": False,
        "package_installation": False,
        "network": False,
        "patch_apply": status == "APPLIED",
    }
    return ProjectPatchApplyResult(
        status=status,
        project_root=str(root),
        patch_file=patch_path,
        files_modified=files_modified,
        backups_created=backups_created,
        files_skipped=files_skipped,
        test_commands=test_commands,
        test_results={"status": "SKIPPED", "reason": "No terminal execution in v8.5 foundation."},
        self_healing_triggered=bool(errors),
        retry_patch_generated=retry_patch_generated,
        consensus=consensus,
        next_action="review_and_run_project_tests" if status == "APPLIED" else "review_project_patch",
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
    )


def _test_commands_for(root: Path) -> list[str]:
    commands: list[str] = []
    if (root / "package.json").exists() or (root / "apps" / "web" / "package.json").exists():
        commands.append("npm test")
    if (root / "pyproject.toml").exists() or (root / "apps" / "api").exists():
        commands.append("pytest")
    return commands


def _approval_token_error(approval_token: str | None) -> str | None:
    expected = os.environ.get("ANN_PROJECT_PATCH_TOKEN")
    if not approval_token:
        return "approval_token is required for real project patch apply."
    if not expected:
        return "ANN_PROJECT_PATCH_TOKEN must be set for real project patch apply."
    if approval_token != expected:
        return "approval_token does not match ANN_PROJECT_PATCH_TOKEN."
    return None


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    return normalized.anchor.lower().replace("\\", "/").startswith("c:")


def _allow_temp_targets(path: Path) -> bool:
    if os.environ.get("ANN_ALLOW_TEMP_PROJECT_PATCH_TARGETS") != "1":
        return False
    temp = os.environ.get("TEMP")
    if not temp:
        return False
    return _is_relative_to(path, Path(temp).resolve())


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _blocked(errors: list[str]) -> bool:
    return any(
        "blocked" in error.lower()
        or "protected" in error.lower()
        or "approval_token" in error.lower()
        or "confirm_apply" in error.lower()
        or "ann repository" in error.lower()
        or "traversal" in error.lower()
        for error in errors
    )


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
