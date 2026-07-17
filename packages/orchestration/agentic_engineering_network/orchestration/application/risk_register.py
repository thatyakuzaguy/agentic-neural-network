from __future__ import annotations

from dataclasses import asdict, dataclass


RISK_CATEGORIES = [
    "product",
    "market",
    "technical",
    "security",
    "legal",
    "compliance",
    "operational",
    "financial",
]


@dataclass(frozen=True)
class RiskItem:
    id: str
    risk_title: str
    category: str
    severity: str
    likelihood: str
    owner: str
    mitigation: str
    status: str
    accepted_by: str
    review_date: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_risk_register() -> list[dict[str, object]]:
    risks = [
        RiskItem("risk_product_fit", "Unvalidated product-market fit", "market", "high", "medium", "Product owner", "Complete customer discovery and pilot feedback.", "open", "", "2026-07-05"),
        RiskItem("risk_tenant_isolation", "Tenant isolation defect", "security", "critical", "low", "Security owner", "Run RBAC/tenant test matrix and security review.", "open", "", "2026-07-05"),
        RiskItem("risk_legal_claims", "Unsupported compliance claim", "legal", "critical", "medium", "Legal owner", "Qualified counsel reviews all policies and claims.", "open", "", "2026-07-05"),
        RiskItem("risk_cost_model", "Unclear infrastructure cost model", "financial", "medium", "medium", "Release owner", "Estimate cloud, model, database, and support costs.", "open", "", "2026-07-05"),
        RiskItem("risk_operability", "Insufficient runbooks for production incidents", "operational", "high", "medium", "DevOps owner", "Create incident, backup, restore, and rollback runbooks.", "open", "", "2026-07-05"),
    ]
    return [risk.to_dict() for risk in risks]


def unresolved_critical_count(risks: list[dict[str, object]]) -> int:
    return len(
        [
            risk
            for risk in risks
            if str(risk.get("severity", "")).lower() == "critical"
            and str(risk.get("status", "")).lower() not in {"resolved", "accepted"}
        ]
    )
