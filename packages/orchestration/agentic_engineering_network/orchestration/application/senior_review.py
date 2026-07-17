from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.orchestration.application.product_discovery import (
    ProductDiscoveryService,
)
from agentic_engineering_network.orchestration.application.requirements_quality import (
    RequirementsQualityService,
)
from agentic_engineering_network.orchestration.application.sdlc_pipeline import get_senior_sdlc_pipeline
from agentic_engineering_network.orchestration.application.testing_strategy import get_test_strategy
from agentic_engineering_network.orchestration.domain.quality import (
    Finding,
    QualityScorecard,
    SeniorGateResult,
    gate_status,
)
from agentic_engineering_network.security.compliance_evidence import collect_compliance_evidence
from agentic_engineering_network.security.threat_model import build_threat_model


@dataclass(frozen=True)
class SeniorAssessment:
    idea: str
    weak_before: list[str]
    product_discovery: dict[str, object]
    requirements_quality: dict[str, object]
    sdlc_pipeline: list[dict[str, object]]
    test_strategy: dict[str, object]
    threat_model: dict[str, object]
    compliance_evidence: list[dict[str, object]]
    gates: list[dict[str, object]]
    scorecard: dict[str, int]
    release_blockers: list[str]
    human_review_required: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SeniorReviewService:
    def assess(self, idea: str) -> SeniorAssessment:
        product = ProductDiscoveryService().discover(idea)
        requirements = RequirementsQualityService().validate(idea)
        threat_model = build_threat_model()
        compliance_gate = self._compliance_gate()
        architecture_gate = self._architecture_gate()
        qa_gate = self._qa_gate()
        release_gate = self._release_gate([product.gate, requirements.gate, threat_model.gate, compliance_gate, architecture_gate, qa_gate])
        gates = [product.gate, requirements.gate, architecture_gate, threat_model.gate, qa_gate, compliance_gate, release_gate]
        scorecard = QualityScorecard(
            product_quality=product.gate.score,
            architecture_quality=architecture_gate.score,
            code_quality=76,
            test_quality=qa_gate.score,
            security_quality=threat_model.gate.score,
            compliance_readiness=compliance_gate.score,
            ux_quality=74,
            deployment_readiness=release_gate.score,
        )
        release_blockers = [
            fix
            for gate in gates
            if gate.status.value == "fail"
            for fix in gate.required_fixes
        ]
        return SeniorAssessment(
            idea=idea,
            weak_before=[
                "Agent outputs were role-prompt oriented rather than schema/rubric/gate oriented.",
                "Product discovery and requirement validation were present but not release-blocking.",
                "Security and compliance were checklists without evidence collection or STRIDE modeling.",
                "Testing lacked a formal strategy dashboard and failure-class policy.",
            ],
            product_discovery=product.to_dict(),
            requirements_quality=requirements.to_dict(),
            sdlc_pipeline=get_senior_sdlc_pipeline(),
            test_strategy=get_test_strategy(),
            threat_model=threat_model.to_dict(),
            compliance_evidence=collect_compliance_evidence(),
            gates=[gate.to_dict() for gate in gates],
            scorecard=scorecard.to_dict(),
            release_blockers=release_blockers,
            human_review_required=[
                "Legal/compliance claims and policy templates",
                "Production cloud architecture and cost model",
                "Domain-specific business invariants",
                "Security review of real auth, billing, and tenant policies",
            ],
        )

    def _architecture_gate(self) -> SeniorGateResult:
        return SeniorGateResult(
            "Architecture gate",
            gate_status(82, 0),
            82,
            [],
            ["Generated projects can drift if API/database/UI contracts are not reviewed together."],
            [],
            ["Add ADRs for every non-trivial generated project decision.", "Generate OpenAPI contract snapshots."],
            ["A principal engineer should review tradeoffs for high-risk domains."],
        )

    def _qa_gate(self) -> SeniorGateResult:
        return SeniorGateResult(
            "QA gate",
            gate_status(80, 0),
            80,
            [],
            ["Coverage thresholds require generated project instrumentation to become measurable."],
            [],
            ["Add mutation testing for critical algorithms.", "Persist coverage trend per run."],
            ["A senior QA engineer should review flaky-test classification for large apps."],
        )

    def _compliance_gate(self) -> SeniorGateResult:
        return SeniorGateResult(
            "Compliance gate",
            gate_status(68, 0),
            68,
            [
                Finding(
                    "high",
                    "compliance",
                    "Compliance artifacts are templates and evidence pointers, not legal approval.",
                    "Require legal and security review before making compliance claims.",
                )
            ],
            ["False compliance claims create legal and customer trust risk."],
            ["Collect signed policy ownership and legal review evidence before production claims."],
            ["Map controls to real customer commitments and vendor subprocessors."],
            ["Qualified counsel must review privacy, terms, DPA, cookie, and retention policies."],
        )

    def _release_gate(self, previous_gates: list[SeniorGateResult]) -> SeniorGateResult:
        score = round(sum(gate.score for gate in previous_gates) / len(previous_gates))
        failed = [gate.name for gate in previous_gates if gate.status.value == "fail"]
        return SeniorGateResult(
            "Release gate",
            gate_status(score, len(failed)),
            score,
            [
                Finding(
                    "critical",
                    "release",
                    f"Release blocked by: {', '.join(failed)}.",
                    "Resolve failed senior gates before packaging as production-ready.",
                )
            ]
            if failed
            else [],
            ["Production readiness depends on all upstream gates and real provider configuration."],
            [f"Resolve {name}." for name in failed],
            ["Run a staging deployment rehearsal with real secrets managed outside git."],
            ["Human sign-off is required for customer-facing production release."],
        )
