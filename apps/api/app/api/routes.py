from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from agentic_engineering_network.agents.definitions import get_agent_registry
from agentic_engineering_network.orchestration.readiness import get_saas_readiness_checklist
from agentic_engineering_network.orchestration.requirements_engine import refine_idea
from agentic_engineering_network.orchestration.saas_templates import get_saas_templates
from agentic_engineering_network.orchestration.application.sdlc_pipeline import get_senior_sdlc_pipeline
from agentic_engineering_network.orchestration.application.senior_review import SeniorReviewService
from agentic_engineering_network.orchestration.application.testing_strategy import get_test_strategy
from agentic_engineering_network.orchestration.application.architecture_uncertainty import (
    get_architecture_uncertainty_review,
)
from agentic_engineering_network.orchestration.application.business_context import assess_business_context
from agentic_engineering_network.orchestration.application.confidence import build_confidence_dashboard
from agentic_engineering_network.orchestration.application.human_gates import (
    make_human_gate_decision,
    summarize_human_gates,
)
from agentic_engineering_network.orchestration.application.market_validation import (
    get_market_validation_workflow,
)
from agentic_engineering_network.orchestration.application.release_readiness import (
    evaluate_release_readiness,
)
from agentic_engineering_network.orchestration.application.risk_register import unresolved_critical_count
from agentic_engineering_network.orchestration.application.approval_packets import build_approval_packets
from agentic_engineering_network.orchestration.application.intelligence import (
    ArchitectureIntelligenceEngine,
    ComplianceIntelligenceEngine,
    ProductIntelligenceEngine,
    ReleaseIntelligenceEngine,
    SecurityIntelligenceEngine,
    build_intelligence_suite,
)
from agentic_engineering_network.orchestration.application.simulation import run_estimate_simulations
from agentic_engineering_network.security.approvals import ApprovalRequest
from agentic_engineering_network.security.compliance import get_compliance_checklist
from agentic_engineering_network.security.compliance_evidence import collect_compliance_evidence
from agentic_engineering_network.security.threat_model import build_threat_model
from agentic_engineering_network.shared.billing import StripeBillingService
from agentic_engineering_network.shared.integrations import get_integration_statuses

from app.core.container import agent_office_service, approval_center, audit_logger, run_store
from app.core.settings import settings
from app.schemas.runs import (
    ApprovalDecision,
    BillingCheckoutRequest,
    BillingPortalRequest,
    BusinessContextSubmission,
    HumanGateSubmission,
    IdeaSubmission,
    PlatformSettingsUpdate,
    RequirementRefinementRequest,
    RiskRegisterSubmission,
    RunResponse,
    SeniorAssessmentRequest,
    SimulationRequest,
)
from app.services.approval_effects import apply_approval_effect
from app.services.evidence_store import EvidenceStore


router = APIRouter()


def evidence_store() -> EvidenceStore:
    return EvidenceStore(settings)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic-engineering-network-api"}


@router.get("/readinessz")
def readinessz() -> dict[str, object]:
    return {
        "status": "ready",
        "checks": {
            "run_state_path": settings.run_state_path.exists(),
            "generated_projects_path": settings.generated_projects_path.exists(),
            "audit_log_parent": settings.audit_log_path.parent.exists(),
        },
    }


@router.get("/errors/status")
def error_tracking_status() -> dict[str, object]:
    return {
        "provider": "sentry" if settings.sentry_dsn else "mock",
        "configured": bool(settings.sentry_dsn),
        "dsn_present": bool(settings.sentry_dsn),
    }


@router.get("/agents")
def agents() -> list[dict[str, object]]:
    return [asdict(agent) for agent in get_agent_registry()]


@router.get("/agent-office/state")
def agent_office_state() -> dict[str, object]:
    return agent_office_service.state()


@router.get("/agent-office/events")
def agent_office_events(limit: int = 50) -> dict[str, object]:
    safe_limit = max(1, min(limit, 200))
    return {"events": agent_office_service.events(safe_limit)}


