from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output


def _extract_context_section(input_text: str, title: str) -> str:
    marker = f"{title}\n{'=' * len(title)}\n"
    if marker not in input_text:
        return ""
    section = input_text.split(marker, 1)[1]
    for next_title in (
        "USER REQUEST",
        "PRODUCT REQUIREMENTS",
        "ARCHITECTURE",
        "CODE",
        "TESTS",
        "SECURITY REVIEW",
        "STATIC SANITY CHECK FINDINGS",
        "REVIEWER",
        "FIXES",
        "POST-FIX STATIC SANITY CHECK FINDINGS",
    ):
        next_marker = f"\n\n{next_title}\n{'=' * len(next_title)}\n"
        if next_marker in section:
            section = section.split(next_marker, 1)[0]
    return section.strip()


def _has_static_findings(section: str) -> bool:
    return bool(section) and "- No findings." not in section


def _fixer_ran_without_post_fix_findings(input_text: str) -> bool:
    fixes = _extract_context_section(input_text, "FIXES")
    return bool(fixes and "SKIPPED" not in fixes and "POST-FIX STATIC SANITY CHECK FINDINGS" not in input_text)


def _remaining_static_blocker(input_text: str) -> str | None:
    post_fix_findings = _extract_context_section(
        input_text, "POST-FIX STATIC SANITY CHECK FINDINGS"
    )
    if _has_static_findings(post_fix_findings):
        return "- Post-fix static sanity checker reported blocking defects."

    if _fixer_ran_without_post_fix_findings(input_text):
        return "- Fixer ran without post-fix static sanity findings."

    if not post_fix_findings:
        initial_findings = _extract_context_section(input_text, "STATIC SANITY CHECK FINDINGS")
        if _has_static_findings(initial_findings):
            return "- Static sanity checker reported blocking defects."

    return None


class FinalReviewerAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Final Reviewer Agent", model, load_prompt("final_reviewer"), clean_deepseek_output)

    def run(self, input_text: str) -> str:
        output = super().run(input_text)
        static_blocker = _remaining_static_blocker(input_text)
        upper_output = output.upper()
        approved = upper_output.startswith("STATUS: APPROVED") or (
            "FINAL DECISION" in upper_output and "APPROVED" in upper_output
        )
        if approved and static_blocker:
            return (
                "STATUS: CHANGES REQUIRED\n"
                "Post-fix static sanity checker reported blocking defects.\n\n"
                "FINAL ASSESSMENT\n"
                "* Final approval is blocked by unresolved static sanity findings.\n\n"
                "REQUIREMENTS STATUS\n"
                "* Manual review required before approval.\n\n"
                "ARCHITECTURE STATUS\n"
                "* Manual review required before approval.\n\n"
                "IMPLEMENTATION STATUS\n"
                f"{static_blocker}\n\n"
                "TEST STATUS\n"
                "* Manual review required before approval.\n\n"
                "SECURITY STATUS\n"
                "* Manual review required before approval.\n\n"
                "REVIEW STATUS\n"
                "* Reviewer findings cannot be considered closed while static sanity is blocking.\n\n"
                "FIX STATUS\n"
                "* Fix plan requires follow-up before final approval.\n\n"
                "FINAL DECISION\n"
                "Rejected\n\n"
                "REASONING\n"
                "* Final approval is blocked until static sanity findings are resolved.\n\n"
                "CONFIDENCE\n"
                "High"
            )
        return output
