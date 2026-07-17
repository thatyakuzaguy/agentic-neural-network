from pathlib import Path

from agentic_network.final_reviewer.runtime import (
    FINAL_REVIEW_OUTPUT_FILE,
    clean_final_reviewer_response,
    parse_final_reviewer_sections,
    run_final_reviewer_agent,
    validate_final_reviewer_response,
)


VALID_FINAL_REVIEW = """FINAL ASSESSMENT
- The generated artifacts are internally consistent.

REQUIREMENTS STATUS
- Requirements are sufficiently covered.

ARCHITECTURE STATUS
- Architecture aligns with requirements.

IMPLEMENTATION STATUS
- Implementation plan aligns with architecture.

TEST STATUS
- Test coverage addresses major acceptance criteria.

SECURITY STATUS
- Security concerns have been reviewed.

REVIEW STATUS
- Reviewer findings have been addressed.

FIX STATUS
- No significant unresolved fixes remain.

FINAL DECISION
Approved

REASONING
- No blocking inconsistencies remain across the artifact chain.

CONFIDENCE
High"""


def _fake_final_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    assert "CODE AGENT PLAN" in prompt
    assert "TEST ENGINEER PLAN" in prompt
    assert "SECURITY AGENT REVIEW" in prompt
    assert "REVIEWER AGENT REPORT" in prompt
    assert "FIXER AGENT PLAN" in prompt
    return VALID_FINAL_REVIEW


def test_parse_and_validate_final_reviewer_sections() -> None:
    parsed = parse_final_reviewer_sections(VALID_FINAL_REVIEW)
    warnings, errors = validate_final_reviewer_response(
        final_review_output=VALID_FINAL_REVIEW,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["final_decision"] == "Approved"
    assert parsed["final_assessment"][0].startswith("The generated")
    assert warnings == []
    assert errors == []


def test_validation_rejects_invalid_final_decision() -> None:
    invalid = VALID_FINAL_REVIEW.replace("FINAL DECISION\nApproved", "FINAL DECISION\nMaybe")
    parsed = parse_final_reviewer_sections(invalid)

    _warnings, errors = validate_final_reviewer_response(
        final_review_output=invalid,
        parsed_sections=parsed,
    )

    assert "final_decision_invalid" in errors


def test_validation_rejects_code_fences_and_code_constructs() -> None:
    raw_response = VALID_FINAL_REVIEW.replace(
        "- Implementation plan aligns with architecture.",
        "```python\n"
        "from app import reset\n"
        "class Review:\n"
        "    pass\n"
        "def approve():\n"
        "    return reset()\n"
        "```\n"
        "- Implementation plan aligns with architecture.",
    )
    cleaned = clean_final_reviewer_response(raw_response)
    parsed = parse_final_reviewer_sections(cleaned)

    _warnings, errors = validate_final_reviewer_response(
        final_review_output=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "```" not in cleaned
    assert "code_fence_present" in errors
    assert "forbidden_import_statement" in errors
    assert "forbidden_function_definition" in errors
    assert "forbidden_class_definition" in errors
    assert "forbidden_return_statement" in errors


def test_cleaner_normalizes_numbered_lists_and_scalars() -> None:
    numbered = VALID_FINAL_REVIEW.replace("- ", "1. ").replace(
        "FINAL DECISION\nApproved",
        "FINAL DECISION\nchanges required",
    ).replace(
        "CONFIDENCE\nHigh",
        "CONFIDENCE\nMedium",
    )

    cleaned = clean_final_reviewer_response(numbered)
    parsed = parse_final_reviewer_sections(cleaned)

    assert "1." not in cleaned
    assert "* The generated artifacts" in cleaned
    assert parsed["final_decision"] == "Rejected"
    assert parsed["confidence"] == "High"


def test_fallback_produces_valid_rejected_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / FINAL_REVIEW_OUTPUT_FILE
    calls = 0

    def invalid_response(*, prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "```python\nimport os\n\ndef approve():\n    return os.environ\n```"

    result = run_final_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
        fix_plan="READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=invalid_response,
    )

    assert calls == 2
    assert result.validation_errors == []
    assert result.fallback_used is True
    assert result.parsed_sections["final_decision"] == "Rejected"
    assert any(
        warning.startswith("model_output_replaced_after_validation_errors")
        for warning in result.warnings
    )
    assert output_path.read_text(encoding="utf-8").strip() == result.final_review_output
    assert "```" not in result.final_review_output
    assert "def " not in result.final_review_output


def test_run_final_reviewer_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / FINAL_REVIEW_OUTPUT_FILE

    result = run_final_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
        fix_plan="READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=_fake_final_response,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert result.artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_FINAL_REVIEW



def test_think_tags_are_removed_before_validation(tmp_path: Path) -> None:
    output_path = tmp_path / FINAL_REVIEW_OUTPUT_FILE

    def response_with_think(*, prompt: str) -> str:
        return "<think>hidden reasoning with import os</think>\n" + VALID_FINAL_REVIEW

    result = run_final_reviewer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
        fix_plan="READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=response_with_think,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert "think_tags_removed" in result.warnings
    assert "<think" not in result.final_review_output.lower()
    assert result.final_review_output == VALID_FINAL_REVIEW


def test_unclosed_think_tag_before_valid_final_review_output_is_cleaned() -> None:
    raw = "<think>hidden reasoning\nthis should be removed\n" + VALID_FINAL_REVIEW

    cleaned = clean_final_reviewer_response(raw)
    parsed = parse_final_reviewer_sections(cleaned)
    warnings, errors = validate_final_reviewer_response(
        final_review_output=cleaned,
        parsed_sections=parsed,
        raw_response=cleaned,
    )

    assert "<think" not in cleaned.lower()
    assert cleaned == VALID_FINAL_REVIEW
    assert errors == []
    assert warnings == []
