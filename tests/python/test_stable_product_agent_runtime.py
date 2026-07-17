from pathlib import Path

from agentic_network.product_agent.runtime import (
    PRODUCT_AGENT_CONFIG_PATH,
    _local_path,
    parse_product_agent_sections,
    run_product_agent,
    validate_product_agent_response,
)


VALID_RESPONSE = """REQUIREMENTS
- Add rate limits to password reset requests.

AMBIGUITIES
- The allowed request volume is not specified.

ASSUMPTIONS
- Existing password reset behavior remains unchanged.

ACCEPTANCE CRITERIA
- Excessive password reset requests are limited.

RISKS
- Overly strict limits could block legitimate users.

CONFIDENCE
High"""


def test_parse_product_agent_sections() -> None:
    sections = parse_product_agent_sections(VALID_RESPONSE)

    assert sections["requirements"] == ["Add rate limits to password reset requests."]
    assert sections["ambiguities"] == ["The allowed request volume is not specified."]
    assert sections["assumptions"] == ["Existing password reset behavior remains unchanged."]
    assert sections["acceptance_criteria"] == ["Excessive password reset requests are limited."]
    assert sections["risks"] == ["Overly strict limits could block legitimate users."]
    assert sections["confidence"] == "High"


def test_validate_product_agent_response_accepts_stable_format() -> None:
    warnings = validate_product_agent_response(
        instruction="Add rate limits to password reset requests.",
        cleaned_response=VALID_RESPONSE,
        parsed_sections=parse_product_agent_sections(VALID_RESPONSE),
    )

    assert warnings == []


def test_validate_product_agent_response_flags_contract_violations() -> None:
    response = """# REQUIREMENTS
- Create an API endpoint with tenant admins.

CONFIDENCE
Medium
```python
print("bad")
```"""

    warnings = validate_product_agent_response(
        instruction="Support pagination for product search.",
        cleaned_response=response,
        parsed_sections=parse_product_agent_sections(response),
    )

    assert "missing_section_requirements" in warnings
    assert "missing_section_ambiguities" in warnings
    assert "confidence_not_high" in warnings
    assert "markdown_headings_present" in warnings
    assert "code_fence_present" in warnings
    assert "forbidden_term_api" in warnings
    assert "forbidden_term_endpoint" in warnings
    assert "forbidden_term_tenant" in warnings
    assert "forbidden_term_admin" in warnings


def test_run_product_agent_returns_structured_result_without_loading_model() -> None:
    def fake_generator(*, instruction: str, config_path: Path, max_new_tokens: int) -> str:
        assert instruction == "Add rate limits to password reset requests."
        assert config_path == _local_path(PRODUCT_AGENT_CONFIG_PATH)
        assert max_new_tokens == 512
        return VALID_RESPONSE

    result = run_product_agent(
        "Add rate limits to password reset requests.",
        response_generator=fake_generator,
    )

    assert result.raw_instruction == "Add rate limits to password reset requests."
    assert "REQUIREMENTS" in result.cleaned_response
    assert "CONFIDENCE\nHigh" in result.cleaned_response
    assert result.parsed_sections["confidence"] == "High"
    assert result.quality_warnings == []
    assert result.config_path == str(_local_path(PRODUCT_AGENT_CONFIG_PATH))
    assert result.adapter_path.endswith("qwen3-8b-product-agent-v9-repaired-v2-bullets")
