from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RequirementRefinement:
    assumptions: list[str]
    clarifying_questions: list[str]
    domain_model: list[str]
    user_stories: list[str]
    acceptance_criteria: list[str]
    edge_cases: list[str]
    api_contracts: list[str]
    test_cases: list[str]
    improvement_workflow: list[str]


def refine_idea(idea: str) -> dict[str, object]:
    lower = idea.lower()
    questions: list[str] = []
    if not any(keyword in lower for keyword in ["crm", "ecommerce", "booking", "lms", "marketplace", "dashboard", "chatbot"]):
        questions.append("Which SaaS category best matches the product?")
    if "billing" not in lower and "stripe" not in lower:
        questions.append("Will the product need subscriptions, usage billing, one-time payments, or no billing?")
    if "tenant" not in lower and "b2b" not in lower:
        questions.append("Is this single-tenant, multi-tenant B2B, or consumer-focused?")
    return asdict(
        RequirementRefinement(
            assumptions=[
                "Use secure defaults and mock external providers until real credentials are configured.",
                "Generate a working MVP plus production-readiness backlog, not a legal/compliance guarantee.",
                "Ask clarifying questions only when category, billing, tenancy, or primary persona is ambiguous.",
            ],
            clarifying_questions=questions,
            domain_model=["tenant", "user", "membership", "role", "subscription", "audit_event", "integration_connection", "workflow_definition"],
            user_stories=[
                "As an owner, I can configure billing and invite users.",
                "As an admin, I can manage tenant settings and integrations.",
                "As a contributor, I can perform core workflow actions within my permissions.",
                "As a support operator, I can inspect audit and health status without accessing secrets.",
            ],
            acceptance_criteria=[
                "All tenant-scoped queries require tenant context.",
                "All privileged actions require explicit RBAC permission.",
                "The app boots with mock providers and switches to real providers through environment variables.",
                "CI runs lint, tests, docker build, and security scans.",
            ],
            edge_cases=[
                "Expired subscription with grace period.",
                "Webhook replay or invalid signature.",
                "User belongs to multiple tenants.",
                "Integration provider outage.",
                "Migration failure during deployment.",
            ],
            api_contracts=[
                "GET /health",
                "GET /readiness",
                "GET /integrations/status",
                "POST /billing/checkout-session",
                "POST /workflows/evaluate",
            ],
            test_cases=[
                "tenant isolation tests",
                "RBAC forbidden/allowed matrix",
                "Stripe mock checkout",
                "webhook signature validation",
                "workflow rule evaluation",
                "CI docker compose build",
            ],
            improvement_workflow=[
                "Generate MVP",
                "Run lifecycle checks",
                "Summarize failures",
                "Apply validated diff repairs",
                "Escalate to human after configured max attempts",
                "Repeat with refined requirements",
            ],
        )
    )

