from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True)
class Finding:
    severity: str
    area: str
    message: str
    recommendation: str


@dataclass(frozen=True)
class SeniorGateResult:
    name: str
    status: GateStatus
    score: int
    findings: list[Finding]
    risks: list[str]
    required_fixes: list[str]
    optional_improvements: list[str]
    human_review_notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "status": self.status.value,
            "findings": [asdict(finding) for finding in self.findings],
        }


@dataclass(frozen=True)
class QualityScorecard:
    product_quality: int
    architecture_quality: int
    code_quality: int
    test_quality: int
    security_quality: int
    compliance_readiness: int
    ux_quality: int
    deployment_readiness: int

    @property
    def overall(self) -> int:
        values = [
            self.product_quality,
            self.architecture_quality,
            self.code_quality,
            self.test_quality,
            self.security_quality,
            self.compliance_readiness,
            self.ux_quality,
            self.deployment_readiness,
        ]
        return round(sum(values) / len(values))

    def to_dict(self) -> dict[str, int]:
        return {**asdict(self), "overall": self.overall}


def score_from_coverage(required_items: list[str], covered_items: set[str], floor: int = 35) -> int:
    if not required_items:
        return 100
    ratio = len([item for item in required_items if item in covered_items]) / len(required_items)
    return max(floor, min(100, round(ratio * 100)))


def gate_status(score: int, critical_findings: int = 0) -> GateStatus:
    if critical_findings:
        return GateStatus.FAIL
    if score >= 80:
        return GateStatus.PASS
    if score >= 60:
        return GateStatus.NEEDS_HUMAN_REVIEW
    return GateStatus.FAIL
