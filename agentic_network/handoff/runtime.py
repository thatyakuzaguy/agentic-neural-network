"""Build a non-LLM handoff bundle from pipeline run artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HANDOFF_OUTPUT_FILE = "09_handoff_bundle.md"
SUMMARY_FILE = "summary.json"
ARTIFACTS = (
    ("00 Context", "00_context.md"),
    ("01 Product Requirements", "01_product_requirements.md"),
    ("02 Architecture Plan", "02_architecture_plan.md"),
    ("03 Code Plan", "03_code.md"),
    ("04 Test Plan", "04_tests.md"),
    ("05 Security Review", "05_security.md"),
    ("06 Reviewer Report", "06_review.md"),
    ("07 Fix Plan", "07_fix_plan.md"),
    ("08 Final Review", "08_final_review.md"),
    ("10 Knowledge Capture", "10_knowledge_capture.md"),
)
OPTIONAL_ARTIFACTS = (
    ("11 Execution Plan", "11_execution_plan.md"),
    ("12 Patch Approval", "12_patch_approval.md"),
    ("06a Failure Context", "06a_failure_context.md"),
    ("06a Failure Context JSON", "06a_failure_context.json"),
    ("Repository Intelligence Summary", "repository_intelligence/project_summary.json"),
    ("26 Repository Context", "26_repository_context.md"),
    ("26 Repository Context JSON", "26_repository_context.json"),
    ("25 Patch Quality", "25_patch_quality.md"),
    ("13 Patch Apply", "13_patch_apply.md"),
    ("14 Test Run", "14_test_run.md"),
    ("17 Failure Analysis", "17_failure_analysis.md"),
    ("18 Root Cause", "18_root_cause.md"),
    ("15 Merge Readiness", "15_merge_readiness.md"),
    ("16 Human Approval", "16_human_approval.md"),
    ("21 Self Healing", "21_self_healing.md"),
    ("27 Autonomous Loop", "27_autonomous_loop.md"),
    ("37 Parallel Review", "37_parallel_review.md"),
    ("37 Parallel Review JSON", "37_parallel_review.json"),
    ("38 Consensus Decision", "38_consensus_decision.md"),
    ("38 Consensus Decision JSON", "38_consensus_decision.json"),
    ("39 Action Plan", "39_action_plan.md"),
    ("39 Action Plan JSON", "39_action_plan.json"),
)
OPTIONAL_ARTIFACT_PATTERNS = (
    ("34 Retry Test Failure Analysis", "34_retry_test_failure_analysis_attempt_*.md"),
    ("35 Retry Failure Followup Plan", "35_retry_failure_followup_plan_attempt_*.md"),
    ("36 Retry Failure Loop", "36_retry_failure_loop_attempt_*.md"),
    ("37 Failure Context", "37_failure_context_attempt_*.md"),
    ("37 Failure Context JSON", "37_failure_context_attempt_*.json"),
)
REQUIRED_HEADINGS = (
    "# ANN Handoff Bundle",
    "## Task",
    "## Run Summary",
    "## Artifact Index",
    "## 00 Context",
    "## 01 Product Requirements",
    "## 02 Architecture Plan",
    "## 03 Code Plan",
    "## 04 Test Plan",
    "## 05 Security Review",
    "## 06 Reviewer Report",
    "## 07 Fix Plan",
    "## 08 Final Review",
    "## 10 Knowledge Capture",
    "## Machine Summary",
)


@dataclass(frozen=True)
class HandoffBundleResult:
    """Result metadata for a handoff bundle build."""

    run_dir: str
    artifact_path: str
    included_artifacts: list[str]
    missing_artifacts: list[str]
    final_decision: str
    reviewer_approval_status: str
    fixer_ready_for_rereview: str
    warnings: list[str]
    validation_errors: list[str]


def build_handoff_bundle(run_dir: Path, task: str | None = None) -> HandoffBundleResult:
    """Create 09_handoff_bundle.md from a completed or partial run directory."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    task_text = task or str(summary.get("task") or _read_optional(resolved_run_dir / "00_user_request.md"))
    task_text = task_text.strip() or "Unknown"

    included_artifacts: list[str] = []
    missing_artifacts: list[str] = []
    artifact_sections: list[str] = []
    artifacts_to_include = list(ARTIFACTS)
    artifacts_to_include.extend(
        (label, filename)
        for label, filename in OPTIONAL_ARTIFACTS
        if (resolved_run_dir / filename).exists()
    )
    artifacts_to_include.extend(_discover_optional_artifacts(resolved_run_dir))
    for label, filename in artifacts_to_include:
        artifact_path = resolved_run_dir / filename
        artifact_sections.append(f"## {label}")
        if artifact_path.exists():
            included_artifacts.append(filename)
            artifact_sections.append(artifact_path.read_text(encoding="utf-8").strip() or "_Empty artifact._")
        else:
            missing_artifacts.append(filename)
            warning = f"missing_artifact:{filename}"
            warnings.append(warning)
            artifact_sections.append(f"_Artifact missing: {filename}_")
        artifact_sections.append("")

    final_decision = _summary_value(summary, "final_decision", "final_status")
    reviewer_approval_status = _summary_value(
        summary, "reviewer_approval_status", "reviewer_status"
    )
    fixer_ready_for_rereview = _summary_value(summary, "fixer_ready_for_rereview")
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stages_included = summary.get("stages_run")
    if isinstance(stages_included, list):
        stage_text = ", ".join(str(stage) for stage in stages_included)
    else:
        stage_text = "Unknown"

    lines = [
        "# ANN Handoff Bundle",
        "",
        "## Task",
        task_text,
        "",
        "## Run Summary",
        f"- Run directory: {resolved_run_dir}",
        f"- Final decision: {final_decision}",
        f"- Reviewer approval status: {reviewer_approval_status}",
        f"- Fixer ready for re-review: {fixer_ready_for_rereview}",
        f"- Generated at: {generated_at}",
        f"- Stages included: {stage_text}",
        "",
        "## Artifact Index",
    ]
    lines.extend(f"- {label}" for label, _filename in artifacts_to_include)
    lines.append("")
    lines.extend(artifact_sections)
    lines.extend(
        [
            "## Machine Summary",
            _machine_summary_excerpt(summary, missing_artifacts),
            "",
        ]
    )

    artifact_path = resolved_run_dir / HANDOFF_OUTPUT_FILE
    artifact_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    validation_errors = validate_handoff_bundle(
        artifact_path=artifact_path,
        included_artifacts=included_artifacts,
        missing_artifacts=missing_artifacts,
        final_decision=final_decision,
    )
    return HandoffBundleResult(
        run_dir=str(resolved_run_dir),
        artifact_path=str(artifact_path),
        included_artifacts=included_artifacts,
        missing_artifacts=missing_artifacts,
        final_decision=final_decision,
        reviewer_approval_status=reviewer_approval_status,
        fixer_ready_for_rereview=fixer_ready_for_rereview,
        warnings=warnings,
        validation_errors=validation_errors,
    )


