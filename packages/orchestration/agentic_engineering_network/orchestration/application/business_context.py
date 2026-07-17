from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agentic_engineering_network.orchestration.application.confidence import (
    ConfidenceLevel,
    confidence_from_evidence,
)


CRITICAL_CONTEXT_FIELDS = [
    "industry",
    "target_customer",
    "geography",
    "revenue_model",
    "timeline",
    "compliance_needs",
]


@dataclass(frozen=True)
class BusinessContext:
    industry: str = ""
    target_customer: str = ""
    geography: str = ""
    revenue_model: str = ""
    budget: str = ""
    timeline: str = ""
    risk_tolerance: str = ""
    compliance_needs: str = ""
    operational_constraints: str = ""
    existing_tools: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BusinessContextAssessment:
    context: BusinessContext
    confidence: ConfidenceLevel
    completed_fields: list[str]
    missing_context: list[str]
    critical_missing: list[str]
    approval_blocked: bool
    evidence_used: list[str]
    assumptions: list[str]
    required_human_validation: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "context": self.context.to_dict(),
            "confidence": self.confidence.value,
        }


def assess_business_context(payload: dict[str, object]) -> BusinessContextAssessment:
    context = BusinessContext(
        industry=str(payload.get("industry", "") or "").strip(),
        target_customer=str(payload.get("target_customer", "") or "").strip(),
        geography=str(payload.get("geography", "") or "").strip(),
        revenue_model=str(payload.get("revenue_model", "") or "").strip(),
        budget=str(payload.get("budget", "") or "").strip(),
        timeline=str(payload.get("timeline", "") or "").strip(),
        risk_tolerance=str(payload.get("risk_tolerance", "") or "").strip(),
        compliance_needs=str(payload.get("compliance_needs", "") or "").strip(),
        operational_constraints=str(payload.get("operational_constraints", "") or "").strip(),
        existing_tools=[str(item).strip() for item in payload.get("existing_tools", []) if str(item).strip()]
        if isinstance(payload.get("existing_tools", []), list)
        else [],
        competitors=[str(item).strip() for item in payload.get("competitors", []) if str(item).strip()]
        if isinstance(payload.get("competitors", []), list)
        else [],
    )
    context_dict = context.to_dict()
    completed = [
        key
        for key, value in context_dict.items()
        if value and (not isinstance(value, list) or len(value) > 0)
    ]
    missing = [key for key in context_dict if key not in completed]
    critical_missing = [key for key in CRITICAL_CONTEXT_FIELDS if not context_dict.get(key)]
    confidence = confidence_from_evidence(len(completed), len(critical_missing))
    return BusinessContextAssessment(
        context=context,
        confidence=confidence,
        completed_fields=completed,
        missing_context=missing,
        critical_missing=critical_missing,
        approval_blocked=bool(critical_missing),
        evidence_used=completed,
        assumptions=["Business context is user-supplied until external evidence is attached."],
        required_human_validation=[
            "Product owner must confirm ICP, geography, revenue model, and timeline.",
            "Legal/compliance owner must confirm compliance needs for selected jurisdictions.",
        ],
    )
