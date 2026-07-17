from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.orchestration.application.architecture_uncertainty import (
    get_architecture_uncertainty_review,
)
from agentic_engineering_network.orchestration.application.confidence import ConfidenceLevel
from agentic_engineering_network.orchestration.application.market_validation import (
    get_market_validation_workflow,
)
from agentic_engineering_network.orchestration.application.risk_register import default_risk_register
from agentic_engineering_network.security.compliance import get_compliance_checklist
from agentic_engineering_network.security.compliance_evidence import collect_compliance_evidence
from agentic_engineering_network.security.threat_model import build_threat_model


RESPONSIBILITY_STATEMENT = (
    "This system provides staff/principal-level engineering assistance and decision support. "
    "Final responsibility for market success, legal compliance, security, architecture, and production deployment "
    "remains with qualified human decision-makers."
)


@dataclass(frozen=True)
class IntelligenceConclusion:
    title: str
    confidence: ConfidenceLevel
    evidence: list[str]
    assumptions: list[str]
    unknowns: list[str]
    risks: list[str]
    human_validation_required: list[str]

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "confidence": self.confidence.value}


class ProductIntelligenceEngine:
    def generate(self, idea: str) -> dict[str, object]:
        validation = get_market_validation_workflow(idea)
        unsupported_assumptions = [
            "Target customer has urgent pain",
            "Budget owner exists and can buy",
            "Chosen pricing maps to perceived value",
        ]
        return {
            "responsibility_statement": RESPONSIBILITY_STATEMENT,
            "icp_profiles": ["Primary ICP", "Budget owner ICP", "Early adopter ICP"],
            "customer_personas": ["Economic buyer", "Admin/operator", "Daily user", "Support reviewer"],
            "market_hypotheses": ["Customers will switch if activation is faster than current workaround."],
            "value_propositions": ["Reduce manual workflow effort with auditable automation."],
            "pricing_models": ["per-seat subscription", "usage add-on", "enterprise compliance tier"],
            "feature_prioritization": [
                {"feature": "primary workflow", "priority": "P0", "reason": "direct value delivery"},
                {"feature": "billing entitlement", "priority": "P0", "reason": "monetization path"},
                {"feature": "advanced customization", "priority": "P2", "reason": "post-validation expansion"},
            ],
            "opportunity_scoring": {"confidence": "low", "reason": "external market evidence is still required"},
            "competitor_analysis": validation["competitor_research_template"],
            "customer_interview_plans": validation["interview_script"],
            "survey_templates": validation["survey_generator"],
            "landing_page_experiment_plans": validation["landing_page_experiment_checklist"],
            "validation_roadmaps": validation["tasks"],
            "gtm_plans": ["ICP landing page", "founder-led discovery", "pilot cohort", "case-study launch"],
            "churn_risk_analysis": ["unclear activation event", "insufficient onboarding", "weak switching cost"],
            "monetization_analysis": ["validate WTP", "model COGS", "define expansion trigger"],
            "unsupported_assumptions": unsupported_assumptions,
            "missing_market_evidence": ["interviews", "survey data", "conversion data", "pricing proof"],
            "weak_business_case_flags": ["No product is marked validated without evidence."],
            "weak_monetization_flags": ["Pricing remains a hypothesis until buyers confirm budget."],
            "conclusion": IntelligenceConclusion(
                "Product validation",
                ConfidenceLevel.BLOCKED,
                ["generated validation workflow"],
                unsupported_assumptions,
                ["actual willingness to pay", "conversion rate", "sales cycle"],
                ["building a product without validated demand"],
                ["Product owner approval after evidence review"],
            ).to_dict(),
        }


class ArchitectureIntelligenceEngine:
    def generate(self) -> dict[str, object]:
        uncertainty = get_architecture_uncertainty_review()
        return {
            "responsibility_statement": RESPONSIBILITY_STATEMENT,
            "adrs": uncertainty["architecture_decision_records"],
            "architecture_diagrams": ["system context", "container view", "runtime sequence", "data flow"],
            "scalability_analysis": uncertainty["scalability_assumptions"],
            "performance_projections": ["baseline p95 targets required", "load test required before production"],
            "infrastructure_estimates": ["local Docker", "single cloud region", "managed Postgres", "object storage"],
            "tradeoff_analysis": uncertainty["tradeoff_analysis"],
            "domain_driven_design_suggestions": ["bounded contexts", "tenant aggregate", "billing aggregate", "audit log"],
            "event_driven_alternatives": ["webhook events", "async job queue", "outbox pattern"],
            "monolith_vs_microservice_analysis": [
                {"option": "modular monolith", "fit": "best default", "risk": "module boundaries need review"},
                {"option": "microservices", "fit": "only after team/scale proof", "risk": "ops complexity"},
            ],
            "database_alternatives": ["PostgreSQL", "read replica", "Redis cache", "search index"],
            "deployment_alternatives": uncertainty["alternative_architecture_comparison"],
            "cost_projections": uncertainty["cost_assumptions"],
            "assumptions": uncertainty["scalability_assumptions"],
            "risks": ["unknown peak load", "unknown data volume", "cloud cost variance"],
            "failure_modes": uncertainty["failure_mode_analysis"],
            "mitigation_plans": ["load test", "backup rehearsal", "rollback runbook", "ADR review"],
            "conclusion": IntelligenceConclusion(
                "Architecture fit",
                ConfidenceLevel.MEDIUM,
                ["ADRs", "tradeoff analysis", "failure-mode analysis"],
                uncertainty["scalability_assumptions"],
                ["actual workload", "domain-specific constraints"],
                ["architecture may not be optimal for every domain"],
                ["Senior architect sign-off"],
            ).to_dict(),
        }


