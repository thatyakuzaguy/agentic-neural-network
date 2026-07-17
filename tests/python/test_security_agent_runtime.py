from pathlib import Path

from agentic_network.security_agent.runtime import (
    SECURITY_OUTPUT_FILE,
    clean_security_agent_response,
    parse_security_agent_sections,
    run_security_agent,
    validate_security_agent_response,
)


VALID_SECURITY_REVIEW = """SECURITY FINDINGS
- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.
- Reset-attempt tracking should not expose sensitive account existence information.
- User-facing feedback should avoid confirming whether an account exists.

THREATS
- Automated reset abuse may overwhelm users or email systems.
- Attackers may use reset behavior to enumerate valid accounts.
- Weak tracking may allow repeated attempts from rotating identifiers.

ABUSE SCENARIOS
- An attacker repeatedly triggers reset messages for a target user.
- An attacker probes reset feedback to infer account validity.
- A malicious actor attempts to bypass limits by changing identifiers.

SECURITY TESTS
- Verify excessive reset attempts are limited without revealing account existence.
- Verify feedback remains generic when limits are reached.
- Verify reset attempts are tracked consistently across repeated requests.
- Verify legitimate users can recover after the allowed waiting conditions.

MITIGATIONS
- Use generic feedback for reset requests and limit events.
- Track repeated reset attempts using privacy-preserving identifiers.
- Apply consistent limits across supported reset channels.
- Log abuse indicators for monitoring without exposing sensitive data.

RESIDUAL RISKS
- Highly distributed abuse may still bypass simple limits.
- Strict controls may impact legitimate users during account recovery.
- Poor telemetry handling may introduce privacy concerns.

CONFIDENCE
High"""


def _fake_security_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    assert "CODE AGENT PLAN" in prompt
    assert "TEST ENGINEER PLAN" in prompt
    return VALID_SECURITY_REVIEW


def test_parse_and_validate_security_sections() -> None:
    parsed = parse_security_agent_sections(VALID_SECURITY_REVIEW)
    warnings, errors = validate_security_agent_response(
        generated_security_review=VALID_SECURITY_REVIEW,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["security_findings"][0].startswith("Password reset")
    assert warnings == []
    assert errors == []


def test_validation_rejects_code_fences_after_cleaning() -> None:
    raw_response = VALID_SECURITY_REVIEW.replace(
        "SECURITY TESTS\n- Verify excessive reset attempts are limited without revealing account existence.",
        "SECURITY TESTS\n```text\npayload example\n```\n- Verify excessive reset attempts are limited without revealing account existence.",
    )
    cleaned = clean_security_agent_response(raw_response)
    parsed = parse_security_agent_sections(cleaned)

    _warnings, errors = validate_security_agent_response(
        generated_security_review=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "```" not in cleaned
    assert "code_fence_present" in errors


def test_validation_rejects_exploit_payloads() -> None:
    raw_response = VALID_SECURITY_REVIEW.replace(
        "- An attacker probes reset feedback to infer account validity.",
        "- An attacker probes reset feedback to infer account validity.\n"
        "- Use UNION SELECT to dump account data.",
    )
    cleaned = clean_security_agent_response(raw_response)
    parsed = parse_security_agent_sections(cleaned)

    _warnings, errors = validate_security_agent_response(
        generated_security_review=cleaned,
        parsed_sections=parsed,
        raw_response=raw_response,
    )

    assert "exploit_payload_sql_union" in errors


def test_validation_rejects_invented_cve_ids() -> None:
    raw_response = VALID_SECURITY_REVIEW.replace(
        "- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.",
        "- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.\n"
        "- This is caused by CVE-2099-12345.",
    )
    parsed = parse_security_agent_sections(raw_response)

    _warnings, errors = validate_security_agent_response(
        generated_security_review=raw_response,
        parsed_sections=parsed,
    )

    assert "invented_cve_id_present" in errors


def test_cleaner_normalizes_numbered_lists_and_confidence() -> None:
    numbered = VALID_SECURITY_REVIEW.replace("- ", "1. ").replace(
        "CONFIDENCE\nHigh",
        "CONFIDENCE\n- Medium",
    )

    cleaned = clean_security_agent_response(numbered)
    parsed = parse_security_agent_sections(cleaned)

    assert "1." not in cleaned
    assert cleaned.endswith("CONFIDENCE\nHigh")
    assert parsed["confidence"] == "High"
    assert parsed["mitigations"]


def test_fallback_produces_valid_artifact_only_output(tmp_path: Path) -> None:
    output_path = tmp_path / SECURITY_OUTPUT_FILE
    calls = 0

    def invalid_response(*, prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "```python\nimport os\n\ndef exploit():\n    return 'CVE-2099-12345'\n```"

    result = run_security_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        output_artifact_path=output_path,
        response_generator=invalid_response,
    )

    assert calls == 2
    assert result.validation_errors == []
    assert result.fallback_used is True
    assert any(
        warning.startswith("model_output_replaced_after_validation_errors")
        for warning in result.warnings
    )
    assert output_path.read_text(encoding="utf-8").strip() == result.generated_security_review
    assert "CVE-" not in result.generated_security_review
    assert "```" not in result.generated_security_review


def test_run_security_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / SECURITY_OUTPUT_FILE

    result = run_security_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements="REQUIREMENTS\n- Password reset requests must be rate limited.",
        architecture_plan="TECHNICAL SUMMARY\n- Add rate limiting around password reset requests.",
        code_plan="CODE CHANGES\n- Add request tracking and a configurable limit.",
        test_plan="TEST SCENARIOS\n- Verify rate limits block repeated requests.",
        output_artifact_path=output_path,
        response_generator=_fake_security_response,
    )

    assert result.validation_errors == []
    assert result.fallback_used is False
    assert result.output_artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_SECURITY_REVIEW
