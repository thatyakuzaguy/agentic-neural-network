"""Patch Approval Agent runtime.

This stage is a non-LLM validation gate. It reviews generated patch proposal
files and writes an approval artifact; it never applies patches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentic_network.safety.filesystem_policy import load_filesystem_policy

PATCH_APPROVAL_OUTPUT_FILE = "12_patch_approval.md"
PATCHES_DIR = "patches"

SECTION_KEYS = {
    "PATCH SUMMARY": "patch_summary",
    "FILES REVIEWED": "files_reviewed",
    "SAFETY CHECKS": "safety_checks",
    "APPROVAL DECISION": "approval_decision",
    "REASONING": "reasoning",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTIONS = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in REQUIRED_SECTIONS) + r")\s*$",
    re.IGNORECASE,
)
APPROVAL_DECISIONS = {"Approved", "Rejected"}
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\()"
)
SHELL_SCRIPT_PATTERN = re.compile(
    r"(?m)^\s*#!\s*/(?:usr/bin/env\s+)?(?:bash|sh|zsh|powershell|pwsh)\b"
)
WINDOWS_C_PATH_PATTERN = re.compile(r"(?i)(?:^|[\s:+-])(?:/mnt/c\b|[A-Z]:\\)")
ABSOLUTE_MOUNT_PATH_PATTERN = re.compile(r"(?<!\w)(/mnt/[a-zA-Z]/[^\s)\]]+)")
DIFF_PATH_LINE = re.compile(r"(?m)^\s*(?:---|\+\+\+)\s+(.+?)\s*$")

@dataclass(frozen=True)
class PatchApprovalResult:
    """Structured result for patch approval validation."""

    run_dir: str
    approval_output: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    artifact_path: str
    patch_paths: list[str]
    decision: str

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def approve_patches(
    run_dir: Path,
    *,
    patch_dir: str = PATCHES_DIR,
    artifact_name: str = PATCH_APPROVAL_OUTPUT_FILE,
) -> PatchApprovalResult:
    """Review patch proposals and write the patch approval artifact."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    execution_plan = _read_optional(resolved_run_dir / "11_execution_plan.md", warnings)
    final_review = _read_optional(resolved_run_dir / "08_final_review.md", warnings)
    patch_paths = sorted((resolved_run_dir / patch_dir).glob("*.diff"))
    patch_texts = [path.read_text(encoding="utf-8") for path in patch_paths]

    safety_errors = validate_patch_safety(
        patch_texts=patch_texts,
        patch_paths=patch_paths,
        project_root=_project_root(),
        patch_dir=patch_dir,
    )
    final_decision = _extract_final_decision(final_review)
    if final_decision != "Approved":
        safety_errors.append("final_decision_not_approved")
    if not execution_plan.strip():
        safety_errors.append("execution_plan_missing")
    if not patch_paths:
        warnings.append("no_patch_files_found")
        safety_errors.append("patch_files_missing")

    decision = "Rejected" if safety_errors else "Approved"
    approval_output = _render_approval(
        decision=decision,
        patch_paths=patch_paths,
        safety_errors=safety_errors,
        warnings=warnings,
    )
    parsed_sections = parse_patch_approval_sections(approval_output)
    validation_errors = validate_patch_approval_response(
        approval_output=approval_output,
        parsed_sections=parsed_sections,
    )
    validation_errors.extend(safety_errors)
    validation_errors = _dedupe(validation_errors)

    artifact_path = resolved_run_dir / artifact_name
    artifact_path.write_text(approval_output.rstrip() + "\n", encoding="utf-8")
    return PatchApprovalResult(
        run_dir=str(resolved_run_dir),
        approval_output=approval_output,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        artifact_path=str(artifact_path),
        patch_paths=[str(path) for path in patch_paths],
        decision=decision,
    )


def parse_patch_approval_sections(content: str) -> dict[str, list[str] | str]:
    """Parse the fixed Patch Approval Agent output format."""

    parsed: dict[str, list[str] | str] = {}
    current_heading: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = SECTION_LINE.match(line)
        if match:
            current_heading = match.group(1).upper()
            key = SECTION_KEYS[current_heading]
            parsed[key] = "" if current_heading in {"APPROVAL DECISION", "CONFIDENCE"} else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading in {"APPROVAL DECISION", "CONFIDENCE"}:
            parsed[key] = line.lstrip("- ").strip()
        elif line.startswith(("- ", "* ")):
            values = parsed.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return parsed


def validate_patch_approval_response(
    *,
    approval_output: str,
    parsed_sections: dict[str, list[str] | str],
) -> list[str]:
    """Validate the patch approval artifact contract."""

    errors: list[str] = []
    counts = _section_counts(approval_output)
    for title, key in SECTION_KEYS.items():
        count = counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section:{title}")
        elif count > 1:
            errors.append(f"duplicate_section:{title}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section:{title}")
    for title, key in SECTION_KEYS.items():
        value = parsed_sections.get(key, "")
        if title == "APPROVAL DECISION":
            if str(value).strip() not in APPROVAL_DECISIONS:
                errors.append("approval_decision_invalid")
        elif title == "CONFIDENCE":
            if str(value).strip() != "High":
                errors.append("confidence_not_high")
        elif not isinstance(value, list) or not value:
            errors.append(f"empty_section:{title}")
    return errors


