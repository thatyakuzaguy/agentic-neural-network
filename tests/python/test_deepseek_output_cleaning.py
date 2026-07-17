from agentic_network.agents.final_reviewer_agent import FinalReviewerAgent
from agentic_network.agents.reviewer_agent import ReviewerAgent
from agentic_network.agents.security_agent import SecurityAgent
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output


class _LeakyThinkModel(BaseModelClient):
    def generate_text(self, prompt: str) -> str:
        return "<think>hidden reasoning</think>STATUS: APPROVED\nBLOCKING ISSUES:\n- None."

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        return self.generate_text(messages[-1]["content"])


def test_clean_deepseek_output_removes_think_block() -> None:
    output = clean_deepseek_output("<think>hidden reasoning</think>FINAL")

    assert output == "FINAL"


def test_clean_deepseek_output_keeps_after_last_think_and_dedupes_sections() -> None:
    duplicated = """REQUIREMENTS
- Build the feature.

RISKS
- Missing tests.

</think>

REQUIREMENTS
- Build the feature.

RISKS
- Missing tests.
"""

    output = clean_deepseek_output(duplicated)

    assert output == "REQUIREMENTS\n- Build the feature.\n\nRISKS\n- Missing tests."
    assert "</think>" not in output
    assert output.count("REQUIREMENTS") == 1


def test_clean_deepseek_output_preserves_markdown_code_blocks() -> None:
    markdown = """IMPLEMENTATION
```python
def parse_tag() -> str:
    return "</think>"
```

FILES
- app/main.py
"""

    output = clean_deepseek_output(markdown)

    assert 'return "</think>"' in output
    assert "```python" in output
    assert "FILES" in output


def test_clean_deepseek_output_leaves_plain_output_unchanged() -> None:
    markdown = """STATUS: APPROVED
BLOCKING ISSUES:
- None.
"""

    assert clean_deepseek_output(markdown) == markdown.strip()


def test_clean_deepseek_output_removes_duplicate_structured_answer_without_tags() -> None:
    duplicated = """REQUIREMENTS
- Build the feature.

RISKS
- Missing tests.

REQUIREMENTS
- Build the feature.

RISKS
- Missing tests.
"""

    output = clean_deepseek_output(duplicated)

    assert output.count("REQUIREMENTS") == 1
    assert output.count("RISKS") == 1


def test_security_agent_output_is_cleaned() -> None:
    output = SecurityAgent(_LeakyThinkModel()).run("context")

    assert "<think>" not in output
    assert "</think>" not in output
    assert output.startswith("STATUS: APPROVED")


def test_reviewer_agent_output_is_cleaned() -> None:
    output = ReviewerAgent(_LeakyThinkModel()).run("context")

    assert "<think>" not in output
    assert "</think>" not in output
    assert output.startswith("STATUS: APPROVED")


def test_final_reviewer_agent_output_is_cleaned() -> None:
    output = FinalReviewerAgent(_LeakyThinkModel()).run("context")

    assert "<think>" not in output
    assert "</think>" not in output
    assert output.startswith("STATUS: APPROVED")
