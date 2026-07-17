from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValidationTask:
    id: str
    title: str
    status: str
    evidence_required: list[str]
    owner: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_market_validation_workflow(idea: str) -> dict[str, object]:
    normalized = idea.strip() or "the proposed product"
    tasks = [
        ValidationTask("interview_10_customers", "Interview 10 target customers", "evidence required", ["interview notes", "pain ranking", "current workaround"], "Product owner"),
        ValidationTask("willingness_to_pay", "Validate willingness to pay", "evidence required", ["pricing reactions", "budget range", "purchase trigger"], "Product owner"),
        ValidationTask("landing_page_conversion", "Test landing page conversion", "evidence required", ["traffic source", "visitor count", "conversion rate"], "Growth owner"),
        ValidationTask("competitor_research", "Complete competitor research", "evidence required", ["direct alternatives", "pricing comparison", "positioning map"], "Product strategist"),
        ValidationTask("pilot_feedback", "Run pilot with users", "evidence required", ["pilot users", "activation metric", "retention notes"], "Release owner"),
    ]
    return {
        "idea": normalized,
        "product_approval_status": "evidence required",
        "customer_discovery_workflow": [
            "Define ICP hypothesis.",
            "Recruit at least 10 target customers.",
            "Run structured interviews.",
            "Synthesize pains, alternatives, urgency, budget, and decision process.",
            "Attach evidence before product gate approval.",
        ],
        "interview_script": [
            "What problem are you trying to solve today?",
            "How often does this problem happen?",
            "What tools or workarounds do you use now?",
            "What happens if the problem is not solved?",
            "Who owns budget for this workflow?",
            "What would make a solution unacceptable?",
            "Would you pay for this, and from which budget?",
        ],
        "survey_generator": [
            "Rate problem frequency from 1-5.",
            "Rate pain severity from 1-5.",
            "Which current tool do you use?",
            "What is your expected monthly budget?",
            "Would you join a pilot?",
        ],
        "landing_page_experiment_checklist": [
            "One clear value proposition.",
            "ICP-specific headline.",
            "Pricing or waitlist call-to-action.",
            "Analytics event tracking.",
            "Minimum sample size and conversion threshold.",
        ],
        "competitor_research_template": [
            "Competitor name",
            "Target segment",
            "Pricing",
            "Core workflow",
            "Differentiator",
            "Weakness",
        ],
        "pricing_validation_workflow": [
            "Estimate value metric.",
            "Test three price points.",
            "Ask budget owner, not only end user.",
            "Record objections and procurement constraints.",
        ],
        "icp_validation_workflow": [
            "Segment by industry, size, geography, urgency, and existing tools.",
            "Reject segments with no budget owner or low urgency.",
            "Promote segments with repeated high-severity pain and short buying path.",
        ],
        "tasks": [task.to_dict() for task in tasks],
    }