class SecurityIntelligenceEngine:
    def generate(self) -> dict[str, object]:
        threat_model = build_threat_model().to_dict()
        return {
            "responsibility_statement": RESPONSIBILITY_STATEMENT,
            "stride_analysis": threat_model["stride"],
            "owasp_analysis": [
                "broken access control",
                "cryptographic failures",
                "injection",
                "insecure design",
                "security misconfiguration",
                "vulnerable components",
                "identification/authentication failures",
                "software/data integrity failures",
                "logging and monitoring failures",
                "server-side request forgery",
            ],
            "dependency_scanning": threat_model["dependency_checks"],
            "secret_scanning": ["gitleaks", "repository ignore rules", "environment-only secrets"],
            "threat_modeling": threat_model,
            "attack_surface_mapping": ["API routes", "billing webhooks", "generated project sandbox", "Docker socket", "local model runtime"],
            "privilege_review": ["admin token", "approval center", "Docker execution boundary"],
            "rbac_review": threat_model["rbac_review"],
            "api_abuse_analysis": threat_model["api_abuse_review"],
            "security_checklist_generation": threat_model["input_validation_review"] + threat_model["rate_limit_review"],
            "penetration_test_preparation": ["scope API/UI", "seed test tenant", "define no-go production data"],
            "release_contains": {
                "threats": threat_model["stride"],
                "mitigations": threat_model["gate"]["optional_improvements"],
                "residual_risks": threat_model["gate"]["risks"],
                "unresolved_risks": threat_model["gate"]["required_fixes"],
            },
            "conclusion": IntelligenceConclusion(
                "Security readiness",
                ConfidenceLevel.MEDIUM,
                ["STRIDE", "security checklist", "secret scan design"],
                ["local static review is not a penetration test"],
                ["real provider configuration", "runtime exploitability"],
                ["never claim fully secure"],
                ["Security owner review and penetration test decision"],
            ).to_dict(),
        }


class ComplianceIntelligenceEngine:
    def generate(self) -> dict[str, object]:
        return {
            "responsibility_statement": RESPONSIBILITY_STATEMENT,
            "privacy_policy_drafts": ["docs/compliance-templates/PRIVACY_POLICY_TEMPLATE.md"],
            "terms_drafts": ["docs/compliance-templates/TERMS_OF_SERVICE_TEMPLATE.md"],
            "dpa_drafts": ["docs/compliance-templates/DPA_TEMPLATE.md"],
            "retention_policy_drafts": ["docs/compliance-templates/DATA_RETENTION_POLICY_TEMPLATE.md"],
            "security_policy_drafts": ["docs/compliance-templates/SECURITY_POLICY_TEMPLATE.md"],
            "gdpr_readiness_checklists": get_compliance_checklist(),
            "soc2_lite_readiness_checklists": get_compliance_checklist(),
            "iso27001_lite_readiness_checklists": get_compliance_checklist(),
            "accessibility_readiness_reports": ["WCAG review required", "keyboard path required", "contrast review required"],
            "compliance_evidence_repository": collect_compliance_evidence(),
            "compliance_gap_analysis": [
                "qualified legal review missing",
                "jurisdiction-specific obligations missing",
                "subprocessor list must be verified",
                "customer contract terms not reviewed",
            ],
            "jurisdictions_requiring_review": ["EU/GDPR", "United States", "United Kingdom", "Other selected markets"],
            "conclusion": IntelligenceConclusion(
                "Compliance readiness",
                ConfidenceLevel.BLOCKED,
                ["policy drafts", "evidence checklist"],
                ["templates are not legal advice"],
                ["jurisdiction-specific legal obligations"],
                ["never claim guaranteed compliance"],
                ["Qualified legal/compliance owner sign-off"],
            ).to_dict(),
        }


class ReleaseIntelligenceEngine:
    def generate(self) -> dict[str, object]:
        return {
            "responsibility_statement": RESPONSIBILITY_STATEMENT,
            "release_readiness_reports": ["senior gates", "risk register", "human approvals", "test results"],
            "deployment_readiness_reports": ["compose config", "environment validation", "provider configuration"],
            "rollback_plans": ["restore previous image", "database backup restore", "feature flag off-ramp"],
            "migration_plans": ["run migrations", "verify schema", "backup before migration", "rollback notes"],
            "backup_verification_plans": ["pg_dump", "restore rehearsal", "retention verification"],
            "observability_readiness_reports": ["health", "readiness", "logs", "error tracking", "metrics plan"],
            "monitoring_plans": ["API health", "job failures", "billing webhook errors", "database storage", "latency"],
            "incident_response_plans": ["severity matrix", "on-call owner", "customer comms", "postmortem"],
            "release_blockers": [
                "critical tests fail",
                "critical risks exist",
                "security review incomplete",
                "compliance review incomplete",
                "architecture review incomplete",
            ],
            "conclusion": IntelligenceConclusion(
                "Release readiness",
                ConfidenceLevel.BLOCKED,
                ["release checklist", "test results", "risk register"],
                ["staging rehearsal still required"],
                ["real production environment behavior"],
                ["unowned production risk"],
                ["Release owner final approval"],
            ).to_dict(),
        }


def build_intelligence_suite(idea: str) -> dict[str, object]:
    return {
        "responsibility_statement": RESPONSIBILITY_STATEMENT,
        "product": ProductIntelligenceEngine().generate(idea),
        "architecture": ArchitectureIntelligenceEngine().generate(),
        "security": SecurityIntelligenceEngine().generate(),
        "compliance": ComplianceIntelligenceEngine().generate(),
        "release": ReleaseIntelligenceEngine().generate(),
        "enterprise_risks": default_risk_register(),
    }
