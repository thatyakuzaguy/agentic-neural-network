from agentic_network.contract_arbitration.runtime import (
    OWNER_HUMAN_REVIEW_REQUIRED,
    OWNER_PRODUCT_AGENT_REQUIREMENTS,
    OWNER_USER_REQUEST,
    STATUS_CONTRACT_AMBIGUOUS,
    STATUS_CONTRACT_MISSING,
    STATUS_CONTRACT_RESOLVED,
    evaluate_contract_arbitration,
)


def test_user_request_is_top_contract_owner() -> None:
    result = evaluate_contract_arbitration(
        user_request="Return a decimal float total.",
        product_requirements="Return an integer total.",
        assertion_evidence=["AssertionError: expected int got float"],
    )

    assert result["status"] == STATUS_CONTRACT_RESOLVED
    assert result["owner"] == OWNER_USER_REQUEST
    assert result["policy"]["user_request_overrides_generated_artifacts"] is True


def test_product_requirements_override_test_plan() -> None:
    result = evaluate_contract_arbitration(
        product_requirements="Billing totals must be float values.",
        test_plan="Expect integer totals.",
        assertion_evidence=["AssertionError: expected int got float"],
    )

    assert result["status"] == STATUS_CONTRACT_RESOLVED
    assert result["owner"] == OWNER_PRODUCT_AGENT_REQUIREMENTS
    assert "lower_authority_contract_conflict_detected" in result["warnings"]


def test_ambiguous_contract_requires_human_review() -> None:
    result = evaluate_contract_arbitration(
        product_requirements="Return a valid total.",
        assertion_evidence=["AssertionError: expected int got float"],
    )

    assert result["status"] == STATUS_CONTRACT_AMBIGUOUS
    assert result["owner"] == OWNER_HUMAN_REVIEW_REQUIRED
    assert result["policy"]["ambiguous_contract_requires_product_or_human_arbitration"] is True


def test_missing_contract_requires_collection_before_fixing() -> None:
    result = evaluate_contract_arbitration(assertion_evidence=["AssertionError"])

    assert result["status"] == STATUS_CONTRACT_MISSING
    assert result["recommended_next_action"] == "collect_product_contract_before_fixing_code_or_tests"
