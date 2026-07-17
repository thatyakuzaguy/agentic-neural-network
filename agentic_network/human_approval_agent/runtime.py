"""Human Approval / Apply Authorization Agent runtime.

This stage is a non-LLM authorization gate. It never applies patches, executes
code, runs tests, loads models, or modifies repository source files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.pipeline.parallel_gate_runtime import evaluate_parallel_review_gate

HUMAN_APPROVAL_OUTPUT_FILE = "16_human_approval.md"
SUMMARY_FILE = "summary.json"
APPROVAL_TOKEN = "I_APPROVE_PATCH_APPLICATION"
DECISION_APPROVED = "Approved"
DECISION_DENIED = "Denied"

REQUIRED_ARTIFACTS = (
    "summary.json",
    "12_patch_approval.md",
    "15_merge_readiness.md",
)
SECTION_KEYS = {
    "HUMAN APPROVAL SUMMARY": "human_approval_summary",
    "AUTHORIZATION CHECKS": "authorization_checks",
    "APPROVAL TOKEN STATUS": "approval_token_status",
    "MERGE READINESS STATUS": "merge_readiness_status",
    "PATCH APPROVAL STATUS": "patch_approval_status",
    "AUTHORIZATION DECISION": "authorization_decision",
    "REASONING": "reasoning",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTIONS = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in REQUIRED_SECTIONS) + r")\s*$",
    re.IGNORECASE,
)
FORBIDDEN_TEXT = ("```", "@@", "+++", "---")
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:python\s+-m\s+|npm\s+|go\s+test\b|cargo\s+test\b|"
    r"sudo\b|rm\s+|chmod\b|curl\b|wget\b|powershell\b|bash\b|sh\b)"
)


@dataclass(frozen=True)
class HumanApprovalResult:
    """Structured result for human apply authorization."""

    run_dir: str
    decision: str
    report: str
    parsed_sections: dict[str, list[str] | str]
    artifact_path: str
    token_status: str
    warnings: list[str]
    validation_errors: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def authorize_apply(
    run_dir: Path,
    approval_token: str | None = None,
    approve_apply: bool = False,
    *,
    artifact_name: str = HUMAN_APPROVAL_OUTPUT_FILE,
    required_artifacts: tuple[str, ...] = REQUIRED_ARTIFACTS,
    summary_prefix: str = "human_approval",
    patch_approval_decision_key: str = "patch_approval_decision",
    patch_approval_validation_key: str = "patch_approval_validation_passed",
    patch_approval_errors_key: str = "patch_approval_validation_errors",
    require_merge_readiness: bool = True,
) -> HumanApprovalResult:
    """Authorize or deny later patch application based on human approval gates."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    parallel_gate = evaluate_parallel_review_gate(resolved_run_dir)
    missing_artifacts = [name for name in required_artifacts if not (resolved_run_dir / name).exists()]
    decision, token_status, checks, reasoning = _authorize(
        summary=summary,
        missing_artifacts=missing_artifacts,
        approval_token=approval_token,
        approve_apply=approve_apply,
        patch_approval_decision_key=patch_approval_decision_key,
        patch_approval_validation_key=patch_approval_validation_key,
        patch_approval_errors_key=patch_approval_errors_key,
        require_merge_readiness=require_merge_readiness,
        parallel_gate=parallel_gate,
    )
    report = _render_report(
        decision=decision,
        token_status=token_status,
        checks=checks,
        reasoning=reasoning,
        summary=summary,
        missing_artifacts=missing_artifacts,
    )
    parsed = parse_human_approval_sections(report)
    validation_errors = validate_human_approval_report(report, parsed)
    if missing_artifacts:
        validation_errors.extend(f"missing_artifact:{name}" for name in missing_artifacts)
    if parallel_gate.blocks_human_approval:
        validation_errors.append("parallel_review_gate_blocks_human_approval")
    validation_errors.extend(parallel_gate.validation_errors)
    validation_errors = _dedupe(validation_errors)

    artifact_path = resolved_run_dir / artifact_name
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    result = HumanApprovalResult(
        run_dir=str(resolved_run_dir),
        decision=decision,
        report=report,
        parsed_sections=parsed,
        artifact_path=str(artifact_path),
        token_status=token_status,
        warnings=_dedupe(warnings),
        validation_errors=validation_errors,
    )
    _update_summary(resolved_run_dir, result, summary_prefix=summary_prefix)
    return result


