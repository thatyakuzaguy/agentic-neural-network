from pathlib import Path

from agentic_network.test_engineer.runtime import (
    TEST_OUTPUT_FILE,
    clean_test_engineer_response,
    parse_test_engineer_sections,
    run_test_engineer_agent,
    validate_test_engineer_response,
)


VALID_TEST_PLAN = """TEST SCENARIOS
- Verify password reset rate limits prevent repeated abuse.
- Verify legitimate users can still complete password reset after allowed waiting conditions.
- Verify user-facing feedback remains clear when limits are reached.

TEST CASES
- User reaches the configured reset limit and receives clear feedback.
- User remains below the limit and receives reset instructions normally.
- Repeated reset attempts are tracked consistently for the same account or identifier.
- Reset attempts after the allowed waiting window are accepted.

EDGE CASES
- Multiple reset attempts occur close together.
- A user retries after the limit window expires.
- Reset flow is interrupted and resumed.
- Reset attempts originate from repeated identifiers.

REGRESSION TESTS
- Existing successful password reset behavior remains unchanged.
- Existing expired reset-link behavior remains unchanged.
- Existing account recovery messaging remains consistent.

AUTOMATION STRATEGY
- Add behavior-level tests for allowed, blocked, and recovered reset flows.
- Add regression coverage around existing password reset success and failure paths.
- Keep tests deterministic by controlling rate-limit windows or test clocks.

RISKS
- Poorly designed tests may become flaky if time windows are not controlled.
- Missing negative-path tests may allow abuse behavior to regress.
- Overly strict assertions may block valid product changes.

CONFIDENCE
High"""


def _fake_test_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    assert "CODE AGENT PLAN" in prompt
    return VALID_TEST_PLAN


def test_parse_and_validate_test_engineer_sections() -> None:
    parsed = parse_test_engineer_sections(VALID_TEST_PLAN)
    warnings, errors = validate_test_engineer_response(
        generated_test_plan=VALID_TEST_PLAN,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["test_scenarios"][0].startswith("Verify password reset")
    assert warnings == []
    assert errors == []


def test_validation_rejects_code_fences_after_cleaning() -> None:
    raw_response = VALID_TEST_PLAN.replace(
        "TEST CASES\n- User reaches the configured reset limit and receives clear feedback.",
        "TEST CASES\n```python\nprint('no test code')\n```\n- User reaches the configured reset limit and receives clear feedback.",
    )
    cleaned = clean_test_engineer_response(raw_response)
    parsed = parse_test_engineer_sections(cleaned)

    _warnings, errors = validate_test_engineer_response(
        generated_test_plan=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "```" not in cleaned
    assert "code_fence_present" in errors


def test_validation_rejects_executable_test_code() -> None:
    raw_response = VALID_TEST_PLAN.replace(
        "- User remains below the limit and receives reset instructions normally.",
        "- User remains below the limit and receives reset instructions normally.\n"
        "import pytest\n"
        "@pytest.mark.unit\n"
        "def test_reset_limit():\n"
        "    assert True",
    )
    cleaned = clean_test_engineer_response(raw_response)
    parsed = parse_test_engineer_sections(cleaned)

    _warnings, errors = validate_test_engineer_response(
        generated_test_plan=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "forbidden_import_statement" in errors
    assert "forbidden_decorator" in errors
    assert "forbidden_test_function" in errors
    assert "forbidden_assert_statement" in errors


def test_cleaner_normalizes_numbered_lists_and_confidence() -> None:
    numbered = VALID_TEST_PLAN.replace("- ", "1. ").replace("CONFIDENCE\nHigh", "CONFIDENCE\n- Low")

    cleaned = clean_test_engineer_response(numbered)
    parsed = parse_test_engineer_sections(cleaned)

    assert "1." not in cleaned
    assert cleaned.endswith("CONFIDENCE\nHigh")
    assert parsed["confidence"] == "High"
    assert parsed["test_cases"]


def test_fallback_produces_valid_artifact_only_output(tmp_path: Path) -> None:
    output_path = tmp_path / TEST_OUTPUT_FILE
    calls = 0

    def invalid_response(*, prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "```python\nimport pytest\n\ndef test_bad():\n    assert True\n```"

    result = run_test_engineer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        output_artifact_path=output_path,
        response_generator=invalid_response,
    )

    assert calls == 2
    assert result.validation_errors == []
    assert any(
        warning.startswith("model_output_replaced_after_validation_errors")
        for warning in result.warnings
    )
    assert result.output_artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == result.generated_test_plan
    assert "def " not in result.generated_test_plan
    assert "```" not in result.generated_test_plan


def test_run_test_engineer_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / TEST_OUTPUT_FILE

    result = run_test_engineer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        output_artifact_path=output_path,
        response_generator=_fake_test_response,
    )

    assert result.validation_errors == []
    assert result.output_artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_TEST_PLAN
