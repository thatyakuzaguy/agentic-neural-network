from agentic_engineering_network.orchestration.application.approval_packets import build_approval_packets
from agentic_engineering_network.orchestration.application.confidence import ConfidenceLevel
from agentic_engineering_network.orchestration.application.intelligence import (
    RESPONSIBILITY_STATEMENT,
    ArchitectureIntelligenceEngine,
    ComplianceIntelligenceEngine,
    ProductIntelligenceEngine,
    ReleaseIntelligenceEngine,
    SecurityIntelligenceEngine,
    build_intelligence_suite,
)
from agentic_engineering_network.orchestration.application.simulation import run_estimate_simulations


def test_intelligence_suite_contains_owner_engines_and_responsibility_statement() -> None:
    suite = build_intelligence_suite("Build me a SaaS CRM")

    assert suite["responsibility_statement"] == RESPONSIBILITY_STATEMENT
    assert {"product", "architecture", "security", "compliance", "release"}.issubset(suite)


def test_product_intelligence_never_marks_product_validated_without_evidence() -> None:
    report = ProductIntelligenceEngine().generate("Build me a SaaS CRM")

    assert report["conclusion"]["confidence"] == ConfidenceLevel.BLOCKED.value
    assert report["missing_market_evidence"]
    assert "No product is marked validated without evidence." in report["weak_business_case_flags"]


def test_architecture_intelligence_contains_alternatives_and_uncertainty() -> None:
    report = ArchitectureIntelligenceEngine().generate()

    assert report["tradeoff_analysis"]
    assert report["deployment_alternatives"]
    assert report["conclusion"]["confidence"] in {"medium", "blocked", "low", "high"}


def test_security_intelligence_contains_required_release_risk_sections() -> None:
    report = SecurityIntelligenceEngine().generate()

    assert report["stride_analysis"]
    assert report["owasp_analysis"]
    assert {"threats", "mitigations", "residual_risks", "unresolved_risks"}.issubset(report["release_contains"])


def test_compliance_intelligence_blocks_until_human_legal_review() -> None:
    report = ComplianceIntelligenceEngine().generate()

    assert report["conclusion"]["confidence"] == "blocked"
    assert report["compliance_gap_analysis"]


def test_release_intelligence_blocks_on_incomplete_reviews() -> None:
    report = ReleaseIntelligenceEngine().generate()

    assert report["conclusion"]["confidence"] == "blocked"
    assert "security review incomplete" in report["release_blockers"]


def test_simulations_are_marked_as_estimates() -> None:
    simulation = run_estimate_simulations(monthly_visitors=1000, conversion_rate=0.05, price=50)

    assert "estimates" in simulation["estimate_notice"]
    assert simulation["pricing"]["monthly_recurring_revenue"] == 2500


def test_approval_packets_prepare_decision_packages_for_humans() -> None:
    packets = build_approval_packets()

    assert len(packets["packets"]) == 5
    assert all(packet["required_actions"] for packet in packets["packets"])