@router.get("/readiness")
def readiness() -> dict[str, object]:
    return {
        "title": "SaaS Production Readiness",
        "disclaimer": "This checklist reduces launch risk but does not guarantee market success.",
        "sections": get_saas_readiness_checklist(),
    }


@router.get("/compliance")
def compliance() -> dict[str, object]:
    return {
        "title": "Compliance Checklist",
        "disclaimer": "Generated controls and templates are not legal advice; legal review is required.",
        "sections": get_compliance_checklist(),
    }


@router.get("/integrations/status")
def integrations_status() -> dict[str, object]:
    return {"providers": get_integration_statuses()}


@router.get("/billing/status")
def billing_status() -> dict[str, object]:
    return StripeBillingService().status()


@router.post("/billing/checkout")
def billing_checkout(payload: BillingCheckoutRequest) -> dict[str, object]:
    try:
        return StripeBillingService().create_checkout_session(payload.customer_email, payload.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/billing/portal")
def billing_portal(payload: BillingPortalRequest) -> dict[str, object]:
    try:
        return StripeBillingService().create_customer_portal(payload.customer_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/billing/webhook")
async def billing_webhook(request: Request) -> dict[str, object]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        return StripeBillingService().handle_webhook(payload, signature)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/saas-templates")
def saas_templates() -> dict[str, object]:
    return {"templates": get_saas_templates()}


@router.post("/requirements/refine")
def refine_requirements(payload: RequirementRefinementRequest) -> dict[str, object]:
    return refine_idea(payload.idea)


@router.post("/senior-review/assess")
def senior_review_assess(payload: SeniorAssessmentRequest) -> dict[str, object]:
    return SeniorReviewService().assess(payload.idea).to_dict()


@router.get("/senior-review/standards")
def senior_review_standards() -> dict[str, object]:
    return {
        "layers": ["domain", "application", "infrastructure", "interface/API", "UI"],
        "gates": ["Product", "Architecture", "Security", "QA", "Compliance", "Release"],
        "score_areas": [
            "product_quality",
            "architecture_quality",
            "code_quality",
            "test_quality",
            "security_quality",
            "compliance_readiness",
            "ux_quality",
            "deployment_readiness",
        ],
        "blocking_policy": "Critical security, compliance, release, or architecture findings block production release.",
    }


@router.get("/sdlc/pipeline")
def sdlc_pipeline() -> dict[str, object]:
    return {"phases": get_senior_sdlc_pipeline()}


@router.get("/testing/strategy")
def testing_strategy() -> dict[str, object]:
    return get_test_strategy()


@router.get("/security/threat-model")
def threat_model() -> dict[str, object]:
    return build_threat_model().to_dict()


@router.get("/compliance/evidence")
def compliance_evidence() -> dict[str, object]:
    return {"evidence": collect_compliance_evidence()}


@router.post("/market-validation")
def market_validation(payload: SeniorAssessmentRequest) -> dict[str, object]:
    return get_market_validation_workflow(payload.idea)


@router.post("/intelligence/product")
def product_intelligence(payload: SeniorAssessmentRequest) -> dict[str, object]:
    return ProductIntelligenceEngine().generate(payload.idea)


@router.get("/intelligence/architecture")
def architecture_intelligence() -> dict[str, object]:
    return ArchitectureIntelligenceEngine().generate()


@router.get("/intelligence/security")
def security_intelligence() -> dict[str, object]:
    return SecurityIntelligenceEngine().generate()


@router.get("/intelligence/compliance")
def compliance_intelligence() -> dict[str, object]:
    return ComplianceIntelligenceEngine().generate()


@router.get("/intelligence/release")
def release_intelligence() -> dict[str, object]:
    return ReleaseIntelligenceEngine().generate()


@router.post("/intelligence/suite")
def intelligence_suite(payload: SeniorAssessmentRequest) -> dict[str, object]:
    return build_intelligence_suite(payload.idea)


@router.post("/simulations")
def simulations(payload: SimulationRequest) -> dict[str, object]:
    return run_estimate_simulations(payload.monthly_visitors, payload.conversion_rate, payload.price)


@router.get("/approval-packets")
def approval_packets() -> dict[str, object]:
    return build_approval_packets()


@router.get("/business-context")
def get_business_context() -> dict[str, object]:
    context = evidence_store().read_business_context()
    return assess_business_context(context).to_dict()


@router.post("/business-context")
def save_business_context(payload: BusinessContextSubmission) -> dict[str, object]:
    saved = evidence_store().write_business_context(payload.model_dump())
    audit_logger.record(
        "business_context.saved",
        "BusinessContextIntake",
        "Saved business context evidence.",
        {"completed_fields": assess_business_context(saved).completed_fields},
    )
    return assess_business_context(saved).to_dict()


@router.get("/human-gates")
def human_gates() -> dict[str, object]:
    return summarize_human_gates(evidence_store().read_human_gate_decisions())


@router.post("/human-gates")
def decide_human_gate(payload: HumanGateSubmission) -> dict[str, object]:
    try:
        decision = make_human_gate_decision(payload.model_dump()).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    decisions = evidence_store().append_human_gate_decision(decision)
    audit_logger.record(
        "human_gate.decided",
        "HumanResponsibilityGate",
        f"{decision['gate_id']} marked {decision['decision']} by {decision['approver_name']}.",
        decision,
    )
    return summarize_human_gates(decisions)


@router.get("/risks")
def risk_register() -> dict[str, object]:
    risks = evidence_store().read_risks()
    return {"risks": risks, "unresolved_critical": unresolved_critical_count(risks)}


@router.post("/risks")
def save_risk_register(payload: RiskRegisterSubmission) -> dict[str, object]:
    risks = evidence_store().write_risks(payload.risks)
    audit_logger.record(
        "risk_register.saved",
        "RiskRegister",
        "Saved centralized risk register.",
        {"risk_count": len(risks), "unresolved_critical": unresolved_critical_count(risks)},
    )
    return {"risks": risks, "unresolved_critical": unresolved_critical_count(risks)}


@router.get("/confidence")
def confidence_dashboard() -> dict[str, object]:
    business = assess_business_context(evidence_store().read_business_context())
    risks = evidence_store().read_risks()
    gates = summarize_human_gates(evidence_store().read_human_gate_decisions())
    market_evidence_count = len(business.completed_fields)
    assessments = build_confidence_dashboard(
        market_evidence_count=market_evidence_count,
        business_missing_critical=len(business.critical_missing),
        unresolved_critical_risks=unresolved_critical_count(risks),
        human_gate_missing=len(gates["missing_gates"]),
    )
    return {
        "assessments": assessments,
        "responsibility_statement": (
            "This platform can assist at a senior/staff level, but production responsibility remains "
            "with qualified human owners."
        ),
    }


@router.get("/architecture/uncertainty")
def architecture_uncertainty() -> dict[str, object]:
    return get_architecture_uncertainty_review()


@router.get("/legal/workflow")
def legal_workflow() -> dict[str, object]:
    return {
        "legal_review_required": True,
        "jurisdiction_selector": ["EU/GDPR", "United States", "United Kingdom", "Canada", "Other/manual review"],
        "privacy_data_processing_questionnaire": [
            "What personal data is collected?",
            "What is the lawful basis or contractual basis?",
            "Where is data stored and processed?",
            "Which subprocessors are used?",
            "What are retention and deletion timelines?",
            "How are DSAR/export/delete requests handled?",
        ],
        "generated_templates": [
            "docs/compliance-templates/PRIVACY_POLICY_TEMPLATE.md",
            "docs/compliance-templates/TERMS_OF_SERVICE_TEMPLATE.md",
            "docs/compliance-templates/DPA_TEMPLATE.md",
            "docs/compliance-templates/SECURITY_POLICY_TEMPLATE.md",
            "docs/compliance-templates/DATA_RETENTION_POLICY_TEMPLATE.md",
        ],
        "draft_notice": "All legal outputs are drafts requiring qualified human review.",
    }


@router.get("/security/production-readiness")
def production_security_readiness() -> dict[str, object]:
    risks = evidence_store().read_risks()
    return {
        "production_security_readiness_checklist": [
            "Threat model approved",
            "Penetration test completed or explicitly waived by security owner",
            "Dependency scan reviewed",
            "Secret scan reviewed",
            "Auth and RBAC reviewed against real roles",
            "Rate limits and abuse controls reviewed",
            "Accepted risks documented",
        ],
        "threat_model_approval_required": True,
        "penetration_test_required": True,
        "dependency_scan_results": "Run via .github/workflows/security-scan.yml or local pip/npm audit.",
        "secret_scan_results": "Run gitleaks or equivalent before release.",
        "security_risk_register": [risk for risk in risks if risk.get("category") == "security"],
        "accepted_risk_workflow": "Critical risks must be resolved or accepted by the security owner before release.",
        "production_blocked": unresolved_critical_count(risks) > 0,
    }


@router.get("/release/readiness")
def release_readiness() -> dict[str, object]:
    risks = evidence_store().read_risks()
    human_gate_decisions = evidence_store().read_human_gate_decisions()
    return evaluate_release_readiness(
        human_gate_decisions=human_gate_decisions,
        risks=risks,
        security_checklist_passed=unresolved_critical_count(
            [risk for risk in risks if risk.get("category") == "security"]
        )
        == 0,
        legal_reviewed=any(
            decision.get("gate_id") == "legal_compliance_approval"
            and decision.get("decision") == "approved"
            for decision in human_gate_decisions
        ),
        architecture_decisions_exist=True,
        tests_passed=True,
        deployment_checklist_passed=False,
    )


@router.get("/settings")
def platform_settings() -> dict[str, object]:
    return {
        "max_repair_attempts": settings.max_repair_attempts,
        "repair_backoff_base_seconds": settings.repair_backoff_base_seconds,
        "repair_backoff_max_seconds": settings.repair_backoff_max_seconds,
        "ai_provider": settings.ai_provider,
        "local_model_path": str(settings.local_model_path),
        "notes": [
            "Set AEN_MAX_REPAIR_ATTEMPTS in .env/docker-compose environment and restart API to persist changes.",
            "Retry history is written to each generated project's .aen/retry-history.json file.",
        ],
    }


@router.post("/settings")
def update_platform_settings(payload: PlatformSettingsUpdate) -> dict[str, object]:
    if payload.max_repair_attempts < 1 or payload.max_repair_attempts > 50:
        raise HTTPException(status_code=400, detail="max_repair_attempts must be between 1 and 50.")
    return {
        "max_repair_attempts": payload.max_repair_attempts,
        "requires_restart": True,
        "message": "Persist by setting AEN_MAX_REPAIR_ATTEMPTS in .env and recreating the API container.",
    }


@router.post("/runs", response_model=RunResponse)
def create_run(payload: IdeaSubmission) -> dict[str, object]:
    try:
        return run_store.start(payload.idea, payload.workspace_directory, payload.approval_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs", response_model=list[RunResponse])
def list_runs(limit: int = 25) -> list[dict[str, object]]:
    return run_store.list(limit=limit)


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> dict[str, object]:
    run = run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/approvals")
def approvals() -> list[dict[str, object]]:
    return [asdict(item) for item in approval_center.list()]


@router.post("/approvals/{approval_id}")
def resolve_approval(approval_id: str, payload: ApprovalDecision) -> dict[str, object]:
    try:
        item = approval_center.resolve(approval_id, payload.approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    if payload.approved:
        _apply_approval_effect(item)
    run_store.handle_approval_resolution(item)
    return asdict(item)


@router.get("/logs/audit")
def audit_logs(limit: int = 100) -> list[dict[str, object]]:
    return audit_logger.tail(limit=limit)


def _apply_approval_effect(item: ApprovalRequest) -> None:
    apply_approval_effect(item, settings, audit_logger)
