"""Reusable deterministic gate for Parallel Review decisions.

The gate is intentionally read-only and independent from UI, Patch Approval,
and pipeline runner semantics. It exposes a small system capability that other
ANN subsystems can query before continuing with authorization, apply, or
autonomous repair work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PARALLEL_REVIEW_JSON = "37_parallel_review.json"

DECISION_APPROVED = "APPROVED"
DECISION_NEEDS_REVISION = "NEEDS_REVISION"
DECISION_BLOCKED = "BLOCKED"
ALLOWED_DECISIONS = {DECISION_APPROVED, DECISION_NEEDS_REVISION, DECISION_BLOCKED}


@dataclass(frozen=True)
class ParallelGateDecision:
    """Decision returned by the reusable Parallel Review Gate."""

    allowed: bool
    decision: str
    reason: str
    blocks_human_approval: bool
    blocks_patch_apply: bool
    blocks_autonomous_loop: bool
    validation_errors: list[str]


def evaluate_parallel_review_gate(run_dir: str | Path) -> ParallelGateDecision:
    """Evaluate the Parallel Review Gate for a run directory.

    Missing Parallel Review artifacts are non-blocking to preserve compatibility
    with existing ANN runs. Invalid artifacts fail closed.
    """

    validation_errors: list[str] = []
    resolved_run_dir = Path(run_dir).resolve()
    artifact = resolved_run_dir / PARALLEL_REVIEW_JSON
    if not artifact.exists():
        return _decision(
            DECISION_APPROVED,
            reason="parallel_review_artifact_missing_non_blocking",
        )
    if not artifact.is_file():
        return _blocked("parallel_review_artifact_not_file")

    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _blocked("parallel_review_json_invalid")
    if not isinstance(payload, dict):
        return _blocked("parallel_review_json_not_object")

    raw_decision = str(payload.get("decision") or "").strip().upper()
    if raw_decision not in ALLOWED_DECISIONS:
        validation_errors.append(f"parallel_review_decision_invalid:{raw_decision or 'MISSING'}")
        return _decision(
            DECISION_BLOCKED,
            reason="parallel_review_decision_invalid",
            validation_errors=validation_errors,
        )

    reason = _reason_from_payload(payload, raw_decision)
    if raw_decision == DECISION_BLOCKED:
        return _decision(raw_decision, reason=reason, validation_errors=_payload_errors(payload))
    if raw_decision == DECISION_NEEDS_REVISION:
        return ParallelGateDecision(
            allowed=False,
            decision=DECISION_NEEDS_REVISION,
            reason=reason,
            blocks_human_approval=False,
            blocks_patch_apply=True,
            blocks_autonomous_loop=False,
            validation_errors=_payload_errors(payload),
        )
    return _decision(raw_decision, reason=reason, validation_errors=_payload_errors(payload))


def parallel_gate_summary_fields(decision: ParallelGateDecision) -> dict[str, Any]:
    """Return serializable summary fields for callers that choose to persist state."""

    return {
        "parallel_review_gate_allowed": decision.allowed,
        "parallel_review_gate_decision": decision.decision,
        "parallel_review_gate_reason": decision.reason,
        "parallel_review_gate_blocks_human_approval": decision.blocks_human_approval,
        "parallel_review_gate_blocks_patch_apply": decision.blocks_patch_apply,
        "parallel_review_gate_blocks_autonomous_loop": decision.blocks_autonomous_loop,
        "parallel_review_gate_validation_errors": decision.validation_errors,
    }


def _blocked(reason: str) -> ParallelGateDecision:
    return _decision(DECISION_BLOCKED, reason=reason, validation_errors=[reason])


def _decision(
    decision: str,
    *,
    reason: str,
    validation_errors: list[str] | None = None,
) -> ParallelGateDecision:
    validation_errors = validation_errors or []
    blocked = decision == DECISION_BLOCKED
    return ParallelGateDecision(
        allowed=not blocked and not validation_errors,
        decision=decision,
        reason=reason,
        blocks_human_approval=blocked,
        blocks_patch_apply=blocked,
        blocks_autonomous_loop=blocked,
        validation_errors=_dedupe(validation_errors),
    )


def _payload_errors(payload: dict[str, Any]) -> list[str]:
    errors = payload.get("validation_errors", [])
    if isinstance(errors, list):
        return _dedupe([str(error) for error in errors])
    if errors:
        return [f"parallel_review_validation_errors_not_list:{type(errors).__name__}"]
    return []


def _reason_from_payload(payload: dict[str, Any], decision: str) -> str:
    summary = str(payload.get("consensus_summary") or "").strip()
    if summary:
        return summary
    if decision == DECISION_APPROVED:
        return "parallel_review_approved"
    if decision == DECISION_NEEDS_REVISION:
        return "parallel_review_needs_revision"
    return "parallel_review_blocked"


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
