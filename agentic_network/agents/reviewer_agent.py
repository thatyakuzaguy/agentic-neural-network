from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output


def _has_blocking_static_findings(input_text: str) -> bool:
    marker = "STATIC SANITY CHECK FINDINGS"
    if marker not in input_text:
        return False
    findings = input_text.split(marker, 1)[1]
    return "- No findings." not in findings


class ReviewerAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Reviewer Agent", model, load_prompt("reviewer"), clean_deepseek_output)

    def run(self, input_text: str) -> str:
        output = super().run(input_text)
        upper_output = output.upper()
        approved = upper_output.startswith("STATUS: APPROVED") or (
            "APPROVAL STATUS" in upper_output and "APPROVED" in upper_output
        )
        if approved and _has_blocking_static_findings(input_text):
            return (
                "STATUS: CHANGES REQUIRED\n"
                "Static sanity checker reported blocking defects.\n\n"
                "CONSISTENCY CHECK\n"
                "* Static sanity checker reported blocking defects that must be fixed before approval.\n\n"
                "REQUIREMENT GAPS\n"
                "* Manual review required for each static sanity finding.\n\n"
                "ARCHITECTURE GAPS\n"
                "* Static sanity findings may indicate implementation drift from the plan.\n\n"
                "IMPLEMENTATION RISKS\n"
                "* Blocking static findings may cause runtime or integration defects.\n\n"
                "TEST COVERAGE GAPS\n"
                "* Add regression tests for each static sanity finding.\n\n"
                "SECURITY GAPS\n"
                "* Manual review required for any security-sensitive static finding.\n\n"
                "RECOMMENDATIONS\n"
                "* Fix every static sanity finding, then rerun tests and review.\n\n"
                "APPROVAL STATUS\n"
                "Needs Fixes\n\n"
                "CONFIDENCE\n"
                "High"
            )
        return output
