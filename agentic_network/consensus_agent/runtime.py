"""ANN v7.2 Autonomous Consensus Engine.

This subsystem aggregates existing ANN run signals into one deterministic
system recommendation. It is read-mostly: the only writes are the two
consensus artifacts inside the selected run directory.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.architecture_entropy.runtime import evaluate_architecture_entropy
from agentic_network.pipeline.parallel_gate_runtime import (
    DECISION_BLOCKED as PARALLEL_BLOCKED,
    DECISION_NEEDS_REVISION as PARALLEL_NEEDS_REVISION,
    evaluate_parallel_review_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
MARKDOWN_ARTIFACT = "38_consensus_decision.md"
JSON_ARTIFACT = "38_consensus_decision.json"
SUMMARY_FILE = "summary.json"

STATUS_VALID = "VALID"
STATUS_INVALID = "INVALID"

DECISION_APPROVED_TO_APPLY = "APPROVED_TO_APPLY"
DECISION_NEEDS_REVISION = "NEEDS_REVISION"
DECISION_RETRY_RECOMMENDED = "RETRY_RECOMMENDED"
DECISION_BLOCKED = "BLOCKED"
DECISION_FAILED_PERMANENTLY = "FAILED_PERMANENTLY"
DECISION_NO_ACTION = "NO_ACTION"

CONFIDENCE_HIGH = "High"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_LOW = "Low"

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
BLOCKED_PARTS = {".git", "models", "training", "memory", "knowledge", "unsloth_compiled_cache"}
STYLE_ONLY_PATCH_QUALITY = {"LOW_VALUE_COMMENT_ONLY"}
STYLE_TERMS = {
    "style",
    "stylistic",
    "idiom",
    "idiomatic",
    "format",
    "formatting",
    "cosmetic",
    "readability",
    "rename",
    "naming",
    "prefer",
    "preference",
    "convention",
    "refactor",
    "comment-only",
    "comment only",
    "low-value",
    "low value",
}
FUNCTIONAL_TERMS = {
    "failed",
    "failure",
    "bug",
    "security",
    "vulnerability",
    "unsafe",
    "integration",
    "broken",
    "regression",
    "missing",
    "timeout",
    "exception",
    "traceback",
    "data loss",
    "auth",
    "permission",
    "migration",
    "schema",
    "incorrect",
    "invalid",
}


@dataclass(frozen=True)
class ConsensusResult:
    """Structured result for the Autonomous Consensus Engine."""

    status: str
    consensus_decision: str
    confidence: str
    reasons: list[str]
    blocking_findings: list[str]
    warnings: list[str]
    signals_used: dict[str, Any]
    agent_votes: dict[str, str]
    recommended_next_action: str
    skill_evidence_status: str
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_consensus_decision(
    run_dir: str | Path,
    *,
    runs_root: str | Path | None = None,
) -> ConsensusResult:
    """Aggregate ANN run signals and write 38 consensus artifacts."""

    validation_errors, validation_warnings, resolved_run_dir = _validate_run_dir(
        run_dir,
        runs_root=Path(runs_root).resolve() if runs_root is not None else DEFAULT_RUNS_ROOT,
        custom_runs_root=runs_root is not None,
    )
    if validation_errors or resolved_run_dir is None:
        return ConsensusResult(
            status=STATUS_INVALID,
            consensus_decision=DECISION_BLOCKED,
            confidence=CONFIDENCE_LOW,
            reasons=["Consensus did not run because the run directory failed validation."],
            blocking_findings=validation_errors,
            warnings=[],
            signals_used={},
            agent_votes={},
            recommended_next_action="human_review_required",
            skill_evidence_status="SKIPPED",
            artifacts=[],
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
        )

    summary, summary_errors = _load_summary(resolved_run_dir)
    signals = _collect_signals(resolved_run_dir, summary)
    decision, reasons, blockers, warnings, votes, action, confidence = _decide(
        signals=signals,
        summary_errors=summary_errors,
        validation_warnings=validation_warnings,
    )
    status = STATUS_INVALID if summary_errors else STATUS_VALID
    validation_errors = list(summary_errors)
    result_without_artifacts = ConsensusResult(
        status=status,
        consensus_decision=decision,
        confidence=confidence,
        reasons=_dedupe(reasons),
        blocking_findings=_dedupe(blockers),
        warnings=_dedupe(warnings),
        signals_used=signals,
        agent_votes=votes,
        recommended_next_action=action,
        skill_evidence_status=_status(signals.get("skill_evidence_status")),
        artifacts=[],
        validation_errors=_dedupe(validation_errors),
        validation_warnings=_dedupe(validation_warnings),
    )
    artifacts = _write_artifacts(resolved_run_dir, result_without_artifacts)
    result = ConsensusResult(
        **{**result_without_artifacts.to_dict(), "artifacts": artifacts}
    )
    _write_json_artifact(resolved_run_dir / JSON_ARTIFACT, result)
    return result


def _validate_run_dir(
    run_dir: str | Path,
    *,
    runs_root: Path,
    custom_runs_root: bool,
) -> tuple[list[str], list[str], Path | None]:
    errors: list[str] = []
    warnings: list[str] = []
    text = str(run_dir).strip().strip('"').strip("'")
    if not text:
        return ["run_dir_missing"], warnings, None
    if ".." in text.replace("\\", "/").split("/"):
        return ["run_dir_path_traversal_blocked"], warnings, None
    candidate = Path(text)
    if not candidate.is_absolute():
        normalized = text.replace("\\", "/")
        if normalized.startswith("outputs/runs/"):
            candidate = REPO_ROOT / candidate
        else:
            candidate = runs_root / candidate
    resolved = candidate.resolve()
    root = runs_root.resolve()
    if not custom_runs_root and re.match(r"(?i)^(?:c:[\\/]|/mnt/c\b)", text):
        errors.append("run_dir_c_drive_blocked")
    if not _is_relative_to(resolved, root):
        errors.append("run_dir_must_be_inside_outputs_runs")
    if any(part.lower() in BLOCKED_PARTS for part in resolved.parts):
        errors.append("run_dir_protected_path_blocked")
    if not resolved.exists() or not resolved.is_dir():
        errors.append("run_dir_missing")
    if resolved.exists() and not _valid_run_id(resolved.name):
        errors.append("run_dir_invalid_run_id")
    return _dedupe(errors), _dedupe(warnings), resolved if not errors else None


def _load_summary(run_dir: Path) -> tuple[dict[str, Any], list[str]]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        return {}, ["missing_summary_json"]
    if not path.is_file():
        return {}, ["summary_json_not_file"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, ["invalid_summary_json"]
    if not isinstance(payload, dict):
        return {}, ["summary_json_not_object"]
    return payload, []


def _collect_signals(run_dir: Path, summary: dict[str, Any]) -> dict[str, Any]:
    parallel_gate = evaluate_parallel_review_gate(run_dir)
    parallel_review = _read_optional_json(run_dir / "37_parallel_review.json")
    skill_evidence = _read_optional_json(run_dir / "70_skill_evidence_bundle.json")
    failure_context = _read_latest_failure_context(run_dir)
    test_validity = _test_validity_from_summary_or_context(summary, failure_context)
    architecture_entropy = evaluate_architecture_entropy(run_dir, runs_root=run_dir.parent)
    return {
        "patch_quality_decision": _summary_text(summary, "patch_quality_decision"),
        "patch_quality_score": summary.get("patch_quality_score"),
        "patch_quality_reasons": _as_list(summary.get("patch_quality_reasons")),
        "patch_approval_decision": _summary_text(summary, "patch_approval_decision"),
        "patch_approval_validation_passed": summary.get("patch_approval_validation_passed"),
        "parallel_review_decision": parallel_gate.decision,
        "parallel_review_gate_allowed": parallel_gate.allowed,
        "parallel_review_gate_reason": parallel_gate.reason,
        "parallel_review_gate_validation_errors": parallel_gate.validation_errors,
        "parallel_review_warnings": _as_list(parallel_review.get("warnings")),
        "parallel_review_blocking_findings": _as_list(parallel_review.get("blocking_findings")),
        "parallel_review_agent_results": parallel_review.get("agent_results", {}),
        "parallel_review_style_only_disagreement": parallel_review.get("style_only_disagreement"),
        "human_approval_decision": _summary_text(summary, "human_approval_decision"),
        "human_approval_status": _summary_text(summary, "human_approval_status"),
        "patch_apply_status": _status(summary.get("patch_apply_status")),
        "test_runner_status": _status(summary.get("test_runner_status")),
        "test_validity_status": _status(test_validity.get("status")),
        "test_validity_classification": _status(test_validity.get("classification")),
        "test_validity_confidence": test_validity.get("confidence"),
        "test_validity_reasons": _as_list(test_validity.get("reasons")),
        "test_validity_recommended_next_action": str(test_validity.get("recommended_next_action") or ""),
        "test_validity_fix_policy": test_validity.get("fix_policy", {}),
        "contract_authority_status": _status(
            ((test_validity.get("contract_evidence") or {}).get("contract_authority") or {}).get("status")
        ),
        "contract_authority_owner": str(
            ((test_validity.get("contract_evidence") or {}).get("contract_authority") or {}).get("owner") or ""
        ),
        "architecture_entropy_status": _status(architecture_entropy.get("status")),
        "architecture_entropy_score": architecture_entropy.get("entropy_score"),
        "architecture_entropy_signals": _as_list(architecture_entropy.get("signals")),
        "architecture_entropy_hotspots": _as_list(architecture_entropy.get("hotspots")),
        "architecture_entropy_recommendations": _as_list(architecture_entropy.get("recommendations")),
        "architecture_entropy_recommended_next_action": str(architecture_entropy.get("recommended_next_action") or ""),
        "architecture_entropy_fix_policy": architecture_entropy.get("fix_policy", {}),
        "self_healing_status": _status(summary.get("self_healing_status")),
        "self_healing_last_patch": _summary_text(summary, "self_healing_last_patch")
        or _summary_text(summary, "self_healing_retry_patch"),
        "autonomous_loop_status": _status(summary.get("autonomous_loop_status")),
        "autonomous_loop_attempts": summary.get("autonomous_loop_attempts"),
        "autonomous_loop_max_attempts": summary.get("autonomous_loop_max_attempts"),
        "merge_readiness_decision": _summary_text(summary, "merge_readiness_decision"),
        "merge_readiness_status": _summary_text(summary, "merge_readiness_status"),
        "memory_enabled": summary.get("memory_enabled"),
        "knowledge_capture_status": _summary_text(summary, "knowledge_capture_status")
        or _summary_text(summary, "knowledge_status"),
        "has_patch_artifact": (run_dir / "12_patch_approval.md").exists()
        or (run_dir / "25_patch_quality.md").exists()
        or (run_dir / "patches").is_dir(),
        "has_consensus_artifacts": (run_dir / MARKDOWN_ARTIFACT).exists()
        or (run_dir / JSON_ARTIFACT).exists(),
        "skill_evidence_status": skill_evidence.get("status") or summary.get("skill_evidence_status"),
        "skill_evidence_items": skill_evidence.get("evidence_items", []),
    }


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_latest_failure_context(run_dir: Path) -> dict[str, Any]:
    candidates = [
        *sorted(run_dir.glob("37_failure_context_attempt_*.json"), reverse=True),
        run_dir / "06a_failure_context.json",
    ]
    for path in candidates:
        payload = _read_optional_json(path)
        if payload:
            return payload
    return {}


def _test_validity_from_summary_or_context(
    summary: dict[str, Any],
    failure_context: dict[str, Any],
) -> dict[str, Any]:
    if summary.get("test_validity_status"):
        return {
            "status": summary.get("test_validity_status"),
            "classification": summary.get("test_validity_classification", ""),
            "confidence": summary.get("test_validity_confidence"),
            "reasons": _as_list(summary.get("test_validity_reasons")),
            "recommended_next_action": summary.get("test_validity_recommended_next_action", ""),
            "fix_policy": summary.get("test_validity_fix_policy", {}),
        }
    value = failure_context.get("test_validity")
    return value if isinstance(value, dict) else {}


def _decide(
    *,
    signals: dict[str, Any],
    summary_errors: list[str],
    validation_warnings: list[str],
) -> tuple[str, list[str], list[str], list[str], dict[str, str], str, str]:
    reasons: list[str] = []
    blockers: list[str] = []
    warnings = list(validation_warnings)
    votes = _agent_votes(signals, summary_errors=summary_errors)

    if summary_errors:
        blockers.extend(summary_errors)
        reasons.append("Required run summary is missing or invalid.")
        return (
            DECISION_BLOCKED,
            reasons,
            blockers,
            warnings,
            votes,
            "repair_or_regenerate_summary_then_rerun_consensus",
            CONFIDENCE_LOW,
        )

    parallel_decision = signals["parallel_review_decision"]
    patch_quality = _upper(signals["patch_quality_decision"])
    patch_approval = signals["patch_approval_decision"]
    patch_apply = signals["patch_apply_status"]
    tests = signals["test_runner_status"]
    autonomous = signals["autonomous_loop_status"]
    merge = _upper(signals["merge_readiness_decision"])
    has_patch = bool(signals["has_patch_artifact"])

    if parallel_decision == PARALLEL_BLOCKED:
        blockers.append("Parallel Review Gate is BLOCKED.")
        blockers.extend(str(item) for item in signals.get("parallel_review_gate_validation_errors", []))
        reasons.append(str(signals["parallel_review_gate_reason"]))
        return (
            DECISION_BLOCKED,
            reasons,
            blockers,
            warnings,
            votes,
            "resolve_parallel_review_blockers",
            CONFIDENCE_HIGH,
        )

    if autonomous == DECISION_FAILED_PERMANENTLY:
        blockers.append("Autonomous Loop exhausted retry attempts.")
        reasons.append("Autonomous Loop status is FAILED_PERMANENTLY.")
        return (
            DECISION_FAILED_PERMANENTLY,
            reasons,
            blockers,
            warnings,
            votes,
            "escalate_to_human_engineer_with_retry_history",
            CONFIDENCE_HIGH,
        )

    failed_statuses = {"FAILED", "FAILED_TESTS", "TIMEOUT"}
    if tests in failed_statuses and _test_validity_blocks_code_retry(signals):
        validity = signals.get("test_validity_status") or "UNKNOWN"
        classification = signals.get("test_validity_classification") or "UNKNOWN"
        blockers.append(f"Test Runner reported {tests}, but Test Validity Gate classified it as {classification}.")
        reasons.append(
            f"Test Validity Gate status is {validity}; do not rewrite code under test until the test contract is validated."
        )
        warnings.extend(str(item) for item in signals.get("test_validity_reasons", []))
        return (
            DECISION_NEEDS_REVISION,
            reasons,
            blockers,
            warnings,
            votes,
            "challenge_or_repair_test_contract_before_code_fix",
            CONFIDENCE_HIGH if validity == "TEST_EXPECTATION_SUSPECT" else CONFIDENCE_MEDIUM,
        )

    if _architecture_entropy_requires_refactor(signals):
        status = signals.get("architecture_entropy_status") or "UNKNOWN"
        score = signals.get("architecture_entropy_score")
        blockers.append(f"Architecture Entropy Gate reported {status} with score {score}.")
        reasons.append("Repeated localized fixes or complexity signals require architecture-level refactor review.")
        warnings.extend(str(item) for item in signals.get("architecture_entropy_recommendations", []))
        return (
            DECISION_NEEDS_REVISION,
            reasons,
            blockers,
            warnings,
            votes,
            "run_architecture_refactor_review",
            CONFIDENCE_HIGH if status == "ARCHITECTURE_REVIEW_REQUIRED" else CONFIDENCE_MEDIUM,
        )

    if tests in failed_statuses and _retry_patch_available(signals):
        reasons.append("Tests failed and Self Healing produced retry context.")
        warnings.append("Retry must still pass quality, approval, human approval, apply, and test gates.")
        return (
            DECISION_RETRY_RECOMMENDED,
            reasons,
            blockers,
            warnings,
            votes,
            "run_guarded_retry_loop",
            CONFIDENCE_HIGH,
        )

    if tests in failed_statuses:
        blockers.append(f"Test Runner reported {tests}.")
        reasons.append("Failed tests need a repair plan before apply or merge.")
        return (
            DECISION_NEEDS_REVISION,
            reasons,
            blockers,
            warnings,
            votes,
            "run_self_healing_or_request_revision",
            CONFIDENCE_HIGH,
        )

    revision_decisions = {"NEEDS_REVISION", "NEEDS_RELOCATION", "LOW_VALUE_COMMENT_ONLY", "UNCONNECTED_LOGIC"}
    if parallel_decision == PARALLEL_NEEDS_REVISION or patch_quality in revision_decisions:
        if _style_only_disagreement_suppressed(signals):
            reasons.append("Style-only disagreement was suppressed because no functional evidence requires revision.")
            warnings.append("Stylistic review feedback was recorded as advisory and did not consume retry attempts.")
            votes["style_disagreement_suppression"] = DECISION_NO_ACTION
            return (
                DECISION_NO_ACTION,
                reasons,
                blockers,
                warnings,
                votes,
                "wait_for_functional_evidence_or_user_preference",
                CONFIDENCE_HIGH,
            )
        reasons.append("One or more review signals require revision before normal apply.")
        return (
            DECISION_NEEDS_REVISION,
            reasons,
            blockers,
            warnings,
            votes,
            "revise_patch_or_enter_retry_loop",
            CONFIDENCE_HIGH,
        )

    if _is_contradictory(signals):
        blockers.append("Signals are contradictory across apply, tests, and readiness.")
        reasons.append("Consensus cannot safely recommend apply from contradictory signals.")
        return (
            DECISION_NEEDS_REVISION,
            reasons,
            blockers,
            warnings,
            votes,
            "review_contradictory_signals",
            CONFIDENCE_MEDIUM,
        )

    no_action_statuses = {"", "UNKNOWN", "SKIPPED", "NOT_RUN", "NOT RUN"}
    if not has_patch or (
        patch_quality in no_action_statuses
        and _upper(patch_approval) in no_action_statuses
        and patch_apply in no_action_statuses
        and tests in no_action_statuses
    ):
        reasons.append("No applicable patch or active execution signal was found.")
        return (
            DECISION_NO_ACTION,
            reasons,
            blockers,
            warnings,
            votes,
            "wait_for_new_plan_or_patch",
            CONFIDENCE_MEDIUM,
        )

    approved_quality = patch_quality in {"IMPLEMENTATION_READY", "APPROVED", "PASS", "PASSED"}
    approved_review = parallel_decision == "APPROVED"
    approved_patch = patch_approval == "Approved"
    no_apply_failure = patch_apply not in {"FAILED", "REJECTED", "DRY_RUN_FAILED"}
    tests_safe = tests in {"", "UNKNOWN", "SKIPPED", "NO_TESTS_DETECTED", "PASSED"}
    ready_to_apply = merge in {"", "UNKNOWN", "READY TO APPLY", "READY_TO_APPLY"}

    if approved_quality and approved_review and approved_patch and no_apply_failure and tests_safe and ready_to_apply:
        reasons.append("Patch quality, parallel review, and patch approval all allow guarded apply.")
        return (
            DECISION_APPROVED_TO_APPLY,
            reasons,
            blockers,
            warnings,
            votes,
            "request_human_approval_then_patch_apply",
            CONFIDENCE_HIGH,
        )

    reasons.append("Signals are incomplete or not strong enough for guarded apply.")
    return (
        DECISION_NEEDS_REVISION,
        reasons,
        blockers,
        warnings,
        votes,
        "complete_missing_signals_or_request_revision",
        CONFIDENCE_MEDIUM,
    )


def _agent_votes(signals: dict[str, Any], *, summary_errors: list[str]) -> dict[str, str]:
    if summary_errors:
        return {"summary": DECISION_BLOCKED}
    votes: dict[str, str] = {}
    quality = _upper(signals["patch_quality_decision"])
    votes["patch_quality"] = (
        DECISION_APPROVED_TO_APPLY
        if quality in {"IMPLEMENTATION_READY", "APPROVED", "PASS", "PASSED"}
        else DECISION_NEEDS_REVISION
        if quality
        else DECISION_NO_ACTION
    )
    parallel = signals["parallel_review_decision"]
    votes["parallel_review"] = (
        DECISION_BLOCKED
        if parallel == PARALLEL_BLOCKED
        else DECISION_NEEDS_REVISION
        if parallel == PARALLEL_NEEDS_REVISION
        else DECISION_APPROVED_TO_APPLY
    )
    votes["patch_approval"] = (
        DECISION_APPROVED_TO_APPLY
        if signals["patch_approval_decision"] == "Approved"
        else DECISION_NEEDS_REVISION
        if signals["patch_approval_decision"]
        else DECISION_NO_ACTION
    )
    tests = signals["test_runner_status"]
    votes["test_runner"] = (
        DECISION_RETRY_RECOMMENDED
        if tests in {"FAILED", "FAILED_TESTS", "TIMEOUT"} and _retry_patch_available(signals)
        else DECISION_NEEDS_REVISION
        if tests in {"FAILED", "FAILED_TESTS", "TIMEOUT"}
        else DECISION_APPROVED_TO_APPLY
        if tests in {"PASSED", "NO_TESTS_DETECTED"}
        else DECISION_NO_ACTION
    )
    if _test_validity_blocks_code_retry(signals):
        votes["test_validity"] = DECISION_NEEDS_REVISION
    if _architecture_entropy_requires_refactor(signals):
        votes["architecture_entropy"] = DECISION_NEEDS_REVISION
    votes["self_healing"] = (
        DECISION_RETRY_RECOMMENDED
        if _retry_patch_available(signals)
        else DECISION_NO_ACTION
    )
    votes["autonomous_loop"] = (
        DECISION_FAILED_PERMANENTLY
        if signals["autonomous_loop_status"] == DECISION_FAILED_PERMANENTLY
        else DECISION_APPROVED_TO_APPLY
        if signals["autonomous_loop_status"] == "PASSED"
        else DECISION_NO_ACTION
    )
    if _style_only_disagreement_suppressed(signals):
        votes["style_disagreement_suppression"] = DECISION_NO_ACTION
    return votes


def _write_artifacts(run_dir: Path, result: ConsensusResult) -> list[str]:
    markdown_path = run_dir / MARKDOWN_ARTIFACT
    json_path = run_dir / JSON_ARTIFACT
    markdown_path.write_text(_render_markdown(result, artifacts=[str(markdown_path), str(json_path)]), encoding="utf-8")
    return [str(markdown_path), str(json_path)]


def _write_json_artifact(path: Path, result: ConsensusResult) -> None:
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def _render_markdown(result: ConsensusResult, *, artifacts: list[str]) -> str:
    return "\n".join(
        [
            "# ANN Consensus Decision",
            "",
            "## Decision",
            f"- Status: {result.status}",
            f"- Consensus decision: {result.consensus_decision}",
            f"- Confidence: {result.confidence}",
            f"- Recommended next action: {result.recommended_next_action}",
            f"- Skill evidence status: {result.skill_evidence_status}",
            f"- Generated at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            "",
            "## Reasons",
            *_bullets(result.reasons),
            "",
            "## Blocking Findings",
            *_bullets(result.blocking_findings or ["None"]),
            "",
            "## Warnings",
            *_bullets(result.warnings or ["None"]),
            "",
            "## Agent Votes",
            *_bullets([f"{name}: {vote}" for name, vote in result.agent_votes.items()] or ["None"]),
            "",
            "## Signals Used",
            "```json",
            json.dumps(result.signals_used, indent=2),
            "```",
            "",
            "## Artifacts Created",
            *_bullets(artifacts),
            "",
        ]
    ).rstrip() + "\n"


def _is_contradictory(signals: dict[str, Any]) -> bool:
    tests = signals["test_runner_status"]
    patch_apply = signals["patch_apply_status"]
    merge = _upper(signals["merge_readiness_decision"])
    if patch_apply == "APPLIED" and tests in {"FAILED", "FAILED_TESTS", "TIMEOUT"} and merge in {"READY TO MERGE", "READY_TO_MERGE"}:
        return True
    if patch_apply in {"FAILED", "REJECTED", "DRY_RUN_FAILED"} and merge in {"READY TO APPLY", "READY_TO_APPLY", "READY TO MERGE", "READY_TO_MERGE"}:
        return True
    return False


def _retry_patch_available(signals: dict[str, Any]) -> bool:
    status = signals["self_healing_status"]
    patch = str(signals.get("self_healing_last_patch") or "").strip()
    return status in {"RETRY_PATCH_GENERATED", "PASSED"} or bool(patch)


def _test_validity_blocks_code_retry(signals: dict[str, Any]) -> bool:
    status = signals.get("test_validity_status")
    classification = signals.get("test_validity_classification")
    if status in {"TEST_EXPECTATION_SUSPECT", "TEST_CONTRACT_AMBIGUOUS"}:
        return True
    return classification in {"TEST_EXPECTATION_SUSPECT", "TEST_FIXTURE_SUSPECT", "AMBIGUOUS"} and status not in {
        "",
        "UNKNOWN",
        "VALID_TEST_FAILURE",
    }


def _architecture_entropy_requires_refactor(signals: dict[str, Any]) -> bool:
    return signals.get("architecture_entropy_status") in {
        "REFACTOR_RECOMMENDED",
        "ARCHITECTURE_REVIEW_REQUIRED",
    }


def _style_only_disagreement_suppressed(signals: dict[str, Any]) -> bool:
    if _has_functional_blocker(signals):
        return False
    patch_quality = _upper(signals.get("patch_quality_decision"))
    style_evidence = patch_quality in STYLE_ONLY_PATCH_QUALITY
    text_evidence = _style_evidence_text(signals)
    if _is_style_only_text(text_evidence):
        style_evidence = True
    if signals.get("parallel_review_style_only_disagreement") is True:
        style_evidence = True
    if not style_evidence:
        return False
    tests = signals.get("test_runner_status")
    patch_apply = signals.get("patch_apply_status")
    patch_approval = str(signals.get("patch_approval_decision") or "")
    if tests not in {"", "UNKNOWN", "SKIPPED", "NOT_RUN", "NOT RUN", "NO_TESTS_DETECTED", "PASSED"}:
        return False
    if patch_apply in {"FAILED", "REJECTED", "DRY_RUN_FAILED"}:
        return False
    if patch_approval and patch_approval not in {"Approved", "Skipped", "SKIPPED"}:
        return False
    return True


def _has_functional_blocker(signals: dict[str, Any]) -> bool:
    patch_quality = _upper(signals.get("patch_quality_decision"))
    if signals.get("parallel_review_decision") == PARALLEL_BLOCKED:
        return True
    if _as_list(signals.get("parallel_review_blocking_findings")):
        return True
    if patch_quality in {"REJECTED", "NEEDS_RELOCATION", "UNCONNECTED_LOGIC"}:
        return True
    if signals.get("test_runner_status") in {"FAILED", "FAILED_TESTS", "TIMEOUT"}:
        return True
    if signals.get("patch_apply_status") in {"FAILED", "REJECTED", "DRY_RUN_FAILED"}:
        return True
    if signals.get("autonomous_loop_status") == DECISION_FAILED_PERMANENTLY:
        return True
    if _retry_patch_available(signals):
        return True
    text = _style_evidence_text(signals)
    return _contains_functional_terms(text)


def _style_evidence_text(signals: dict[str, Any]) -> str:
    values: list[Any] = [
        signals.get("patch_quality_decision"),
        signals.get("patch_quality_reasons"),
        signals.get("parallel_review_gate_reason"),
        signals.get("parallel_review_warnings"),
        signals.get("parallel_review_agent_results"),
    ]
    return json.dumps(values, sort_keys=True, default=str).lower()


def _is_style_only_text(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in STYLE_TERMS) and not _contains_functional_terms(lowered)


def _contains_functional_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in FUNCTIONAL_TERMS)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None or value == "":
        return []
    return [value]


def _summary_text(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _status(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id)) and run_id not in {".", ".."}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
