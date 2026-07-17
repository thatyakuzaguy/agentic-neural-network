from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EvidenceConfidence:
    area: str
    confidence: ConfidenceLevel
    evidence_used: list[str]
    missing_evidence: list[str]
    assumptions: list[str]
    risks: list[str]
    required_human_validation: list[str]

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "confidence": self.confidence.value}


def confidence_from_evidence(evidence_count: int, missing_critical: int) -> ConfidenceLevel:
    if missing_critical > 0:
        return ConfidenceLevel.BLOCKED
    if evidence_count >= 5:
        return ConfidenceLevel.HIGH
    if evidence_count >= 2:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def build_confidence_dashboard(
    market_evidence_count: int,
    business_missing_critical: int,
    unresolved_critical_risks: int,
    human_gate_missing: int,
) -> list[dict[str, object]]:
    assessments = [
        EvidenceConfidence(
            "product_market",
            confidence_from_evidence(market_evidence_count, business_missing_critical),
            ["business context", "market validation workflow"] if market_evidence_count else [],
            ["customer interviews", "willingness-to-pay proof", "landing-page conversion data"],
            ["Initial market signal is based on user-provided context until field evidence is attached."],
            ["Building the wrong product despite good engineering execution."],
            ["Product owner must approve evidence before product gate passes."],
        ),
        EvidenceConfidence(
            "security",
            ConfidenceLevel.BLOCKED if unresolved_critical_risks else ConfidenceLevel.MEDIUM,
            ["threat model", "security checklist", "risk register"],
            ["penetration test report", "live dependency scan results", "real auth/RBAC review"],
            ["Local checks are not a substitute for production security ownership."],
            ["Critical security risks can block production release."],
            ["Security owner must accept or resolve production risks."],
        ),
        EvidenceConfidence(
            "compliance",
            ConfidenceLevel.BLOCKED,
            ["policy templates", "compliance checklist", "evidence room"],
            ["qualified legal review", "jurisdiction-specific obligations", "signed DPA review"],
            ["All generated legal/compliance outputs are drafts."],
            ["False compliance claims create legal and trust risk."],
            ["Legal/compliance owner must review and sign off."],
        ),
        EvidenceConfidence(
            "release",
            ConfidenceLevel.BLOCKED if human_gate_missing or unresolved_critical_risks else ConfidenceLevel.MEDIUM,
            ["test results", "deployment checklist", "senior gates"],
            ["human approvals", "staging rehearsal", "rollback evidence"],
            ["Release confidence depends on both automated gates and human owners."],
            ["Unowned risks can ship into production."],
            ["Release owner must approve final readiness."],
        ),
    ]
    return [assessment.to_dict() for assessment in assessments]
