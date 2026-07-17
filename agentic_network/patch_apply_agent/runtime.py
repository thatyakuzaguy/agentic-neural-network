"""Patch Apply Agent runtime.

This stage is the first ANN stage that can modify repository files, but it is
locked by explicit approval flags and prior Patch Approval Agent validation. By
default it writes only an audit artifact and performs no repository writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.pipeline.parallel_gate_runtime import evaluate_parallel_review_gate
from agentic_network.safety.filesystem_policy import _canonical_path_key, load_filesystem_policy

PATCH_APPLY_OUTPUT_FILE = "13_patch_apply.md"
PATCHES_DIR = "patches"
BACKUPS_DIR = "backups"
SUMMARY_FILE = "summary.json"
HUMAN_APPROVAL_FILE = "16_human_approval.md"

APPLY_STATUS_SKIPPED = "SKIPPED"
APPLY_STATUS_REJECTED = "REJECTED"
APPLY_STATUS_DRY_RUN_PASSED = "DRY_RUN_PASSED"
APPLY_STATUS_DRY_RUN_FAILED = "DRY_RUN_FAILED"
APPLY_STATUS_APPLIED = "APPLIED"
APPLY_STATUS_FAILED = "FAILED"

STATUS_LABELS = {
    APPLY_STATUS_SKIPPED: "Skipped",
    APPLY_STATUS_REJECTED: "Rejected",
    APPLY_STATUS_DRY_RUN_PASSED: "Dry Run Passed",
    APPLY_STATUS_DRY_RUN_FAILED: "Dry Run Failed",
    APPLY_STATUS_APPLIED: "Applied",
    APPLY_STATUS_FAILED: "Failed",
}

FORBIDDEN_C_PATH_PATTERN = re.compile(r"(?i)(?:^|[\s:+-])(?:/mnt/c\b|[A-Z]:\\)")
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\()"
)
SHELL_SCRIPT_PATTERN = re.compile(
    r"(?m)^\s*#!\s*/(?:usr/bin/env\s+)?(?:bash|sh|zsh|powershell|pwsh)\b"
)
DIFF_HEADER = re.compile(r"^(---|\+\+\+)\s+(.+?)\s*$")
HUNK_HEADER = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

@dataclass(frozen=True)
class PatchApplyResult:
    """Structured result for an approved patch application attempt."""

    run_dir: str
    status: str
    artifact_path: str
    patch_paths: list[str]
    files_modified: list[str]
    backups_created: list[str]
    warnings: list[str]
    validation_errors: list[str]
    dry_run: bool
    approved_flag: bool
    report: str

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


@dataclass(frozen=True)
class _FilePatch:
    patch_path: Path
    target_path: Path
    old_path_text: str
    new_path_text: str
    hunks: list[list[str]]


@dataclass(frozen=True)
class _PreparedChange:
    target_path: Path
    old_text: str
    new_text: str


def apply_approved_patches(
    run_dir: Path,
    approve_patches: bool = False,
    dry_run: bool = True,
    *,
    patch_dir: str = PATCHES_DIR,
    output_artifact: str = PATCH_APPLY_OUTPUT_FILE,
    human_approval_artifact: str = HUMAN_APPROVAL_FILE,
    summary_prefix: str = "patch_apply",
    approval_decision_key: str = "patch_approval_decision",
    approval_validation_key: str = "patch_approval_validation_passed",
    human_decision_key: str = "human_approval_decision",
    human_validation_key: str = "human_approval_validation_passed",
) -> PatchApplyResult:
    """Validate and optionally apply approved patch proposals from a run directory."""

    resolved_run_dir = run_dir.resolve()
    artifact_path = resolved_run_dir / output_artifact
    warnings: list[str] = []
    errors: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    parallel_gate = evaluate_parallel_review_gate(resolved_run_dir)
    patch_paths = sorted((resolved_run_dir / patch_dir).glob("*.diff"))
    patch_path_strings = [str(path) for path in patch_paths]
    files_modified: list[str] = []
    backups_created: list[str] = []

    approval_errors = _approval_errors(
        summary=summary,
        approve_patches=approve_patches,
        approval_decision_key=approval_decision_key,
        approval_validation_key=approval_validation_key,
        parallel_gate=parallel_gate,
        retry_mode=summary_prefix.startswith("retry_") or patch_dir == "retry_patches",
    )
    if not dry_run and approve_patches:
        approval_errors.extend(
            _human_approval_errors(
                resolved_run_dir,
                summary,
                human_approval_artifact=human_approval_artifact,
                human_decision_key=human_decision_key,
                human_validation_key=human_validation_key,
            )
        )
    approval_errors = _dedupe(approval_errors)
    if approval_errors:
        status = APPLY_STATUS_SKIPPED if "approve_patches_flag_missing" in approval_errors else APPLY_STATUS_REJECTED
        errors.extend(approval_errors)
        report = _render_report(
            status=status,
            approval_items=_approval_items(
                summary,
                approve_patches,
                dry_run=dry_run,
                approval_decision_key=approval_decision_key,
                approval_validation_key=approval_validation_key,
                human_decision_key=human_decision_key,
                human_validation_key=human_validation_key,
                parallel_gate=parallel_gate,
            ),
            patches_processed=[path.name for path in patch_paths] or ["None"],
            files_modified=files_modified,
            backups_created=backups_created,
            warnings=warnings,
            errors=errors,
            dry_run=dry_run,
        )
        artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
        result = _result(
            resolved_run_dir,
            status,
            artifact_path,
            patch_path_strings,
            files_modified,
            backups_created,
            warnings,
            errors,
            dry_run,
            approve_patches,
            report,
        )
        _update_summary(resolved_run_dir, result, summary_prefix=summary_prefix)
        return result

    if not patch_paths:
        errors.append("patch_files_missing")

    try:
        prepared = _prepare_changes(
            run_dir=resolved_run_dir,
            patch_paths=patch_paths,
            project_root=_project_root(),
            warnings=warnings,
            patch_dir=patch_dir,
        )
    except ValueError as exc:
        errors.extend(str(exc).split("|"))
        prepared = []

    if errors:
        status = APPLY_STATUS_DRY_RUN_FAILED if dry_run else APPLY_STATUS_FAILED
    elif dry_run:
        status = APPLY_STATUS_DRY_RUN_PASSED
        files_modified = [str(change.target_path) for change in prepared]
    else:
        try:
            backups_created = _apply_prepared_changes(resolved_run_dir, prepared)
            files_modified = [str(change.target_path) for change in prepared]
            status = APPLY_STATUS_APPLIED
        except OSError as exc:
            errors.append(f"write_failed:{type(exc).__name__}")
            status = APPLY_STATUS_FAILED

    report = _render_report(
        status=status,
        approval_items=_approval_items(
            summary,
            approve_patches,
            dry_run=dry_run,
            approval_decision_key=approval_decision_key,
            approval_validation_key=approval_validation_key,
            human_decision_key=human_decision_key,
            human_validation_key=human_validation_key,
            parallel_gate=parallel_gate,
        ),
        patches_processed=[path.name for path in patch_paths] or ["None"],
        files_modified=files_modified,
        backups_created=backups_created,
        warnings=warnings,
        errors=errors,
        dry_run=dry_run,
    )
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    result = _result(
        resolved_run_dir,
        status,
        artifact_path,
        patch_path_strings,
        files_modified,
        backups_created,
        warnings,
        errors,
        dry_run,
        approve_patches,
        report,
    )
    _update_summary(resolved_run_dir, result, summary_prefix=summary_prefix)
    return result


def _result(
    run_dir: Path,
    status: str,
    artifact_path: Path,
    patch_paths: list[str],
    files_modified: list[str],
    backups_created: list[str],
    warnings: list[str],
    errors: list[str],
    dry_run: bool,
    approved_flag: bool,
    report: str,
) -> PatchApplyResult:
    return PatchApplyResult(
        run_dir=str(run_dir),
        status=status,
        artifact_path=str(artifact_path),
        patch_paths=patch_paths,
        files_modified=files_modified,
        backups_created=backups_created,
        warnings=_dedupe(warnings),
        validation_errors=_dedupe(errors),
        dry_run=dry_run,
        approved_flag=approved_flag,
        report=report,
    )


def _approval_errors(
    *,
    summary: dict[str, Any],
    approve_patches: bool,
    approval_decision_key: str,
    approval_validation_key: str,
    parallel_gate: Any,
    retry_mode: bool,
) -> list[str]:
    errors: list[str] = []
    if not approve_patches:
        errors.append("approve_patches_flag_missing")
    if str(summary.get("final_decision") or "").strip() != "Approved":
        errors.append("final_decision_not_approved")
    if str(summary.get(approval_decision_key) or "").strip() != "Approved":
        errors.append("patch_approval_decision_not_approved")
    if summary.get(approval_validation_key) is not True:
        errors.append("patch_approval_validation_not_passed")
    if parallel_gate.blocks_patch_apply and not (
        retry_mode and parallel_gate.decision == "NEEDS_REVISION"
    ):
        errors.append(f"parallel_review_gate_blocks_patch_apply:{parallel_gate.decision}")
    errors.extend(parallel_gate.validation_errors)
    return _dedupe(errors)


def _approval_items(
    summary: dict[str, Any],
    approve_patches: bool,
    *,
    dry_run: bool,
    approval_decision_key: str,
    approval_validation_key: str,
    human_decision_key: str,
    human_validation_key: str,
    parallel_gate: Any,
) -> list[str]:
    items = [
        f"Explicit approval flag: {'present' if approve_patches else 'missing'}.",
        f"Final decision: {summary.get('final_decision', 'Unknown')}.",
        f"Patch approval decision: {summary.get(approval_decision_key, 'Unknown')}.",
        f"Patch approval validation passed: {summary.get(approval_validation_key, False)}.",
        f"Parallel Review Gate decision: {parallel_gate.decision}.",
        f"Parallel Review Gate blocks patch apply: {parallel_gate.blocks_patch_apply}.",
    ]
    if dry_run:
        items.append("Human approval required for real apply: no.")
    else:
        items.extend(
            [
                "Human approval required for real apply: yes.",
                f"Human approval decision: {summary.get(human_decision_key, 'Unknown')}.",
                f"Human approval validation passed: {summary.get(human_validation_key, False)}.",
            ]
        )
    return items


def _human_approval_errors(
    run_dir: Path,
    summary: dict[str, Any],
    *,
    human_approval_artifact: str,
    human_decision_key: str,
    human_validation_key: str,
) -> list[str]:
    errors: list[str] = []
    if str(summary.get(human_decision_key) or "").strip() != "Approved":
        errors.append("human_approval_not_approved")
    if summary.get(human_validation_key) is not True:
        errors.append("human_approval_validation_failed")
    artifact_path = run_dir / human_approval_artifact
    if not artifact_path.exists():
        errors.append("human_approval_artifact_missing")
        return _dedupe(errors)
    try:
        content = artifact_path.read_text(encoding="utf-8")
    except OSError:
        errors.append("human_approval_artifact_unreadable")
        return _dedupe(errors)
    if _authorization_decision_from_artifact(content) != "Approved":
        errors.append("human_approval_artifact_not_approved")
    return _dedupe(errors)


def _authorization_decision_from_artifact(content: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip().upper() == "AUTHORIZATION DECISION":
            for candidate in lines[index + 1 :]:
                value = candidate.strip().lstrip("- ").strip()
                if value:
                    return value
    return "Unknown"

def _prepare_changes(
    *,
    run_dir: Path,
    patch_paths: list[Path],
    project_root: Path,
    warnings: list[str],
    patch_dir: str,
) -> list[_PreparedChange]:
    errors: list[str] = []
    file_patches: list[_FilePatch] = []
    for patch_path in patch_paths:
        resolved_patch_path = patch_path.resolve()
        if not _is_relative_to(resolved_patch_path, run_dir / patch_dir):
            errors.append(f"patch_file_outside_{patch_dir}_dir:{patch_path}")
            continue
        patch_text = patch_path.read_text(encoding="utf-8")
        if FORBIDDEN_C_PATH_PATTERN.search(patch_text):
            errors.append("forbidden_c_path_present")
        if FORBIDDEN_COMMAND_PATTERN.search(patch_text):
            errors.append("dangerous_command_present")
        if SHELL_SCRIPT_PATTERN.search(patch_text):
            errors.append("shell_script_present")
        try:
            file_patches.extend(_parse_patch_file(patch_path, patch_text, project_root))
        except ValueError as exc:
            errors.extend(str(exc).split("|"))
    if errors:
        raise ValueError("|".join(_dedupe(errors)))
    if patch_paths and not file_patches:
        raise ValueError("malformed_patch_no_file_headers")

    prepared: list[_PreparedChange] = []
    seen_targets: set[Path] = set()
    for file_patch in file_patches:
        if file_patch.target_path in seen_targets:
            errors.append(f"duplicate_patch_target:{file_patch.target_path}")
            continue
        seen_targets.add(file_patch.target_path)
        try:
            old_text = file_patch.target_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            old_text = ""
            warnings.append(f"target_file_will_be_created:{file_patch.target_path}")
        except UnicodeDecodeError:
            errors.append(f"target_file_not_utf8:{file_patch.target_path}")
            continue
        try:
            new_text = _apply_hunks(old_text, file_patch.hunks)
        except ValueError as exc:
            errors.append(f"patch_does_not_apply:{file_patch.target_path}:{exc}")
            continue
        prepared.append(_PreparedChange(file_patch.target_path, old_text, new_text))
    if errors:
        raise ValueError("|".join(_dedupe(errors)))
    return prepared


def _parse_patch_file(patch_path: Path, patch_text: str, project_root: Path) -> list[_FilePatch]:
    lines = patch_text.splitlines()
    patches: list[_FilePatch] = []
    errors: list[str] = []
    index = 0
    while index < len(lines):
        old_path: str | None = None
        while index < len(lines):
            match = DIFF_HEADER.match(lines[index])
            if match and match.group(1) == "---":
                old_path = match.group(2).strip()
                index += 1
                break
            index += 1
        if old_path is None:
            break
        if index >= len(lines):
            errors.append(f"patch_missing_new_header:{patch_path.name}")
            break
        match = DIFF_HEADER.match(lines[index])
        if not match or match.group(1) != "+++":
            errors.append(f"patch_missing_new_header:{patch_path.name}")
            break
        new_path = match.group(2).strip()
        index += 1
        target_text = new_path if new_path != "/dev/null" else old_path
        if target_text == "/dev/null":
            errors.append(f"patch_deletion_not_supported:{patch_path.name}")
            continue
        target_path, path_error = _resolve_target_path(target_text, project_root)
        if path_error:
            errors.append(path_error)
            target_path = project_root / "__invalid_patch_target__"
        hunks: list[list[str]] = []
        while index < len(lines):
            if DIFF_HEADER.match(lines[index]) and lines[index].startswith("---"):
                break
            if HUNK_HEADER.match(lines[index]):
                hunk: list[str] = [lines[index]]
                index += 1
                while index < len(lines):
                    if HUNK_HEADER.match(lines[index]):
                        break
                    if DIFF_HEADER.match(lines[index]) and lines[index].startswith("---"):
                        break
                    hunk.append(lines[index])
                    index += 1
                hunks.append(hunk)
                continue
            index += 1
        if not hunks:
            errors.append(f"patch_hunks_missing:{patch_path.name}")
        elif not path_error:
            patches.append(_FilePatch(patch_path, target_path, old_path, new_path, hunks))
    if errors:
        raise ValueError("|".join(_dedupe(errors)))
    return patches


def _resolve_target_path(path_text: str, project_root: Path) -> tuple[Path, str | None]:
    normalized = _normalize_diff_path(path_text)
    if not normalized:
        return project_root / "__invalid_patch_target__", f"patch_target_invalid:{path_text}"
    if normalized in {"old", "new"}:
        return project_root / "__invalid_patch_target__", f"patch_target_not_repository_file:{normalized}"
    policy = load_filesystem_policy(project_root=project_root)
    raw_path = Path(normalized)
    target_path = policy.normalize_path(raw_path if raw_path.is_absolute() else normalized)
    if not _is_relative_to(target_path, project_root):
        return target_path, f"patch_target_outside_project_root:{normalized}"
    policy_errors = policy.validate_patch_target(target_path)
    for error in policy_errors:
        if error.startswith("protected_path_modified:") or error == "forbidden_c_path_present":
            return target_path, error
        if error.startswith(("path_outside_allowed_roots:", "blocked_path:", "external_path_approval_required:", "path_traversal_present:")):
            return target_path, error
    return target_path, None


def _normalize_diff_path(path_text: str) -> str:
    text = path_text.strip().strip('"').strip("'")
    if "\t" in text:
        text = text.split("\t", 1)[0]
    if text.startswith(("a/", "b/")):
        text = text[2:]
    return text.strip()


def _protected_path_error(path: Path, project_root: Path) -> str | None:
    errors = load_filesystem_policy(project_root=project_root).validate_patch_target(path)
    for error in errors:
        if error.startswith("protected_path_modified:"):
            return error
    return None


def _apply_hunks(old_text: str, hunks: list[list[str]]) -> str:
    original_lines = old_text.splitlines(keepends=True)
    result: list[str] = []
    source_index = 0
    for hunk in hunks:
        header = hunk[0]
        match = HUNK_HEADER.match(header)
        if not match:
            raise ValueError("invalid_hunk_header")
        old_start = int(match.group(1))
        expected_index = max(old_start - 1, 0)
        if expected_index < source_index:
            raise ValueError("overlapping_hunks")
        result.extend(original_lines[source_index:expected_index])
        source_index = expected_index
        for hunk_line in hunk[1:]:
            if not hunk_line:
                raise ValueError("empty_hunk_line")
            marker = hunk_line[0]
            value = hunk_line[1:]
            if marker == "\\":
                continue
            if marker == " ":
                if source_index >= len(original_lines) or _strip_line_ending(original_lines[source_index]) != value:
                    raise ValueError("context_mismatch")
                result.append(original_lines[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(original_lines) or _strip_line_ending(original_lines[source_index]) != value:
                    raise ValueError("delete_mismatch")
                source_index += 1
            elif marker == "+":
                result.append(value + "\n")
            else:
                raise ValueError("unsupported_hunk_line")
    result.extend(original_lines[source_index:])
    return "".join(result)


def _strip_line_ending(line: str) -> str:
    return line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith("\n") else line


def _apply_prepared_changes(run_dir: Path, prepared: list[_PreparedChange]) -> list[str]:
    backups_dir = run_dir / BACKUPS_DIR
    backups_created: list[str] = []
    project_root = _project_root()
    for change in prepared:
        relative_target = _relative_to_project(change.target_path, project_root)
        backup_path = (backups_dir / relative_target).resolve()
        if not _is_relative_to(backup_path, backups_dir):
            raise OSError("backup_path_outside_run_dir")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(change.old_text, encoding="utf-8")
        backups_created.append(str(backup_path))
    for change in prepared:
        change.target_path.parent.mkdir(parents=True, exist_ok=True)
        change.target_path.write_text(change.new_text, encoding="utf-8")
    return backups_created


def _render_report(
    *,
    status: str,
    approval_items: list[str],
    patches_processed: list[str],
    files_modified: list[str],
    backups_created: list[str],
    warnings: list[str],
    errors: list[str],
    dry_run: bool,
) -> str:
    summary_items = [
        f"Patch apply stage completed with status: {STATUS_LABELS[status]}.",
        f"Dry run mode: {dry_run}.",
        "No repository files were modified." if status != APPLY_STATUS_APPLIED else "Approved patches were applied after backups were created.",
    ]
    return "\n".join(
        [
            "PATCH APPLY SUMMARY",
            *_bullets(summary_items),
            "",
            "APPROVAL CHECKS",
            *_bullets(approval_items),
            "",
            "PATCHES PROCESSED",
            *_bullets(patches_processed or ["None"]),
            "",
            "FILES MODIFIED",
            *_bullets(files_modified or ["None"]),
            "",
            "BACKUPS CREATED",
            *_bullets(backups_created or ["None"]),
            "",
            "VALIDATION WARNINGS",
            *_bullets(_dedupe(warnings) or ["None"]),
            "",
            "VALIDATION ERRORS",
            *_bullets(_dedupe(errors) or ["None"]),
            "",
            "APPLY STATUS",
            STATUS_LABELS[status],
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    summary_path = run_dir / SUMMARY_FILE
    if not summary_path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _update_summary(run_dir: Path, result: PatchApplyResult, *, summary_prefix: str) -> None:
    summary_path = run_dir / SUMMARY_FILE
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary = payload
        except json.JSONDecodeError:
            summary = {}
    summary.update(patch_apply_summary_fields(result, prefix=summary_prefix))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files[summary_prefix] = result.artifact_path
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def patch_apply_summary_fields(
    result: PatchApplyResult | None,
    *,
    prefix: str = "patch_apply",
) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        f"{prefix}_status": result.status,
        f"{prefix}_artifact": result.artifact_path,
        f"{prefix}_files_modified": result.files_modified,
        f"{prefix}_backups_created": result.backups_created,
        f"{prefix}_validation_passed": result.validation_passed,
        f"{prefix}_validation_errors": result.validation_errors,
        f"{prefix}_validation_warnings": result.warnings,
        f"{prefix}_dry_run": result.dry_run,
        f"{prefix}_approved_flag": result.approved_flag,
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_relative_to(path: Path, parent: Path) -> bool:
    path_key = _canonical_path_key(path)
    parent_key = _canonical_path_key(parent)
    return path_key == parent_key or path_key.startswith(parent_key.rstrip("/") + "/")


def _relative_to_project(path: Path, project_root: Path) -> Path:
    path_key = _canonical_path_key(path)
    project_key = _canonical_path_key(project_root).rstrip("/")
    if path_key == project_key:
        return Path(".")
    if not path_key.startswith(project_key + "/"):
        raise ValueError("path_outside_project_root")
    return Path(path_key[len(project_key) + 1 :])


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
