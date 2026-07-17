"""Merge Readiness Agent runtime.

This stage is a non-LLM decision gate. It reads prior ANN artifacts and summary
metadata, then writes a merge-readiness decision without executing commands,
running tests, applying patches, or modifying repository source files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.pipeline.parallel_gate_runtime import evaluate_parallel_review_gate

MERGE_READINESS_OUTPUT_FILE = "15_merge_readiness.md"
SUMMARY_FILE = "summary.json"

DECISION_READY_TO_APPLY = "READY TO APPLY"
DECISION_READY_TO_MERGE = "READY TO MERGE"
DECISION_BLOCKED = "BLOCKED"

REQUIRED_ARTIFACTS = (
    "summary.json",
    "12_patch_approval.md",
    "13_patch_apply.md",
    "14_test_run.md",
    "08_final_review.md",
    "11_execution_plan.md",
)
SECTION_KEYS = {
    "MERGE SUMMARY": "merge_summary",
    "ARTIFACT STATUS": "artifact_status",
    "PATCH STATUS": "patch_status",
    "TEST STATUS": "test_status",
    "RISKS": "risks",
    "MERGE DECISION": "merge_decision",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTIONS = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in REQUIRED_SECTIONS) + r")\s*$",
    re.IGNORECASE,
)
FORBIDDEN_TEXT = (
    "```",
    "@@",
    "+++",
    "---",
)
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:python\s+-m\s+|npm\s+|go\s+test\b|cargo\s+test\b|"
    r"sudo\b|rm\s+|chmod\b|curl\b|wget\b)"
)


@dataclass(frozen=True)
class MergeReadinessResult:
    """Structured result for merge-readiness evaluation."""

    run_dir: str
    decision: str
    report: str
    parsed_sections: dict[str, list[str] | str]
    artifact_path: str
    warnings: list[str]
    validation_errors: list[str]
    artifact_status: dict[str, str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def evaluate_merge_readiness(run_dir: Path) -> MergeReadinessResult:
    """Evaluate whether an ANN run is ready to apply, merge, or blocked."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    parallel_gate = evaluate_parallel_review_gate(resolved_run_dir)
    artifact_status = _artifact_status(resolved_run_dir)
    missing_artifacts = [name for name, status in artifact_status.items() if status == "missing"]
    decision, reasons, risks = _decide(summary, missing_artifacts, parallel_gate=parallel_gate)

    report = _render_report(
        decision=decision,
        artifact_status=artifact_status,
        reasons=reasons,
        risks=risks,
        summary=summary,
    )
    parsed = parse_merge_readiness_sections(report)
    validation_errors = validate_merge_readiness_report(report, parsed)
    if missing_artifacts:
        validation_errors.extend(f"missing_artifact:{name}" for name in missing_artifacts)
    validation_errors = _dedupe(validation_errors)

    artifact_path = resolved_run_dir / MERGE_READINESS_OUTPUT_FILE
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    result = MergeReadinessResult(
        run_dir=str(resolved_run_dir),
        decision=decision,
        report=report,
        parsed_sections=parsed,
        artifact_path=str(artifact_path),
        warnings=_dedupe(warnings),
        validation_errors=validation_errors,
        artifact_status=artifact_status,
    )
    _update_summary(resolved_run_dir, result)
    return result


def parse_merge_readiness_sections(content: str) -> dict[str, list[str] | str]:
    """Parse the fixed Merge Readiness Agent report format."""

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
            parsed[key] = "" if current_heading in {"MERGE DECISION", "CONFIDENCE"} else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading in {"MERGE DECISION", "CONFIDENCE"}:
            parsed[key] = line.lstrip("- ").strip()
        elif line.startswith(("- ", "* ")):
            values = parsed.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return parsed


def validate_merge_readiness_report(
    report: str,
    parsed_sections: dict[str, list[str] | str],
) -> list[str]:
    """Validate merge readiness artifact shape and safety constraints."""

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
        if title == "MERGE DECISION":
            if str(value).strip() not in {
                DECISION_READY_TO_APPLY,
                DECISION_READY_TO_MERGE,
                DECISION_BLOCKED,
            }:
                errors.append("merge_decision_invalid")
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


def merge_readiness_summary_fields(result: MergeReadinessResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "merge_readiness_status": "VALID" if result.validation_passed else "INVALID",
        "merge_readiness_decision": result.decision,
        "merge_readiness_validation_passed": result.validation_passed,
        "merge_readiness_validation_errors": result.validation_errors,
        "merge_readiness_validation_warnings": result.warnings,
        "merge_readiness_artifact": result.artifact_path,
    }