def parse_human_approval_sections(content: str) -> dict[str, list[str] | str]:
    """Parse the fixed Human Approval Agent output format."""

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
            parsed[key] = "" if current_heading in {"AUTHORIZATION DECISION", "CONFIDENCE"} else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading in {"AUTHORIZATION DECISION", "CONFIDENCE"}:
            parsed[key] = line.lstrip("- ").strip()
        elif line.startswith(("- ", "* ")):
            values = parsed.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return parsed


def validate_human_approval_report(
    report: str,
    parsed_sections: dict[str, list[str] | str],
) -> list[str]:
    """Validate human approval artifact shape and non-executable safety."""

    errors: list[str] = []
    counts = _section_counts(report)
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
        if title == "AUTHORIZATION DECISION":
            if str(value).strip() not in {DECISION_APPROVED, DECISION_DENIED}:
                errors.append("authorization_decision_invalid")
        elif title == "CONFIDENCE":
            if str(value).strip() != "High":
                errors.append("confidence_not_high")
        elif not isinstance(value, list) or not value:
            errors.append(f"empty_section:{title}")
    lowered = report.lower()
    for marker in FORBIDDEN_TEXT:
        if marker.lower() in lowered:
            errors.append("forbidden_content_present")
            break
    if FORBIDDEN_COMMAND_PATTERN.search(report):
        errors.append("forbidden_content_present")
    return _dedupe(errors)


def human_approval_summary_fields(
    result: HumanApprovalResult | None,
    *,
    prefix: str = "human_approval",
) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        f"{prefix}_status": "VALID" if result.validation_passed else "INVALID",
        f"{prefix}_decision": result.decision,
        f"{prefix}_artifact": result.artifact_path,
        f"{prefix}_validation_passed": result.validation_passed,
        f"{prefix}_validation_errors": result.validation_errors,
        f"{prefix}_validation_warnings": result.warnings,
        f"{prefix}_token_status": result.token_status,
    }


def _authorize(
    *,
    summary: dict[str, Any],
    missing_artifacts: list[str],
    approval_token: str | None,
    approve_apply: bool,
    patch_approval_decision_key: str,
    patch_approval_validation_key: str,
    patch_approval_errors_key: str,
    require_merge_readiness: bool,
    parallel_gate: Any,
) -> tuple[str, str, list[str], list[str]]:
    token_status = _token_status(approval_token)
    checks: list[str] = []
    failures: list[str] = []

    _check(approve_apply, "Explicit approve apply flag is present.", "Explicit approve apply flag is missing.", checks, failures)
    _check(token_status == "valid", "Approval token matched required phrase.", "Approval token is missing or invalid.", checks, failures)
    _check(_summary_text(summary, "final_decision") == "Approved", "Final Reviewer approved the run.", "Final Reviewer did not approve the run.", checks, failures)
    _check(_summary_text(summary, patch_approval_decision_key) == "Approved", "Patch Approval Agent approved the patch set.", "Patch Approval Agent did not approve the patch set.", checks, failures)
    _check(summary.get(patch_approval_validation_key) is True, "Patch Approval validation passed.", "Patch Approval validation did not pass.", checks, failures)
    merge_decision = _summary_text(summary, "merge_readiness_decision")
    if require_merge_readiness:
        _check(merge_decision in {"READY TO APPLY", "READY TO MERGE"}, "Merge readiness allows apply authorization.", "Merge readiness does not allow apply authorization.", checks, failures)
    else:
        checks.append("Merge readiness gate is not required for retry authorization mode.")
    patch_apply_status = _normalize_status(_summary_text(summary, "patch_apply_status"))
    _check(patch_apply_status not in {"FAILED", "REJECTED", "DRY_RUN_FAILED"}, "Patch Apply Agent did not report failure.", "Patch Apply Agent reported a failed or rejected state.", checks, failures)
    patch_errors = _as_list(summary.get(patch_approval_errors_key))
    _check(not patch_errors, "Patch Approval validation errors are empty.", "Patch Approval validation errors are present.", checks, failures)
    protected_findings = _protected_findings(summary)
    _check(not protected_findings, "No protected path findings are present.", "Protected path findings are present.", checks, failures)
    if parallel_gate.blocks_human_approval:
        checks.append(f"Parallel Review Gate blocks human approval: {parallel_gate.decision}.")
        failures.append(f"Parallel Review Gate blocked human approval: {parallel_gate.reason}.")
    else:
        checks.append(f"Parallel Review Gate allows human approval: {parallel_gate.decision}.")
    if missing_artifacts:
        failures.append("Required authorization artifacts are missing.")
        checks.append("Required authorization artifacts are missing.")

    decision = DECISION_APPROVED if not failures else DECISION_DENIED
    reasoning = ["All human authorization gates passed."] if decision == DECISION_APPROVED else failures
    return decision, token_status, checks, reasoning


