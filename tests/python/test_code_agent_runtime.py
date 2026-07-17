from pathlib import Path

from agentic_network.code_agent.runtime import (
    CODE_OUTPUT_FILE,
    clean_code_agent_response,
    parse_code_agent_sections,
    run_code_agent,
    validate_code_agent_response,
)

ARCHITECTURE_WITH_FILES = """TECHNICAL SUMMARY
- Add rate limiting around password reset requests.

FILES TO INSPECT
- apps/api/app/api/routes.py
- apps/api/app/core/settings.py

HANDOFF TO CODE AGENT
- Implement the scoped route and tests.

CONFIDENCE
High"""


VALID_CODE_PLAN = """FILES TO MODIFY
- apps/api/app/api/routes.py
- apps/api/app/core/settings.py

NEW FILES
- Candidate: tests for password reset rate-limit behavior.

CODE CHANGES
- Add configurable rate limit policy for password reset requests.
- Track reset attempts by user or request identity.
- Block excessive requests with user-facing feedback.

TESTS TO ADD
- Verify limits are enforced for repeated requests.
- Verify legitimate reset requests still work.
- Verify limits reset after the configured window expires.

RATIONALE
- Prevent password reset abuse while preserving usability.
- Align implementation with Product and Architect artifacts.

CONFIDENCE
High"""


def _fake_code_response(*, prompt: str) -> str:
    assert "PRODUCT AGENT REQUIREMENTS" in prompt
    assert "ARCHITECT AGENT PLAN" in prompt
    return VALID_CODE_PLAN


def test_parse_and_validate_code_sections() -> None:
    parsed = parse_code_agent_sections(VALID_CODE_PLAN)
    warnings, errors = validate_code_agent_response(
        generated_code_plan=VALID_CODE_PLAN,
        parsed_sections=parsed,
        architecture_plan=ARCHITECTURE_WITH_FILES,
    )

    assert parsed["confidence"] == "High"
    assert parsed["files_to_modify"] == [
        "apps/api/app/api/routes.py",
        "apps/api/app/core/settings.py",
    ]
    assert warnings == []
    assert errors == []


def test_validation_rejects_missing_sections_and_code_fences() -> None:
    invalid = VALID_CODE_PLAN.replace(
        "NEW FILES\n- Candidate: tests for password reset rate-limit behavior.\n\n",
        "",
    )
    invalid = invalid + "\n```python\nprint('no direct code')\n```"
    parsed = parse_code_agent_sections(invalid)

    _warnings, errors = validate_code_agent_response(
        generated_code_plan=invalid,
        parsed_sections=parsed,
        architecture_plan=ARCHITECTURE_WITH_FILES,
    )

    assert "missing_section_new_files" in errors
    assert "code_fence_present" in errors


def test_run_code_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / CODE_OUTPUT_FILE

    result = run_code_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements=(
            "REQUIREMENTS\n"
            "- Password reset requests must be rate limited.\n\n"
            "ACCEPTANCE CRITERIA\n"
            "- Repeated requests are blocked."
        ),
        architecture_plan=ARCHITECTURE_WITH_FILES,
        output_artifact_path=output_path,
        response_generator=_fake_code_response,
    )

    assert result.validation_errors == []
    assert result.output_artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_CODE_PLAN


def test_validation_rejects_code_syntax_even_when_fences_are_cleaned() -> None:
    raw_response = """FILES TO MODIFY
- Candidate: password reset request handling module.

NEW FILES
- None

CODE CHANGES
```python
import os
@decorator
def add_limit():
    return True
```

TESTS TO ADD
- Verify repeated requests are blocked.

RATIONALE
- Prevent abuse.

CONFIDENCE
High"""
    cleaned = clean_code_agent_response(raw_response)
    parsed = parse_code_agent_sections(cleaned)

    _warnings, errors = validate_code_agent_response(
        generated_code_plan=cleaned,
        parsed_sections=parsed,
        architecture_plan=ARCHITECTURE_WITH_FILES,
        raw_response=raw_response,
    )

    assert "code_fence_present" in errors
    assert "forbidden_code_import" in errors
    assert "forbidden_code_decorator" in errors
    assert "forbidden_code_def" in errors
    assert "forbidden_code_return" in errors


def test_cleaner_normalizes_numbered_lists_and_confidence() -> None:
    raw_response = """FILES TO MODIFY
1. Candidate: password reset request handling module.
2. Candidate: rate-limit policy module.

NEW FILES
1. None

CODE CHANGES
1. Add request tracking for repeated password reset attempts.
2. Apply the policy before sending reset instructions.

TESTS TO ADD
1. Verify excessive reset attempts are blocked.

RATIONALE
1. Prevent abuse while preserving usability.

CONFIDENCE
- Medium"""

    cleaned = clean_code_agent_response(raw_response)
    parsed = parse_code_agent_sections(cleaned)

    assert "1." not in cleaned
    assert "- Candidate: password reset request handling module." in cleaned
    assert cleaned.endswith("CONFIDENCE\nHigh")
    assert parsed["confidence"] == "High"


def test_validation_requires_candidate_prefix_for_unlisted_paths() -> None:
    invented_path_plan = """FILES TO MODIFY
- src/auth/password_reset.py

NEW FILES
- None

CODE CHANGES
- Add request tracking for repeated password reset attempts.

TESTS TO ADD
- Verify excessive reset attempts are blocked.

RATIONALE
- Prevent abuse while preserving usability.

CONFIDENCE
High"""
    parsed = parse_code_agent_sections(invented_path_plan)

    _warnings, errors = validate_code_agent_response(
        generated_code_plan=invented_path_plan,
        parsed_sections=parsed,
        architecture_plan=ARCHITECTURE_WITH_FILES,
    )

    assert "invented_file_path_src/auth/password_reset.py" in errors

    candidate_plan = invented_path_plan.replace(
        "- src/auth/password_reset.py",
        "- Candidate: src/auth/password_reset.py",
    )
    parsed_candidate = parse_code_agent_sections(candidate_plan)

    _candidate_warnings, candidate_errors = validate_code_agent_response(
        generated_code_plan=candidate_plan,
        parsed_sections=parsed_candidate,
        architecture_plan=ARCHITECTURE_WITH_FILES,
    )

    assert candidate_errors == []
