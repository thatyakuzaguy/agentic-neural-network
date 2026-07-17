"""Deterministic read-only gate for validating failed test evidence.

The gate exists to prevent ANN from treating every failed test as proof that
application code is wrong. It classifies whether the code under test, the test
expectation, a fixture/integration boundary, or the contract itself should be
investigated first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentic_network.contract_arbitration.runtime import (
    STATUS_CONTRACT_RESOLVED,
    evaluate_contract_arbitration,
)

STATUS_VALID_TEST_FAILURE = "VALID_TEST_FAILURE"
STATUS_TEST_EXPECTATION_SUSPECT = "TEST_EXPECTATION_SUSPECT"
STATUS_TEST_CONTRACT_AMBIGUOUS = "TEST_CONTRACT_AMBIGUOUS"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

CLASSIFICATION_CODE_UNDER_TEST_SUSPECT = "CODE_UNDER_TEST_SUSPECT"
CLASSIFICATION_TEST_EXPECTATION_SUSPECT = "TEST_EXPECTATION_SUSPECT"
CLASSIFICATION_TEST_FIXTURE_SUSPECT = "TEST_FIXTURE_SUSPECT"
CLASSIFICATION_AMBIGUOUS = "AMBIGUOUS"

ASSERTION_PATTERNS = (
    re.compile(r"AssertionError(?::\s*(?P<message>.*))?", re.IGNORECASE),
    re.compile(r"\bassert\b.+", re.IGNORECASE),
    re.compile(r"\bexpected\b.+\b(?:got|actual)\b.+", re.IGNORECASE),
)
TEST_PATH_PATTERN = re.compile(r"(?i)(?:^|[\\/])(?:tests?|__tests__|specs?)[\\/]|(?:^|[\\/])test_[^\\/]+\.py$")
RUNTIME_EXCEPTION_PATTERN = re.compile(
    r"\b(?:NameError|TypeError|ValueError|KeyError|AttributeError|ImportError|ModuleNotFoundError|SyntaxError)\b"
)
FIXTURE_TERMS = {
    "fixture",
    "mock",
    "monkeypatch",
    "factory",
    "seed",
    "migration",
    "docker",
    "compose",
    "database",
    "redis",
    "postgres",
    "webhook",
    "env",
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


def evaluate_test_validity_gate(
    *,
    test_report: str = "",
    stdout: str = "",
    stderr: str = "",
    user_request: str = "",
    product_requirements: str = "",
    architecture_plan: str = "",
    test_plan: str = "",
    code_plan: str = "",
    targets: list[dict[str, Any]] | None = None,
    affected_files: list[str] | None = None,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Classify failed test evidence without executing commands or mutating files."""

    targets = targets or []
    affected_files = affected_files or []
    artifact_paths = artifact_paths or {}
    failure_text = "\n".join(value for value in (test_report, stdout, stderr) if value)
    contract_text = "\n".join(
        value for value in (product_requirements, architecture_plan, test_plan, code_plan) if value
    )
    assertion_evidence = _assertion_evidence(failure_text)
    test_paths = _test_paths(targets, affected_files, failure_text)
    contract_authority = evaluate_contract_arbitration(
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
        test_plan=test_plan,
        assertion_evidence=assertion_evidence,
    )
    authoritative_types = set(
        contract_authority.get("types_by_owner", {}).get(str(contract_authority.get("owner") or ""), [])
    )
    contract_types = authoritative_types or _detect_type_terms(contract_text)
    assertion_types = _detect_type_terms("\n".join(assertion_evidence))
    conflicts = _type_conflicts(contract_types, assertion_types)
    reasons: list[str] = []
    warnings: list[str] = []

    if not failure_text.strip():
        status = STATUS_INSUFFICIENT_EVIDENCE
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.2
        reasons.append("No failed test output was available.")
    elif conflicts and assertion_evidence and contract_authority.get("status") == STATUS_CONTRACT_RESOLVED:
        status = STATUS_TEST_EXPECTATION_SUSPECT
        classification = CLASSIFICATION_TEST_EXPECTATION_SUSPECT
        confidence = 0.86 if test_paths else 0.78
        reasons.append(
            "Assertion expectation conflicts with product/architecture/test contract: "
            + ", ".join(f"{left}_vs_{right}" for left, right in conflicts)
        )
        if test_paths:
            reasons.append("Failure target is in test code, so the assertion itself must be reviewed first.")
    elif _fixture_suspect(failure_text, test_paths):
        status = STATUS_TEST_CONTRACT_AMBIGUOUS
        classification = CLASSIFICATION_TEST_FIXTURE_SUSPECT
        confidence = 0.72
        reasons.append("Failure includes fixture, mock, environment, or integration-boundary signals.")
    elif assertion_evidence and contract_authority.get("status") != STATUS_CONTRACT_RESOLVED:
        status = STATUS_TEST_CONTRACT_AMBIGUOUS
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.62
        reasons.append(
            "Assertion failed, but Product Contract Arbitration did not find a resolved authoritative contract."
        )
    elif assertion_evidence and test_paths and not contract_text.strip():
        status = STATUS_TEST_CONTRACT_AMBIGUOUS
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.58
        reasons.append("Assertion failed in test code, but no contract text was available to validate the expectation.")
    elif assertion_evidence and test_paths:
        status = STATUS_TEST_CONTRACT_AMBIGUOUS
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.55
        reasons.append("Assertion failed in test code; contract evidence is not strong enough to blame code automatically.")
    elif RUNTIME_EXCEPTION_PATTERN.search(failure_text):
        status = STATUS_VALID_TEST_FAILURE
        classification = CLASSIFICATION_CODE_UNDER_TEST_SUSPECT
        confidence = 0.76
        reasons.append("Runtime exception points to executable code behavior rather than only a test expectation.")
    elif assertion_evidence:
        status = STATUS_TEST_CONTRACT_AMBIGUOUS
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.5
        reasons.append("Assertion failed, but the evidence does not isolate whether the test or implementation is wrong.")
    else:
        status = STATUS_INSUFFICIENT_EVIDENCE
        classification = CLASSIFICATION_AMBIGUOUS
        confidence = 0.35
        reasons.append("Failure text does not contain a recognized assertion or runtime exception.")

    if not contract_text.strip():
        warnings.append("contract_text_missing")

    return {
        "version": "1.0",
        "status": status,
        "classification": classification,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "warnings": warnings,
        "test_targets": test_paths,
        "assertion_evidence": assertion_evidence[:8],
        "contract_evidence": {
            "contract_authority": contract_authority,
            "contract_types": sorted(contract_types),
            "assertion_types": sorted(assertion_types),
            "conflicts": [f"{left}_vs_{right}" for left, right in conflicts],
            "artifact_paths_used": {
                key: value
                for key, value in artifact_paths.items()
                if key in {"product", "architect", "test", "test_revised", "failure_context"}
            },
        },
        "recommended_next_action": _recommended_action(status, classification),
        "fix_policy": {
            "do_not_modify_code_under_test_until_test_contract_validated": status
            in {STATUS_TEST_EXPECTATION_SUSPECT, STATUS_TEST_CONTRACT_AMBIGUOUS},
            "allow_test_or_fixture_patch_when_contract_conflict_is_confirmed": status
            == STATUS_TEST_EXPECTATION_SUSPECT,
            "require_human_or_reviewer_contract_check_when_ambiguous": status
            in {STATUS_TEST_CONTRACT_AMBIGUOUS, STATUS_INSUFFICIENT_EVIDENCE},
            "failed_tests_remain_blocking_until_validity_resolved": True,
        },
        "safety": {
            "read_only": True,
            "no_shell": True,
            "no_install": True,
            "no_network": True,
        },
    }


