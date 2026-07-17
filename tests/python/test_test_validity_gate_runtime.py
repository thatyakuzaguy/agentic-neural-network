from agentic_network.test_validity_gate.runtime import (
    CLASSIFICATION_CODE_UNDER_TEST_SUSPECT,
    CLASSIFICATION_TEST_EXPECTATION_SUSPECT,
    CLASSIFICATION_TEST_FIXTURE_SUSPECT,
    STATUS_TEST_CONTRACT_AMBIGUOUS,
    STATUS_TEST_EXPECTATION_SUSPECT,
    STATUS_VALID_TEST_FAILURE,
    evaluate_test_validity_gate,
)


def test_detects_bad_test_expectation_against_product_contract() -> None:
    result = evaluate_test_validity_gate(
        test_report="tests/test_price.py:12: AssertionError: expected int got float",
        product_requirements="Prices and tax totals must be represented as decimal float values.",
        test_plan="Verify checkout total keeps cents as a float.",
        targets=[{"path": "tests/test_price.py", "line": 12}],
    )

    assert result["status"] == STATUS_TEST_EXPECTATION_SUSPECT
    assert result["classification"] == CLASSIFICATION_TEST_EXPECTATION_SUSPECT
    assert result["contract_evidence"]["contract_authority"]["owner"] == "PRODUCT_AGENT_REQUIREMENTS"
    assert result["fix_policy"]["do_not_modify_code_under_test_until_test_contract_validated"] is True
    assert result["recommended_next_action"] == "repair_or_regenerate_test_before_code_fix"


def test_runtime_exception_keeps_code_under_test_as_suspect() -> None:
    result = evaluate_test_validity_gate(
        stderr='Traceback\n  File "app/service.py", line 8, in total\nNameError: name "RATE" is not defined',
        product_requirements="The service must calculate totals.",
        targets=[{"path": "app/service.py", "line": 8}],
    )

    assert result["status"] == STATUS_VALID_TEST_FAILURE
    assert result["classification"] == CLASSIFICATION_CODE_UNDER_TEST_SUSPECT
    assert result["fix_policy"]["do_not_modify_code_under_test_until_test_contract_validated"] is False


def test_fixture_or_integration_failure_is_not_treated_as_code_bug() -> None:
    result = evaluate_test_validity_gate(
        test_report="tests/integration/test_webhook.py:44: AssertionError: webhook mock signature invalid",
        product_requirements="Stripe webhook signatures must be verified.",
        targets=[{"path": "tests/integration/test_webhook.py", "line": 44}],
    )

    assert result["status"] == STATUS_TEST_CONTRACT_AMBIGUOUS
    assert result["classification"] == CLASSIFICATION_TEST_FIXTURE_SUSPECT
    assert result["recommended_next_action"] == "inspect_fixture_or_integration_contract_before_code_fix"


def test_missing_contract_keeps_assertion_ambiguous() -> None:
    result = evaluate_test_validity_gate(
        test_report="tests/test_api.py:5: AssertionError: expected 200 got 201",
        targets=[{"path": "tests/test_api.py", "line": 5}],
    )

    assert result["status"] == STATUS_TEST_CONTRACT_AMBIGUOUS
    assert "contract_text_missing" in result["warnings"]
    assert result["recommended_next_action"] == "request_product_contract_arbitration_before_retry_patch"


def test_original_spec_ambiguity_escalates_to_contract_arbitration() -> None:
    result = evaluate_test_validity_gate(
        test_report="tests/test_price.py:12: AssertionError: expected int got float",
        product_requirements="Return a valid price total.",
        test_plan="The generated test expects an integer total.",
        targets=[{"path": "tests/test_price.py", "line": 12}],
    )

    assert result["status"] == STATUS_TEST_CONTRACT_AMBIGUOUS
    assert result["classification"] != CLASSIFICATION_CODE_UNDER_TEST_SUSPECT
    assert result["contract_evidence"]["contract_authority"]["owner"] == "HUMAN_REVIEW_REQUIRED"
    assert result["fix_policy"]["require_human_or_reviewer_contract_check_when_ambiguous"] is True