def _decide(
    summary: dict[str, Any],
    missing_artifacts: list[str],
    *,
    parallel_gate: Any,
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    risks: list[str] = []
    final_decision = _summary_text(summary, "final_decision")
    patch_decision = _summary_text(summary, "patch_approval_decision")
    patch_validation = summary.get("patch_approval_validation_passed") is True
    patch_apply_status = _normalize_status(_summary_text(summary, "patch_apply_status"))
    test_runner_status = _normalize_status(_summary_text(summary, "test_runner_status"))

    if parallel_gate.blocks_patch_apply or parallel_gate.blocks_human_approval:
        reasons.append(f"Parallel Review Gate blocks readiness: {parallel_gate.decision}.")
        risks.append(parallel_gate.reason)
    if missing_artifacts:
        reasons.append("One or more required artifacts are missing.")
        risks.append("Readiness cannot be trusted until all required artifacts are present.")
    if final_decision != "Approved":
        reasons.append("Final Reviewer did not approve the run.")
    if patch_decision != "Approved":
        reasons.append("Patch Approval Agent did not approve the patch set.")
    if not patch_validation:
        reasons.append("Patch Approval validation did not pass.")
    if patch_apply_status in {"FAILED", "REJECTED", "DRY_RUN_FAILED"}:
        reasons.append("Patch Apply Agent reported an unsafe or failed state.")
    if test_runner_status in {"FAILED", "TIMEOUT", "REJECTED"}:
        reasons.append("Test Runner Agent reported a failed, timed out, or rejected state.")

    if reasons:
        return DECISION_BLOCKED, reasons, risks or ["Resolve blocking readiness findings before applying or merging."]

    if patch_apply_status == "APPLIED" and test_runner_status == "PASSED":
        return (
            DECISION_READY_TO_MERGE,
            ["Final review, patch approval, patch application, and test execution are all successful."],
            ["Human review should still confirm the applied patch matches repository expectations."],
        )

    if patch_apply_status in {"SKIPPED", "DRY_RUN_PASSED", "UNKNOWN", "NOT RUN"} and test_runner_status in {
        "SKIPPED",
        "UNKNOWN",
        "NOT RUN",
        "NO_TESTS_DETECTED",
    }:
        return (
            DECISION_READY_TO_APPLY,
            ["Final review and patch approval are approved, while patch application has not been completed."],
            ["Apply patches only through the explicit guarded approval path before merging."],
        )

    return (
        DECISION_BLOCKED,
        ["Current patch or test state does not satisfy ready-to-apply or ready-to-merge criteria."],
        ["Review patch apply and test runner artifacts before proceeding."],
    )


def _render_report(
    *,
    decision: str,
    artifact_status: dict[str, str],
    reasons: list[str],
    risks: list[str],
    summary: dict[str, Any],
) -> str:
    patch_items = [
        f"Patch approval decision: {_summary_text(summary, 'patch_approval_decision') or 'Unknown'}.",
        f"Patch approval validation passed: {summary.get('patch_approval_validation_passed', False)}.",
        f"Patch apply status: {_summary_text(summary, 'patch_apply_status') or 'Unknown'}.",
    ]
    test_items = [
        f"Test runner status: {_summary_text(summary, 'test_runner_status') or 'Unknown'}.",
        f"Test runner run flag: {summary.get('test_runner_run_tests_flag', False)}.",
    ]
    return "\n".join(
        [
            "MERGE SUMMARY",
            *_bullets(reasons),
            "",
            "ARTIFACT STATUS",
            *_bullets([f"{name}: {status}." for name, status in artifact_status.items()]),
            "",
            "PATCH STATUS",
            *_bullets(patch_items),
            "",
            "TEST STATUS",
            *_bullets(test_items),
            "",
            "RISKS",
            *_bullets(risks),
            "",
            "MERGE DECISION",
            decision,
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _artifact_status(run_dir: Path) -> dict[str, str]:
    return {name: "present" if (run_dir / name).exists() else "missing" for name in REQUIRED_ARTIFACTS}


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


def _update_summary(run_dir: Path, result: MergeReadinessResult) -> None:
    summary = _load_summary(run_dir, [])
    summary.update(merge_readiness_summary_fields(result))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files["merge_readiness"] = result.artifact_path
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
