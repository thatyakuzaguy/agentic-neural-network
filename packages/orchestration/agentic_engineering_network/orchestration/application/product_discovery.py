from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.orchestration.domain.quality import (
    Finding,
    SeniorGateResult,
    gate_status,
    score_from_coverage,
)


PRODUCT_SIGNALS = {
    "category": ["crm", "ecommerce", "booking", "lms", "marketplace", "dashboard", "chatbot", "workflow"],
    "customer": ["b2b", "user", "customer", "buyer", "admin", "team", "tenant"],
    "monetization": ["billing", "stripe", "subscription", "pricing", "trial", "plan"],
    "differentiation": ["ai", "automation", "analytics", "premium", "faster", "secure", "compliance"],
}


@dataclass(frozen=True)
class ProductDiscovery:
    problem_statement: str
    icp: list[str]
    personas: list[str]
    value_proposition: str
    competitor_analysis_framework: list[str]
    pricing_model: list[str]
    mvp_scope: list[str]
    feature_prioritization_matrix: list[dict[str, object]]
    risk_matrix: list[dict[str, object]]
    go_to_market_checklist: list[str]
    gate: SeniorGateResult

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "gate": self.gate.to_dict()}


class ProductDiscoveryService:
    def discover(self, idea: str) -> ProductDiscovery:
        normalized = idea.strip() or "Untitled SaaS product"
        lower = normalized.lower()
        covered = {name for name, words in PRODUCT_SIGNALS.items() if any(word in lower for word in words)}
        score = score_from_coverage(list(PRODUCT_SIGNALS), covered)
        findings: list[Finding] = []
        required_fixes: list[str] = []
        if "category" not in covered:
            findings.append(
                Finding(
                    "high",
                    "product",
                    "The product category is ambiguous.",
                    "Specify the domain such as CRM, ecommerce, booking, LMS, marketplace, admin dashboard, or AI chatbot.",
                )
            )
            required_fixes.append("Define the product category and primary workflow.")
        if "customer" not in covered:
            findings.append(
                Finding(
                    "medium",
                    "product",
                    "The target customer/persona is underspecified.",
                    "Name the buyer, daily user, and admin persona.",
                )
            )
            required_fixes.append("Add ICP and persona details before final implementation.")
        if "monetization" not in covered:
            required_fixes.append("Choose a pricing model, trial policy, and billing scope.")

        gate = SeniorGateResult(
            "Product gate",
            gate_status(score, 0),
            score,
            findings,
            ["Weak positioning can produce a technically correct product that nobody wants."],
            required_fixes,
            ["Interview target users before committing to a roadmap.", "Add competitor evidence and willingness-to-pay notes."],
            ["A product lead should validate market assumptions before production launch."],
        )
        return ProductDiscovery(
            problem_statement=f"{normalized} should solve a measurable pain for a defined buyer and user group.",
            icp=["Company size, industry, budget owner, buying trigger, urgency, and current workaround."],
            personas=["Economic buyer", "Admin/operator", "Daily end user", "Support or compliance reviewer"],
            value_proposition="Deliver a faster, safer, measurable workflow outcome than spreadsheets or generic tools.",
            competitor_analysis_framework=[
                "Direct competitors",
                "Spreadsheet/manual workflow alternative",
                "Incumbent platform modules",
                "AI-native substitute",
                "Build-vs-buy comparison",
            ],
            pricing_model=["Free trial or demo workspace", "Core subscription tier", "Pro tier", "Enterprise/security tier"],
            mvp_scope=[
                "One primary workflow",
                "Authentication, tenant isolation, RBAC",
                "Billing-ready plan model",
                "Admin/support dashboard",
                "Audit and observability",
            ],
            feature_prioritization_matrix=[
                {"feature": "Primary workflow", "impact": "high", "effort": "medium", "priority": "P0"},
                {"feature": "Billing and entitlement", "impact": "high", "effort": "medium", "priority": "P0"},
                {"feature": "Advanced customization", "impact": "medium", "effort": "high", "priority": "P2"},
            ],
            risk_matrix=[
                {"risk": "Ambiguous ICP", "likelihood": "medium", "impact": "high", "mitigation": "Discovery interviews"},
                {"risk": "Underpriced usage", "likelihood": "medium", "impact": "medium", "mitigation": "Model usage economics"},
                {"risk": "Compliance claims", "likelihood": "low", "impact": "high", "mitigation": "Legal review"},
            ],
            go_to_market_checklist=[
                "Landing message tested with target segment",
                "Demo script",
                "Pricing page copy",
                "Onboarding activation event",
                "Support runbook",
                "Launch analytics",
            ],
            gate=gate,
        )
