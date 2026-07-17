"""Deterministic product contract arbitration.

This module answers one narrow question: when generated artifacts disagree,
which artifact owns the product contract? It is read-only and does not ask an
LLM to arbitrate semantics.
"""

from __future__ import annotations

import re
from typing import Any

STATUS_CONTRACT_RESOLVED = "CONTRACT_RESOLVED"
STATUS_CONTRACT_CONFLICT = "CONTRACT_CONFLICT"
STATUS_CONTRACT_AMBIGUOUS = "CONTRACT_AMBIGUOUS"
STATUS_CONTRACT_MISSING = "CONTRACT_MISSING"

OWNER_USER_REQUEST = "USER_REQUEST"
OWNER_PRODUCT_AGENT_REQUIREMENTS = "PRODUCT_AGENT_REQUIREMENTS"
OWNER_ARCHITECTURE_PLAN = "ARCHITECTURE_PLAN"
OWNER_TEST_PLAN = "TEST_PLAN"
OWNER_HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"

AUTHORITY_ORDER = (
    OWNER_USER_REQUEST,
    OWNER_PRODUCT_AGENT_REQUIREMENTS,
    OWNER_ARCHITECTURE_PLAN,
    OWNER_TEST_PLAN,
)
FINAL_CONTRACT_OWNERS = {
    OWNER_USER_REQUEST,
    OWNER_PRODUCT_AGENT_REQUIREMENTS,
    OWNER_ARCHITECTURE_PLAN,
}
SOURCE_FIELDS = {
    OWNER_USER_REQUEST: "user_request",
    OWNER_PRODUCT_AGENT_REQUIREMENTS: "product_requirements",
    OWNER_ARCHITECTURE_PLAN: "architecture_plan",
    OWNER_TEST_PLAN: "test_plan",
}
TYPE_TERMS: dict[str, set[str]] = {
    "integer": {"integer", "int", "whole number"},
    "float": {"float", "decimal", "double", "number with decimals", "fractional", "money", "currency"},
    "string": {"string", "str", "text"},
    "boolean": {"boolean", "bool", "true/false"},
    "list": {"list", "array"},
    "object": {"object", "dict", "map", "json object"},
}
CONFLICTS = {
    ("integer", "float"),
    ("float", "integer"),
    ("string", "integer"),
    ("integer", "string"),
    ("boolean", "string"),
    ("string", "boolean"),
}


