from pathlib import Path

from agentic_network.reviewer_agent.runtime import (
    REVIEW_OUTPUT_FILE,
    clean_reviewer_agent_response,
    parse_reviewer_agent_sections,
    run_reviewer_agent,
    validate_reviewer_agent_response,
)


VALID_REVIEW = """CONSISTENCY CHECK
- Product, architecture, code, tests, and security artifacts are aligned.
- The planned work remains scoped to password reset rate limiting.

REQUIREMENT GAPS
- No requirement gaps identified.

ARCHITECTURE GAPS
- No architecture gaps identified.

IMPLEMENTATION RISKS
- Rate-limit behavior may need careful integration with existing reset flows.

TEST COVERAGE GAPS
- Long-window retry behavior may need additional coverage.

SECURITY GAPS
- Distributed reset abuse may need later monitoring beyond simple limits.

RECOMMENDATIONS
- Proceed with implementation after confirming the target files.

APPROVAL STATUS
Approved

CONFIDENCE
High"""


def _fake_reviewer_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    assert "CODE AGENT PLAN" in prompt
    assert "TEST ENGINEER PLAN" in prompt
    assert "SECURITY AGENT REVIEW" in prompt
    return VALID_REVIEW


def test_parse_and_validate_reviewer_sections() -> None:
    parsed = parse_reviewer_agent_sections(VALID_REVIEW)
    warnings, errors = validate_reviewer_agent_response(
        review_output=VALID_REVIEW,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["approval_status"] == "Approved"
    assert parsed["consistency_check"][0].startswith("Product")
    assert warnings == []
    assert errors == []


def test_validation_rejects_code_fences_and_code_constructs() -> None:
    raw_response = VALID_REVIEW.replace(
        "- Proceed with implementation after confirming the target files.",
        "```python\n"
        "import os\n"
        "@decorator\n"
        "def build_limit():\n"
        "    return os.environ\n"
        "```\n"
        "- Proceed with implementation after confirming the target files.",
    )
    cleaned = clean_reviewer_agent_response(raw_response)
    parsed = parse_reviewer_agent_sections(cleaned)

    _warnings, errors = validate_reviewer_agent_response(
        review_output=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "```" not in cleaned
    assert "code_fence_present" in errors
    assert "forbidden_import_statement" in errors
    assert "forbidden_function_definition" in errors
    assert "forbidden_decorator" in errors
    assert "forbidden_return_statement" in errors


def test_cleaner_normalizes_numbered_lists_and_scalars() -> None:
    numbered = VALID_REVIEW.replace("- ", "1. ").replace(
        "APPROVAL STATUS\nApproved",
        "APPROVAL STATUS\nChanges Required",
    ).replace(
        "CONFIDENCE\nHigh",
        "CONFIDENCE\nMedium",
    )

    cleaned = clean_reviewer_agent_response(numbered)
    parsed = parse_reviewer_agent_sections(cleaned)

    assert "1." not in cleaned
    assert "* Product, architecture" in cleaned
    assert parsed["approval_status"] == "Needs Fixes"
    assert parsed["confidence"] == "High"


def test_validation_rejects_invalid_approval_status() -> None:
    invalid = VALID_REVIEW.replace("APPROVAL STATUS\nApproved", "APPROVAL STATUS\nMaybe")
    parsed = parse_reviewer_agent_sections(invalid)

    _warnings, errors = validate_reviewer_agent_response(
        review_output=invalid,
        parsed_sections=parsed,
    )

    assert "approval_status_invalid" in errors


def test_fallback_produces_valid_needs_fixes_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / REVIEW_OUTPUT_FILE
    calls = 0

    def invalid_response(*, prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "```python\nfrom app import reset\n\ndef fix():\n    return reset()\n```"

    result = run_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        output_artifact_path=output_path,
        response_generator=invalid_response,
    )

    assert calls == 2
    assert result.validation_errors == []
    assert result.fallback_used is True
    assert result.parsed_sections["approval_status"] == "Needs Fixes"
    assert any(
        warning.startswith("model_output_replaced_after_validation_errors")
        for warning in result.warnings
    )
    assert output_path.read_text(encoding="utf-8").strip() == result.review_output
    assert "```" not in result.review_output
    assert "def " not in result.review_output


def test_run_reviewer_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / REVIEW_OUTPUT_FILE

    result = run_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        output_artifact_path=output_path,
        response_generator=_fake_reviewer_response,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert result.artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_REVIEW



def test_think_tags_are_removed_before_validation(tmp_path: Path) -> None:
    output_path = tmp_path / REVIEW_OUTPUT_FILE

    def response_with_think(*, prompt: str) -> str:
        return "<think>hidden reasoning with def bad():\n    return None</think>\n" + VALID_REVIEW

    result = run_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        output_artifact_path=output_path,
        response_generator=response_with_think,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert "think_tags_removed" in result.warnings
    assert "<think" not in result.review_output.lower()
    assert result.review_output == VALID_REVIEW


def test_unclosed_think_tag_before_valid_reviewer_output_is_cleaned() -> None:
    raw = "<think>hidden reasoning\nthis should be removed\n" + VALID_REVIEW

    cleaned = clean_reviewer_agent_response(raw)
    parsed = parse_reviewer_agent_sections(cleaned)
    warnings, errors = validate_reviewer_agent_response(
        review_output=cleaned,
        parsed_sections=parsed,
        raw_response=cleaned,
    )

    assert "<think" not in cleaned.lower()
    assert cleaned == VALID_REVIEW
    assert errors == []
    assert warnings == []
