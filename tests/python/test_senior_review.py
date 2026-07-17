from agentic_engineering_network.orchestration.application.product_discovery import ProductDiscoveryService
from agentic_engineering_network.orchestration.application.requirements_quality import RequirementsQualityService
from agentic_engineering_network.orchestration.application.sdlc_pipeline import get_senior_sdlc_pipeline
from agentic_engineering_network.orchestration.application.senior_review import SeniorReviewService
from agentic_engineering_network.orchestration.application.testing_strategy import get_test_strategy
from agentic_engineering_network.security.compliance_evidence import collect_compliance_evidence
from agentic_engineering_network.security.threat_model import build_threat_model


def test_product_discovery_blocks_weak_product_plan() -> None:
    report = ProductDiscoveryService().discover("Build me an app")

    assert report.gate.status.value in {"fail", "needs_human_review"}
    assert report.gate.required_fixes


def test_requirements_quality_reports_missing_areas_and_validation() -> None:
    report = RequirementsQualityService().validate("Build me a CRM")

    assert "billing" in report.missing_requirements
    assert report.non_functional_requirements
    assert report.api_contract_validation
    assert report.database_model_validation


def test_sdlc_pipeline_has_gate_contract_for_each_phase() -> None:
    phases = get_senior_sdlc_pipeline()

    assert len(phases) >= 10
    assert all(phase["inputs"] for phase in phases)
    assert all(phase["outputs"] for phase in phases)
    assert all(phase["validation_checks"] for phase in phases)
    assert all(phase["approval_gates"] for phase in phases)
    assert all(phase["retry_strategy"] for phase in phases)


def test_security_threat_model_includes_stride_reviews() -> None:
    model = build_threat_model()

    assert set(model.stride) == {
        "spoofing",
        "tampering",
        "repudiation",
        "information_disclosure",
        "denial_of_service",
        "elevation_of_privilege",
    }
    assert model.gate.score > 0


def test_test_strategy_has_senior_suite_mix() -> None:
    strategy = get_test_strategy()
    suite_names = {suite["name"] for suite in strategy["suites"]}

    assert {"unit", "integration", "contract", "e2e", "security", "smoke", "regression"}.issubset(suite_names)


def test_compliance_evidence_marks_legal_templates() -> None:
    evidence = collect_compliance_evidence()

    assert any(item["human_review_required"] for item in evidence)
    assert any(item["control"] == "ci_security_scan" for item in evidence)


def test_senior_assessment_returns_scores_gates_and_human_review_notes() -> None:
    assessment = SeniorReviewService().assess(
        "Build me a SaaS CRM with billing, tenant isolation, RBAC, analytics, tests, and deployment"
    )
    payload = assessment.to_dict()

    assert payload["scorecard"]["overall"] >= 60
    assert len(payload["gates"]) >= 6
    assert payload["human_review_required"]
    assert payload["sdlc_pipeline"]
    assert payload["test_strategy"]
