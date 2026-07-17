from pathlib import Path

from agentic_network.fixer_agent.runtime import (
    FIX_OUTPUT_FILE,
    clean_fixer_agent_response,
    parse_fixer_agent_sections,
    run_fixer_agent,
    validate_fixer_agent_response,
)


VALID_FIX_PLAN = """FIX SUMMARY
- No significant fixes are required based on the current review.

REQUIREMENT FIXES
- No requirement changes are required.

ARCHITECTURE FIXES
- No architecture changes are required.

IMPLEMENTATION FIXES
- Continue with planned implementation.

TEST FIXES
- Maintain planned test coverage.

SECURITY FIXES
- Maintain planned security controls.

PRIORITY ORDER
- Proceed with implementation review.

READY FOR RE-REVIEW
Yes

CONFIDENCE
High"""


def _fake_fixer_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    assert "CODE AGENT PLAN" in prompt
    assert "TEST ENGINEER PLAN" in prompt
    assert "SECURITY AGENT REVIEW" in prompt
    assert "REVIEWER AGENT REPORT" in prompt
    return VALID_FIX_PLAN


def test_parse_and_validate_fixer_sections() -> None:
    parsed = parse_fixer_agent_sections(VALID_FIX_PLAN)
    warnings, errors = validate_fixer_agent_response(
        fix_plan_output=VALID_FIX_PLAN,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["ready_for_rereview"] == "Yes"
    assert parsed["fix_summary"][0].startswith("No significant")
    assert warnings == []
    assert errors == []


def test_validation_rejects_invalid_ready_status() -> None:
    invalid = VALID_FIX_PLAN.replace("READY FOR RE-REVIEW\nYes", "READY FOR RE-REVIEW\nMaybe")
    parsed = parse_fixer_agent_sections(invalid)

    _warnings, errors = validate_fixer_agent_response(
        fix_plan_output=invalid,
        parsed_sections=parsed,
    )

    assert "ready_for_rereview_invalid" in errors


def test_validation_rejects_code_fences_and_code_constructs() -> None:
    raw_response = VALID_FIX_PLAN.replace(
        "- Continue with planned implementation.",
        "```python\n"
        "import os\n"
        "class Patch:\n"
        "    pass\n"
        "def fix():\n"
        "    return os.environ\n"
        "```\n"
        "- Continue with planned implementation.",
    )
    cleaned = clean_fixer_agent_response(raw_response)
    parsed = parse_fixer_agent_sections(cleaned)

    _warnings, errors = validate_fixer_agent_response(
        fix_plan_output=cleaned,
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
    numbered = VALID_FIX_PLAN.replace("- ", "1. ").replace(
        "READY FOR RE-REVIEW\nYes",
        "READY FOR RE-REVIEW\nnot ready",
    ).replace(
        "CONFIDENCE\nHigh",
        "CONFIDENCE\nMedium",
    )

    cleaned = clean_fixer_agent_response(numbered)
    parsed = parse_fixer_agent_sections(cleaned)

    assert "1." not in cleaned
    assert "* No significant fixes" in cleaned
    assert parsed["ready_for_rereview"] == "No"
    assert parsed["confidence"] == "High"


def test_fallback_produces_valid_artifact_only_output(tmp_path: Path) -> None:
    output_path = tmp_path / FIX_OUTPUT_FILE
    calls = 0

    def invalid_response(*, prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "```python\nfrom app import reset\n\ndef fix():\n    return reset()\n```"

    result = run_fixer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nNeeds Fixes\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=invalid_response,
    )

    assert calls == 2
    assert result.validation_errors == []
    assert result.fallback_used is True
    assert result.parsed_sections["ready_for_rereview"] == "No"
    assert any(
        warning.startswith("model_output_replaced_after_validation_errors")
        for warning in result.warnings
    )
    assert output_path.read_text(encoding="utf-8").strip() == result.fix_plan_output
    assert "```" not in result.fix_plan_output
    assert "def " not in result.fix_plan_output


def test_run_fixer_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / FIX_OUTPUT_FILE

    result = run_fixer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=_fake_fixer_response,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert result.artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_FIX_PLAN



def test_think_tags_are_removed_before_validation(tmp_path: Path) -> None:
    output_path = tmp_path / FIX_OUTPUT_FILE

    def response_with_think(*, prompt: str) -> str:
        return "<think>hidden reasoning with class Bad: pass</think>\n" + VALID_FIX_PLAN

    result = run_fixer_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        security_review="SECURITY FINDINGS\n- Preserve generic reset feedback.",
        reviewer_report="APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
        output_artifact_path=output_path,
        response_generator=response_with_think,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert "think_tags_removed" in result.warnings
    assert "<think" not in result.fix_plan_output.lower()
    assert result.fix_plan_output == VALID_FIX_PLAN


def test_unclosed_think_tag_before_valid_fixer_output_is_cleaned() -> None:
    raw = "<think>hidden reasoning\nthis should be removed\n" + VALID_FIX_PLAN

    cleaned = clean_fixer_agent_response(raw)
    parsed = parse_fixer_agent_sections(cleaned)
    warnings, errors = validate_fixer_agent_response(
        fix_plan_output=cleaned,
        parsed_sections=parsed,
        raw_response=cleaned,
    )

    assert "<think" not in cleaned.lower()
    assert cleaned == VALID_FIX_PLAN
    assert errors == []
    assert warnings == []
