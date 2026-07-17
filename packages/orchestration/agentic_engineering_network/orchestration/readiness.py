from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    title: str
    description: str
    required: bool = True
    status: str = "planned"


@dataclass(frozen=True)
class ReadinessSection:
    id: str
    title: str
    items: list[ReadinessItem]


def get_saas_readiness_checklist() -> list[dict[str, object]]:
    sections = [
        ReadinessSection(
            "product_market",
            "Product-Market Validation",
            [
                ReadinessItem("persona", "Primary persona defined", "Document buyer, user, pains, and switching trigger."),
                ReadinessItem("problem", "Pain is specific and urgent", "Capture the expensive workflow the product improves."),
                ReadinessItem("differentiation", "Differentiation statement", "Explain why this wins against spreadsheets and incumbents."),
                ReadinessItem("pilot", "Pilot success criteria", "Define measurable success for the first five customers."),
            ],
        ),
        ReadinessSection(
            "pricing",
            "Pricing",
            [
                ReadinessItem("packaging", "Plan packaging", "Define free/trial, team, business, and enterprise boundaries."),
                ReadinessItem("metering", "Usage metering", "Identify seats, usage units, limits, and overage behavior."),
                ReadinessItem("tax", "Tax and invoice policy", "Document tax/VAT ownership and invoice lifecycle."),
            ],
        ),
        ReadinessSection(
            "onboarding",
            "Onboarding",
            [
                ReadinessItem("signup", "Guided signup", "Collect tenant, owner, and first use-case data."),
                ReadinessItem("activation", "Activation checklist", "Track the aha moment and first completed workflow."),
                ReadinessItem("import", "Data import path", "Provide CSV/API import for core records."),
            ],
        ),
        ReadinessSection(
            "billing",
            "Billing",
            [
                ReadinessItem("stripe", "Stripe configured", "Set Stripe keys, price ids, checkout, portal, and webhooks."),
                ReadinessItem("subscription_state", "Subscription state machine", "Persist trialing, active, past_due, canceled, and grace periods."),
                ReadinessItem("entitlements", "Entitlement enforcement", "Gate features by plan and usage."),
            ],
        ),
        ReadinessSection(
            "observability",
            "Observability",
            [
                ReadinessItem("logs", "Structured logs", "Emit JSON logs with tenant, actor, request id, and event type."),
                ReadinessItem("metrics", "Operational metrics", "Track latency, errors, queue depth, billing events, and active tenants."),
                ReadinessItem("errors", "Error tracking", "Connect Sentry, OpenTelemetry, or another error backend."),
            ],
        ),
        ReadinessSection(
            "support_admin",
            "Support/Admin",
            [
                ReadinessItem("admin", "Admin console", "Provide tenant lookup, user impersonation controls, and audit trail."),
                ReadinessItem("support", "Support workflows", "Document escalation, incident, refund, and account recovery paths."),
                ReadinessItem("status", "Status page", "Publish uptime, incidents, and maintenance windows."),
            ],
        ),
        ReadinessSection(
            "deployment",
            "Deployment",
            [
                ReadinessItem("ci", "CI pipeline", "Run lint, tests, docker build, and security scan on every PR."),
                ReadinessItem("secrets", "Secrets configured", "Store secrets in GitHub/cloud secret managers, never source."),
                ReadinessItem("rollback", "Rollback plan", "Define database backup, migration rollback, and release rollback steps."),
            ],
        ),
    ]
    return [asdict(section) for section in sections]

