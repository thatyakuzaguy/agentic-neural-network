from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SaasTemplate:
    id: str
    name: str
    description: str
    core_entities: list[str]
    workflows: list[str]
    integrations: list[str]


def get_saas_templates() -> list[dict[str, object]]:
    templates = [
        SaasTemplate("crm", "CRM SaaS", "Pipeline, accounts, contacts, activities, billing, and dashboards.", ["tenant", "account", "contact", "deal", "activity"], ["lead qualification", "deal escalation", "renewal reminder"], ["Stripe", "email", "calendar", "Slack"]),
        SaasTemplate("ecommerce", "Ecommerce SaaS", "Catalog, checkout, inventory, fulfillment, and customer support.", ["product", "order", "customer", "inventory", "refund"], ["abandoned cart", "low stock", "refund approval"], ["Stripe", "shipping", "email", "analytics"]),
        SaasTemplate("booking", "Booking SaaS", "Availability, reservations, staff, reminders, and payments.", ["resource", "booking", "customer", "staff", "payment"], ["availability sync", "reminder", "no-show followup"], ["calendar", "Stripe", "SMS", "email"]),
        SaasTemplate("lms", "LMS SaaS", "Courses, lessons, cohorts, progress, certificates, and billing.", ["course", "lesson", "learner", "cohort", "certificate"], ["course completion", "drip schedule", "assessment review"], ["video", "email", "analytics", "payments"]),
        SaasTemplate("marketplace", "Marketplace SaaS", "Listings, sellers, buyers, orders, payouts, and moderation.", ["listing", "seller", "buyer", "order", "payout"], ["seller onboarding", "dispute", "payout review"], ["Stripe Connect", "storage", "email", "analytics"]),
        SaasTemplate("internal_admin", "Internal Admin Dashboard", "Operational admin for users, approvals, audit, and reporting.", ["user", "role", "audit_event", "ticket", "report"], ["approval routing", "incident triage", "access review"], ["SSO", "Slack", "warehouse", "error tracking"]),
        SaasTemplate("ai_chatbot", "AI Chatbot SaaS", "Knowledge bases, conversations, usage billing, and support handoff.", ["bot", "knowledge_base", "conversation", "message", "usage_event"], ["handoff", "quality review", "usage alert"], ["OpenAI", "Stripe", "vector store", "helpdesk"]),
    ]
    return [asdict(template) for template in templates]
