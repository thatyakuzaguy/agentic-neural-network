from agentic_network.agents.final_reviewer_agent import FinalReviewerAgent
from agentic_network.agents.reviewer_agent import ReviewerAgent
from agentic_network.agents.test_engineer_agent import TestEngineerAgent as _TestEngineerAgent
from agentic_network.models.base import BaseModelClient
from agentic_network.pipeline.runner import build_context


class _ApprovingModel(BaseModelClient):
    def generate_text(self, prompt: str) -> str:
        return (
            "STATUS: APPROVED\n"
            "BLOCKING ISSUES:\n"
            "- None.\n"
            "NON-BLOCKING ISSUES:\n"
            "- None.\n"
            "MISSING TESTS:\n"
            "- None.\n"
            "REQUIRED FIX PLAN:\n"
            "- No fix required."
        )

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        return self.generate_text(messages[-1]["content"])


def test_reviewer_rejects_missing_import_static_findings() -> None:
    context = (
        "STATIC SANITY CHECK FINDINGS\n"
        "- datetime.fromisoformat(...) is used without importing the datetime class."
    )

    output = ReviewerAgent(_ApprovingModel()).run(context)

    assert output.startswith("STATUS: CHANGES REQUIRED")
    assert "Static sanity checker" in output


def test_reviewer_rejects_naive_utc_timestamp_static_findings() -> None:
    context = (
        "STATIC SANITY CHECK FINDINGS\n"
        "- UTC timestamp requirement is implemented with naive utcnow().isoformat()."
    )

    output = ReviewerAgent(_ApprovingModel()).run(context)

    assert output.startswith("STATUS: CHANGES REQUIRED")
    assert "Static sanity checker" in output


def test_final_reviewer_rejects_post_fix_static_findings() -> None:
    context = build_context(
        {
            "user": "Return an ISO 8601 UTC timestamp with a Z suffix",
            "code": "timestamp = datetime.utcnow().isoformat()",
            "test": 'assert response.json()["timestamp"].endswith("Z")',
            "reviewer": "STATUS: CHANGES REQUIRED\n- Replace naive UTC timestamp.",
            "fixer": (
                "FIXED IMPLEMENTATION\n"
                "timestamp = datetime.utcnow().isoformat()\n"
                "CHANGE SUMMARY\n"
                "- Fixed the UTC timestamp issue."
            ),
            "post_fix_static_sanity": (
                "STATIC SANITY CHECK FINDINGS\n"
                "- BLOCKING: Naive UTC timestamp detected."
            ),
        }
    )

    output = FinalReviewerAgent(_ApprovingModel()).run(context)

    assert output.startswith("STATUS: CHANGES REQUIRED")
    assert "Post-fix static sanity checker" in output


def test_test_engineer_prompt_forbids_invented_coverage() -> None:
    prompt = _TestEngineerAgent(_ApprovingModel()).format_prompt(
        "Create tests for UTC timestamp output."
    )

    assert "Never claim coverage values unless coverage was measured" in prompt
    assert "Never claim pytest results unless pytest was actually executed" in prompt
    assert "must not invent percentages" in prompt