def _assertion_evidence(text: str) -> list[str]:
    evidence: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in ASSERTION_PATTERNS):
            evidence.append(stripped[:500])
    return _dedupe(evidence)


def _test_paths(
    targets: list[dict[str, Any]],
    affected_files: list[str],
    failure_text: str,
) -> list[str]:
    paths: list[str] = []
    for target in targets:
        path = str(target.get("path") or "")
        if path:
            paths.append(path)
    paths.extend(str(path) for path in affected_files if str(path).strip())
    for match in re.findall(r"(?m)([A-Za-z]:[^:\n]+|/[^:\n]+|[\w./\\-]+\.(?:py|tsx?|jsx?)):\d+", failure_text):
        paths.append(match)
    return [path for path in _dedupe(_normalize_path(path) for path in paths) if TEST_PATH_PATTERN.search(path)]


def _detect_type_terms(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for label, terms in TYPE_TERMS.items():
        if any(_contains_word_or_phrase(lowered, term) for term in terms):
            found.add(label)
    return found


def _type_conflicts(contract_types: set[str], assertion_types: set[str]) -> list[tuple[str, str]]:
    conflicts = sorted((left, right) for left in contract_types for right in assertion_types if (left, right) in CONFLICTS)
    return conflicts[:5]


def _fixture_suspect(text: str, test_paths: list[str]) -> bool:
    lowered = text.lower()
    return bool(test_paths) and any(term in lowered for term in FIXTURE_TERMS)


def _recommended_action(status: str, classification: str) -> str:
    if status == STATUS_TEST_EXPECTATION_SUSPECT:
        return "repair_or_regenerate_test_before_code_fix"
    if classification == CLASSIFICATION_TEST_FIXTURE_SUSPECT:
        return "inspect_fixture_or_integration_contract_before_code_fix"
    if status == STATUS_TEST_CONTRACT_AMBIGUOUS:
        return "request_product_contract_arbitration_before_retry_patch"
    if status == STATUS_VALID_TEST_FAILURE:
        return "repair_code_under_test_with_guarded_retry"
    return "collect_more_test_contract_evidence"


def _contains_word_or_phrase(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


def _normalize_path(path: str) -> str:
    value = path.strip().strip('"').replace("\\", "/")
    try:
        return str(Path(value)) if value else ""
    except OSError:
        return value


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


def dumps_for_prompt(payload: dict[str, Any]) -> str:
    """Render compact JSON for agent prompt embedding."""

    return json.dumps(payload, indent=2, sort_keys=True)
