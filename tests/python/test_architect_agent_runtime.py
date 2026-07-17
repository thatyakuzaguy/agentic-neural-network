from pathlib import Path

from agentic_network.architect_agent.runtime import (
    ARCHITECT_OUTPUT_FILE,
    parse_architect_agent_sections,
    resolve_architect_mode,
    run_architect_agent,
    validate_architect_agent_response,
)


VALID_ARCHITECTURE = """TECHNICAL SUMMARY
- Add rate limiting around password reset requests.

AFFECTED AREAS
- Authentication request handling.

FILES TO INSPECT
- apps/api/app/api/routes.py
- tests/python/test_security.py

IMPLEMENTATION PLAN
- Inspect existing request handling and settings patterns.
- Add the smallest rate-limit check near the password reset entry point.
- Preserve Product Agent acceptance criteria in implementation notes.

DATA OR STATE CHANGES
- No schema migration identified until existing storage is inspected.

TEST STRATEGY
- Add tests for allowed requests and blocked repeated requests.

RISKS
- Rate limiting can accidentally block legitimate retries if thresholds are too strict.

HANDOFF TO CODE AGENT
- Inspect the listed files before editing.
- Implement only the minimal rate-limit path and matching tests.

CONFIDENCE
High"""


def _fake_architect_response(*, prompt: str, mode: str, model_path: Path) -> str:
    return VALID_ARCHITECTURE


def test_parse_and_validate_architect_sections() -> None:
    parsed = parse_architect_agent_sections(VALID_ARCHITECTURE)
    warnings, errors = validate_architect_agent_response(
        cleaned_response=VALID_ARCHITECTURE,
        parsed_sections=parsed,
    )

    assert parsed["confidence"] == "High"
    assert parsed["handoff_to_code_agent"] == [
        "Inspect the listed files before editing.",
        "Implement only the minimal rate-limit path and matching tests.",
    ]
    assert warnings == []
    assert errors == []


def test_validation_rejects_missing_handoff_bullet_and_code_fence() -> None:
    invalid = VALID_ARCHITECTURE.replace(
        "- Inspect the listed files before editing.\n"
        "- Implement only the minimal rate-limit path and matching tests.\n",
        "",
    ).replace("High", "Medium")
    invalid = invalid + "\n```python\nprint('nope')\n```"
    parsed = parse_architect_agent_sections(invalid)

    _warnings, errors = validate_architect_agent_response(
        cleaned_response=invalid,
        parsed_sections=parsed,
    )

    assert "handoff_to_code_agent_missing_bullet" in errors
    assert "confidence_not_high" in errors
    assert "code_fence_present" in errors


def test_auto_mode_uses_deep_for_risky_changes() -> None:
    assert (
        resolve_architect_mode(
            "auto",
            "Add rate limits to password reset requests.",
            "REQUIREMENTS\n- Protect authentication flows.",
        )
        == "deep"
    )
    assert (
        resolve_architect_mode(
            "auto",
            "Add a footer link.",
            "REQUIREMENTS\n- Show legal link in the footer.",
        )
        == "fast"
    )


def test_run_architect_agent_writes_valid_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / ARCHITECT_OUTPUT_FILE

    result = run_architect_agent(
        user_request="Add rate limits to password reset requests.",
        product_requirements=(
            "REQUIREMENTS\n"
            "- Password reset requests must be rate limited.\n\n"
            "ACCEPTANCE CRITERIA\n"
            "- Repeated requests are blocked."
        ),
        mode="fast",
        repo_root=tmp_path,
        fast_model_path=Path("/mnt/d/Models/qwen3"),
        output_artifact_path=output_path,
        response_generator=_fake_architect_response,
    )

    assert result.mode_used == "fast"
    assert result.model_path_used == "/mnt/d/Models/qwen3"
    assert result.validation_errors == []
    assert result.output_artifact_path == str(output_path)
    assert output_path.read_text(encoding="utf-8").strip() == VALID_ARCHITECTURE