def evaluate_contract_arbitration(
    *,
    user_request: str = "",
    product_requirements: str = "",
    architecture_plan: str = "",
    test_plan: str = "",
    assertion_evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Determine the highest-authority contract evidence for a dispute."""

    source_text = {
        OWNER_USER_REQUEST: user_request,
        OWNER_PRODUCT_AGENT_REQUIREMENTS: product_requirements,
        OWNER_ARCHITECTURE_PLAN: architecture_plan,
        OWNER_TEST_PLAN: test_plan,
    }
    types_by_owner = {
        owner: sorted(_detect_type_terms(text))
        for owner, text in source_text.items()
        if text.strip()
    }
    present_owners = [owner for owner in AUTHORITY_ORDER if source_text[owner].strip()]
    assertion_types = sorted(_detect_type_terms("\n".join(assertion_evidence or [])))
    authoritative_owner = _first_owner_with_types(types_by_owner)
    conflicts = _cross_source_conflicts(types_by_owner)
    assertion_conflicts = (
        _type_conflicts(set(types_by_owner.get(authoritative_owner, [])), set(assertion_types))
        if authoritative_owner
        else []
    )
    reasons: list[str] = []
    warnings: list[str] = []

    if not present_owners:
        status = STATUS_CONTRACT_MISSING
        owner = OWNER_HUMAN_REVIEW_REQUIRED
        confidence = 0.2
        reasons.append("No user, product, architecture, or test contract text was available.")
    elif authoritative_owner is None:
        status = STATUS_CONTRACT_AMBIGUOUS
        owner = OWNER_HUMAN_REVIEW_REQUIRED
        confidence = 0.42
        reasons.append("Contract artifacts exist, but no deterministic contract terms were found.")
    elif _higher_authority_conflicts(conflicts, authoritative_owner):
        status = STATUS_CONTRACT_CONFLICT
        owner = OWNER_HUMAN_REVIEW_REQUIRED
        confidence = 0.52
        reasons.append("Higher-authority contract artifacts disagree and require Product/Human arbitration.")
    else:
        status = STATUS_CONTRACT_RESOLVED
        owner = authoritative_owner
        confidence = 0.9 if owner in {OWNER_USER_REQUEST, OWNER_PRODUCT_AGENT_REQUIREMENTS} else 0.68
        reasons.append(f"{owner} is the highest-authority artifact with deterministic contract terms.")
        if conflicts:
            warnings.append("lower_authority_contract_conflict_detected")

    return {
        "version": "1.0",
        "status": status,
        "owner": owner,
        "authority_order": list(AUTHORITY_ORDER),
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "warnings": warnings,
        "types_by_owner": types_by_owner,
        "assertion_types": assertion_types,
        "cross_source_conflicts": [f"{left_owner}:{left}_vs_{right_owner}:{right}" for left_owner, left, right_owner, right in conflicts],
        "assertion_conflicts_with_owner": [f"{left}_vs_{right}" for left, right in assertion_conflicts],
        "recommended_next_action": _recommended_action(status, owner),
        "policy": {
            "user_request_overrides_generated_artifacts": True,
            "product_requirements_override_architecture_and_tests": True,
            "test_plan_never_overrides_product_requirements": True,
            "ambiguous_contract_requires_product_or_human_arbitration": status
            in {STATUS_CONTRACT_AMBIGUOUS, STATUS_CONTRACT_CONFLICT, STATUS_CONTRACT_MISSING},
        },
        "safety": {
            "read_only": True,
            "no_shell": True,
            "no_install": True,
            "no_network": True,
        },
    }


def _first_owner_with_types(types_by_owner: dict[str, list[str]]) -> str | None:
    for owner in AUTHORITY_ORDER:
        if owner in FINAL_CONTRACT_OWNERS and types_by_owner.get(owner):
            return owner
    return None


def _higher_authority_conflicts(
    conflicts: list[tuple[str, str, str, str]],
    authoritative_owner: str,
) -> bool:
    authoritative_rank = AUTHORITY_ORDER.index(authoritative_owner)
    for left_owner, _left, right_owner, _right in conflicts:
        if AUTHORITY_ORDER.index(left_owner) <= authoritative_rank and AUTHORITY_ORDER.index(right_owner) <= authoritative_rank:
            return True
    return False


def _cross_source_conflicts(types_by_owner: dict[str, list[str]]) -> list[tuple[str, str, str, str]]:
    conflicts: list[tuple[str, str, str, str]] = []
    owners = [owner for owner in AUTHORITY_ORDER if types_by_owner.get(owner)]
    for left_index, left_owner in enumerate(owners):
        for right_owner in owners[left_index + 1 :]:
            for left, right in _type_conflicts(set(types_by_owner[left_owner]), set(types_by_owner[right_owner])):
                conflicts.append((left_owner, left, right_owner, right))
    return conflicts[:8]


def _type_conflicts(left_types: set[str], right_types: set[str]) -> list[tuple[str, str]]:
    return sorted((left, right) for left in left_types for right in right_types if (left, right) in CONFLICTS)


def _detect_type_terms(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for label, terms in TYPE_TERMS.items():
        if any(_contains_word_or_phrase(lowered, term) for term in terms):
            found.add(label)
    return found


def _contains_word_or_phrase(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


def _recommended_action(status: str, owner: str) -> str:
    if status == STATUS_CONTRACT_RESOLVED:
        return f"use_{owner.lower()}_as_contract_authority"
    if status == STATUS_CONTRACT_CONFLICT:
        return "request_product_agent_or_human_contract_arbitration"
    if status == STATUS_CONTRACT_AMBIGUOUS:
        return "ask_clarifying_question_or_product_agent_contract_refinement"
    return "collect_product_contract_before_fixing_code_or_tests"
