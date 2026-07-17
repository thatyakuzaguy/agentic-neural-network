from agentic_engineering_network.orchestration.readiness import get_saas_readiness_checklist
from agentic_engineering_network.orchestration.requirements_engine import refine_idea
from agentic_engineering_network.orchestration.saas_templates import get_saas_templates
from agentic_engineering_network.security.compliance import get_compliance_checklist
from agentic_engineering_network.shared.billing import StripeBillingService, get_stripe_config
from agentic_engineering_network.shared.integrations import get_integration_statuses


def test_saas_readiness_has_required_sections() -> None:
    sections = {section["id"]: section for section in get_saas_readiness_checklist()}

    assert {
        "product_market",
        "pricing",
        "onboarding",
        "billing",
        "observability",
        "support_admin",
        "deployment",
    }.issubset(sections)
    assert all(section["items"] for section in sections.values())


def test_compliance_marks_legal_review_items() -> None:
    sections = get_compliance_checklist()
    legal_items = [
        item
        for section in sections
        for item in section["items"]
        if item.get("legal_review_required", False)
    ]

    assert legal_items


def test_requirement_refinement_generates_contracts_and_tests() -> None:
    refinement = refine_idea("Build me a SaaS CRM with billing and dashboards")

    assert refinement["domain_model"]
    assert refinement["user_stories"]
    assert refinement["acceptance_criteria"]
    assert refinement["api_contracts"]
    assert refinement["test_cases"]


def test_saas_templates_cover_requested_domains() -> None:
    template_ids = {template["id"] for template in get_saas_templates()}

    assert {
        "crm",
        "ecommerce",
        "booking",
        "lms",
        "marketplace",
        "internal_admin",
        "ai_chatbot",
    }.issubset(template_ids)


def test_integrations_include_mock_and_real_provider_paths() -> None:
    statuses = get_integration_statuses()
    categories = {status["category"] for status in statuses}
    modes = {status["mode"] for status in statuses}

    assert {"email", "payments", "analytics", "storage", "auth", "notifications"}.issubset(categories)
    assert "mock" in modes


def test_stripe_billing_defaults_to_mock_mode() -> None:
    config = get_stripe_config()
    service = StripeBillingService(config)
    checkout = service.create_checkout_session("buyer@example.com", "tenant-demo")
    portal = service.create_customer_portal("cus_mock")
    webhook = service.handle_webhook(b"{}", None)

    assert service.status()["mock_mode"] is True
    assert checkout["mode"] == "mock"
    assert portal["mode"] == "mock"
    assert webhook["received"] is True