def _render_report(
    *,
    decision: str,
    token_status: str,
    checks: list[str],
    reasoning: list[str],
    summary: dict[str, Any],
    missing_artifacts: list[str],
) -> str:
    summary_items = [
        f"Human apply authorization decision: {decision}.",
        "This stage authorizes only and does not apply patches.",
    ]
    if missing_artifacts:
        summary_items.append("One or more required authorization artifacts are missing.")
    merge_items = [
        f"Merge readiness decision: {_summary_text(summary, 'merge_readiness_decision') or 'Unknown'}.",
        f"Merge readiness validation passed: {summary.get('merge_readiness_validation_passed', False)}.",
    ]
    patch_items = [
        f"Patch approval decision: {_summary_text(summary, 'patch_approval_decision') or 'Unknown'}.",
        f"Patch approval validation passed: {summary.get('patch_approval_validation_passed', False)}.",
        f"Patch approval validation errors: {len(_as_list(summary.get('patch_approval_validation_errors')))}.",
    ]
    token_items = [
        "Token status: valid." if token_status == "valid" else f"Token status: {token_status}.",
    ]
    return "\n".join(
        [
            "HUMAN APPROVAL SUMMARY",
            *_bullets(summary_items),
            "",
            "AUTHORIZATION CHECKS",
            *_bullets(checks),
            "",
            "APPROVAL TOKEN STATUS",
            *_bullets(token_items),
            "",
            "MERGE READINESS STATUS",
            *_bullets(merge_items),
            "",
            "PATCH APPROVAL STATUS",
            *_bullets(patch_items),
            "",
            "AUTHORIZATION DECISION",
            decision,
            "",
            "REASONING",
            *_bullets(reasoning),
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _check(condition: bool, passed: str, failed: str, checks: list[str], failures: list[str]) -> None:
    checks.append(passed if condition else failed)
    if not condition:
        failures.append(failed)


def _token_status(token: str | None) -> str:
    if token is None or token == "":
        return "missing"
    return "valid" if token == APPROVAL_TOKEN else "invalid"


def _protected_findings(summary: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "patch_approval_validation_errors",
        "patch_approval_validation_warnings",
        "patch_apply_validation_errors",
        "patch_apply_validation_warnings",
    ):
        values.extend(_as_list(summary.get(key)))
    return [value for value in values if "protected_path" in value.lower()]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in {None, ""}:
        return []
    return [str(value)]


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _update_summary(run_dir: Path, result: HumanApprovalResult, *, summary_prefix: str) -> None:
    summary = _load_summary(run_dir, [])
    summary.update(human_approval_summary_fields(result, prefix=summary_prefix))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files[summary_prefix] = result.artifact_path
    (run_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _section_counts(content: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTIONS}
    for line in content.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _summary_text(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return "" if value in {None, ""} else str(value).strip()


def _normalize_status(value: str) -> str:
    if not value:
        return "UNKNOWN"
    return value.upper().replace(" ", "_")


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items or ["None"]]


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