def validate_handoff_bundle(
    *,
    artifact_path: Path,
    included_artifacts: list[str],
    missing_artifacts: list[str],
    final_decision: str,
) -> list[str]:
    """Validate the generated handoff bundle content."""

    errors: list[str] = []
    if not artifact_path.exists():
        return ["handoff_artifact_missing"]
    content = artifact_path.read_text(encoding="utf-8")
    for heading in REQUIRED_HEADINGS:
        if heading not in content:
            errors.append(f"missing_heading:{heading}")
    for filename in missing_artifacts:
        if f"Artifact missing: {filename}" not in content:
            errors.append(f"missing_artifact_placeholder_absent:{filename}")
    if final_decision != "Unknown" and f"- Final decision: {final_decision}" not in content:
        errors.append("final_decision_not_recorded")
    return errors


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


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _summary_value(summary: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = summary.get(key)
        if value not in {None, ""}:
            return str(value)
    return "Unknown"


def _discover_optional_artifacts(run_dir: Path) -> list[tuple[str, str]]:
    artifacts: list[tuple[str, str]] = []
    for label, pattern in OPTIONAL_ARTIFACT_PATTERNS:
        for path in sorted(run_dir.glob(pattern)):
            artifacts.append((f"{label} {path.stem.rsplit('_', 1)[-1]}", path.name))
    return artifacts


def _machine_summary_excerpt(summary: dict[str, Any], missing_artifacts: list[str]) -> str:
    keys = (
        "timestamp",
        "task",
        "stages_run",
        "reviewer_status",
        "reviewer_approval_status",
        "fixer_ready_for_rereview",
        "final_status",
        "final_decision",
        "final_validation_passed",
        "self_healing_status",
        "self_healing_last_patch",
        "self_healing_validation_passed",
        "memory_enabled",
        "memory_patterns_recorded",
        "memory_successful_repairs",
        "memory_failed_repairs",
        "memory_last_domain",
        "memory_validation_passed",
    )
    excerpt = {key: summary.get(key) for key in keys if key in summary}
    excerpt["missing_artifacts"] = missing_artifacts
    return json.dumps(excerpt, indent=2)
