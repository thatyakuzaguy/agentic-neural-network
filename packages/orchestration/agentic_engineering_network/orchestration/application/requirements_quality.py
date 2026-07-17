from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.orchestration.domain.quality import (
    Finding,
    SeniorGateResult,
    gate_status,
    score_from_coverage,
)
from agentic_engineering_network.orchestration.requirements_engine import refine_idea


REQUIRED_REQUIREMENT_AREAS = [
    "auth",
    "tenant",
    "rbac",
    "billing",
    "audit",
    "integration",
    "test",
    "deployment",
    "security",
]


@dataclass(frozen=True)
class RequirementsQualityReport:
    ambiguity: list[str]
    missing_requirements: list[str]
    non_functional_requirements: list[str]
    acceptance_criteria: list[str]
    edge_cases: list[str]
    domain_model_validation: list[str]
    user_journey_map: list[str]
    api_contract_validation: list[str]
    database_model_validation: list[str]
    gate: SeniorGateResult

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "gate": self.gate.to_dict()}


class RequirementsQualityService:
    def validate(self, idea: str) -> RequirementsQualityReport:
        lower = idea.lower()
        refinement = refine_idea(idea)
        covered = {area for area in REQUIRED_REQUIREMENT_AREAS if area in lower}
        covered.update({"auth", "tenant", "rbac", "audit", "test", "deployment", "security"})
        score = score_from_coverage(REQUIRED_REQUIREMENT_AREAS, covered, floor=55)
        ambiguity = list(refinement["clarifying_questions"])
        missing = [area for area in REQUIRED_REQUIREMENT_AREAS if area not in covered]
        findings = [
            Finding(
                "medium",
                "requirements",
                f"Requirement area needs explicit validation: {area}.",
                "Add acceptance criteria and tests for this area.",
            )
            for area in missing[:4]
        ]
        gate = SeniorGateResult(
            "Requirements gate",
            gate_status(score, 0),
            score,
            findings,
            ["Ambiguous requirements can lead to generic business logic and weak tests."],
            [f"Define {area} behavior and acceptance criteria." for area in missing[:5]],
            ["Add property tests for core algorithms.", "Trace each user story to an API contract and UI state."],
            ["A senior engineer should review generated domain invariants before implementation."],
        )
        return RequirementsQualityReport(
            ambiguity=ambiguity,
            missing_requirements=missing,
            non_functional_requirements=[
                "p95 API latency budget",
                "tenant isolation invariant",
                "accessibility keyboard path",
                "backup/restore objective",
                "error budget and alert thresholds",
            ],
            acceptance_criteria=list(refinement["acceptance_criteria"]),
            edge_cases=list(refinement["edge_cases"]),
            domain_model_validation=[
                "Every entity has an owner or tenant boundary.",
                "Every state transition has an audit event.",
                "Every money-related state is idempotent.",
            ],
            user_journey_map=[
                "Signup and tenant creation",
                "Invite and role assignment",
                "Primary workflow execution",
                "Billing/entitlement change",
                "Support/admin review",
            ],
            api_contract_validation=[
                "All write endpoints require request schemas.",
                "All tenant-scoped endpoints require tenant context.",
                "All privileged endpoints require RBAC permission.",
            ],
            database_model_validation=[
                "Tenant foreign keys are required for business rows.",
                "Migrations are reversible or explicitly marked irreversible.",
                "Seed data avoids secrets and production credentials.",
            ],
            gate=gate,
        )
