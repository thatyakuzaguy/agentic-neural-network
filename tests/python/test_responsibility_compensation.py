from agentic_engineering_network.orchestration.application.architecture_uncertainty import (
    get_architecture_uncertainty_review,
)
from agentic_engineering_network.orchestration.application.business_context import assess_business_context
from agentic_engineering_network.orchestration.application.confidence import ConfidenceLevel, build_confidence_dashboard
from agentic_engineering_network.orchestration.application.human_gates import (
    REQUIRED_HUMAN_GATES,
    make_human_gate_decision,
    summarize_human_gates,
)
from agentic_engineering_network.orchestration.application.market_validation import get_market_validation_workflow
from agentic_engineering_network.orchestration.application.release_readiness import evaluate_release_readiness
from agentic_engineering_network.orchestration.application.risk_register import (
    default_risk_register,
    unresolved_critical_count,
)


def test_business_context_blocks_when_critical_context_missing() -> None:
    assessment = assess_business_context({"industry": "healthcare"})

    assert assessment.approval_blocked is True
    assert assessment.confidence == ConfidenceLevel.BLOCKED
    assert "target_customer" in assessment.critical_missing


def test_market_validation_requires_external_evidence_before_product_approval() -> None:
    workflow = get_market_validation_workflow("Build me a SaaS CRM")

    assert workflow["product_approval_status"] == "evidence required"
    assert len(workflow["tasks"]) >= 5
    assert "Interview 10 target customers" in {task["title"] for task in workflow["tasks"]}


def test_human_gates_require_named_approver_and_all_required_gates() -> None:
    decision = make_human_gate_decision(
        {
            "gate_id": "product_owner_approval",
            "approver_name": "A. Owner",
            "role": "Product owner",
            "decision": "approved",
            "comments": "Evidence reviewed.",
            "risk_acceptance": "Accepts residual product risk.",
        }
    ).to_dict()

    summary = summarize_human_gates([decision])

    assert summary["complete"] is False
    assert len(summary["missing_gates"]) == len(REQUIRED_HUMAN_GATES) - 1


def test_risk_register_tracks_unresolved_critical_risks() -> None:
    risks = default_risk_register()

    assert unresolved_critical_count(risks) >= 1


def test_release_readiness_blocks_without_human_approvals_and_critical_risk_resolution() -> None:
    result = evaluate_release_readiness(
        human_gate_decisions=[],
        risks=default_risk_register(),
        security_checklist_passed=False,
        legal_reviewed=False,
        architecture_decisions_exist=True,
        tests_passed=True,
        deployment_checklist_passed=False,
    )

    assert result["status"] == "blocked"
    assert "required human approvals are incomplete" in result["blockers"]
    assert "qualified human owners" in result["responsibility_statement"]


def test_confidence_dashboard_uses_blocked_instead_of_absolute_guarantees() -> None:
    assessments = build_confidence_dashboard(
        market_evidence_count=0,
        business_missing_critical=3,
        unresolved_critical_risks=1,
        human_gate_missing=5,
    )

    assert {item["confidence"] for item in assessments} == {"blocked"}
    assert all(item["required_human_validation"] for item in assessments)


def test_architecture_uncertainty_requires_architect_signoff() -> None:
    review = get_architecture_uncertainty_review()

    assert review["architect_signoff_required"] is True
    assert review["tradeoff_analysis"]
    assert review["alternative_architecture_comparison"]
    assert review["failure_mode_analysis"]