def validate_patch_safety(
    *,
    patch_texts: list[str],
    patch_paths: list[Path],
    project_root: Path,
    patch_dir: str = PATCHES_DIR,
) -> list[str]:
    """Validate patch proposal text against patch approval safety rules."""

    errors: list[str] = []
    policy = load_filesystem_policy(project_root=project_root)
    for patch_path in patch_paths:
        try:
            resolved = patch_path.resolve()
        except OSError:
            errors.append(f"patch_path_unreadable:{patch_path}")
            continue
        run_dir = patch_path.parents[1] if len(patch_path.parents) > 1 else patch_path.parent
        if not _is_relative_to(resolved, run_dir / patch_dir):
            errors.append(f"patch_file_outside_{patch_dir}_dir:{patch_path}")
    for patch_text in patch_texts:
        if FORBIDDEN_COMMAND_PATTERN.search(patch_text) or SHELL_SCRIPT_PATTERN.search(patch_text):
            errors.append("dangerous_command_present")
        if WINDOWS_C_PATH_PATTERN.search(patch_text):
            errors.append("forbidden_c_path_present")
        for absolute_path in ABSOLUTE_MOUNT_PATH_PATTERN.findall(patch_text):
            if policy.is_path_blocked(absolute_path):
                errors.append("forbidden_c_path_present")
            elif not _is_under_project_root(absolute_path, project_root):
                errors.append(f"path_outside_repository:{absolute_path}")
            errors.extend(_policy_errors_for_patch_path(policy, absolute_path))
        for candidate in _diff_paths(patch_text):
            normalized = _normalize_diff_path(candidate)
            if not normalized:
                continue
            target = policy.normalize_path(normalized)
            if policy.is_path_blocked(normalized):
                errors.append("forbidden_c_path_present")
            elif _is_absolute_diff_path(normalized) and target.is_absolute() and not _is_under_project_root(str(target), project_root):
                errors.append(f"path_outside_repository:{normalized}")
            errors.extend(_policy_errors_for_patch_path(policy, normalized))
    return _dedupe(errors)


def _render_approval(
    *,
    decision: str,
    patch_paths: list[Path],
    safety_errors: list[str],
    warnings: list[str],
) -> str:
    reviewed = [str(path.name) for path in patch_paths] or ["None"]
    checks = (
        [
            "No dangerous commands were detected.",
            "No forbidden C drive references were detected.",
            "No protected model, adapter, dataset, git, or outputs paths were modified.",
        ]
        if not safety_errors
        else [f"Rejected safety issue: {error}." for error in _dedupe(safety_errors)]
    )
    reasoning = (
        ["Patch proposals are reviewable and limited to generated diff files."]
        if decision == "Approved"
        else ["Patch proposals are not safe to approve until listed issues are resolved."]
    )
    if warnings:
        reasoning.extend(f"Warning recorded: {warning}." for warning in warnings)
    lines: list[str] = []
    for heading, items in (
        ("PATCH SUMMARY", [f"Reviewed {len(patch_paths)} patch proposal file(s)."]),
        ("FILES REVIEWED", reviewed),
        ("SAFETY CHECKS", checks),
    ):
        lines.append(heading)
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    lines.extend(["APPROVAL DECISION", decision, ""])
    lines.append("REASONING")
    lines.extend(f"- {item}" for item in reasoning)
    lines.extend(["", "CONFIDENCE", "High"])
    return "\n".join(lines).strip()


def _read_optional(path: Path, warnings: list[str]) -> str:
    if not path.exists():
        warnings.append(f"missing_artifact:{path.name}")
        return ""
    return path.read_text(encoding="utf-8")


def _extract_final_decision(final_review: str) -> str:
    lines = final_review.splitlines()
    for index, line in enumerate(lines):
        if line.strip().upper() == "FINAL DECISION":
            for candidate in lines[index + 1 :]:
                value = candidate.strip().lstrip("- ").strip()
                if value:
                    return value
    return "Unknown"


def _diff_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for match in DIFF_PATH_LINE.finditer(patch_text):
        value = match.group(1).strip()
        if value not in {"old", "new", "/dev/null"}:
            paths.append(value)
    return paths


def _normalize_diff_path(path_text: str) -> str:
    path_text = path_text.strip().strip('"').strip("'")
    if path_text.startswith(("a/", "b/")):
        path_text = path_text[2:]
    return path_text


def _is_absolute_diff_path(path_text: str) -> bool:
    normalized = path_text.replace("\\", "/")
    return bool(re.match(r"(?i)^[a-z]:/", normalized) or normalized.startswith("/"))


def _policy_errors_for_patch_path(policy, path_text: str) -> list[str]:
    errors: list[str] = []
    for error in policy.validate_patch_target(path_text):
        if error == "forbidden_c_path_present":
            errors.append(error)
        elif error.startswith("protected_path_modified:"):
            errors.append(error)
        elif error.startswith("blocked_path:"):
            errors.append(error)
    return errors


def _section_counts(content: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTIONS}
    for line in content.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _is_under_project_root(path_text: str, project_root: Path) -> bool:
    try:
        candidate = Path(path_text).resolve()
        return candidate == project_root or project_root in candidate.parents
    except OSError:
        return False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


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
