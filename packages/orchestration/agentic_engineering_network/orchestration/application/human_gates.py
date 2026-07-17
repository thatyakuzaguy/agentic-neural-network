from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


REQUIRED_HUMAN_GATES = [
    "product_owner_approval",
    "senior_architect_approval",
    "security_owner_approval",
    "legal_compliance_approval",
    "release_owner_approval",
]


@dataclass(frozen=True)
class HumanGateDecision:
    gate_id: str
    approver_name: str
    role: str
    timestamp: str
    decision: str
    comments: str
    risk_acceptance: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def empty_human_gates() -> dict[str, object]:
    return {
        "required_gates": REQUIRED_HUMAN_GATES,
        "decisions": [],
        "complete": False,
        "missing_gates": REQUIRED_HUMAN_GATES,
    }


def summarize_human_gates(decisions: list[dict[str, object]]) -> dict[str, object]:
    approved = {
        str(decision.get("gate_id"))
        for decision in decisions
        if str(decision.get("decision", "")).lower() == "approved"
    }
    missing = [gate for gate in REQUIRED_HUMAN_GATES if gate not in approved]
    return {
        "required_gates": REQUIRED_HUMAN_GATES,
        "decisions": decisions,
        "complete": not missing,
        "missing_gates": missing,
    }


def make_human_gate_decision(payload: dict[str, object]) -> HumanGateDecision:
    gate_id = str(payload.get("gate_id", "")).strip()
    if gate_id not in REQUIRED_HUMAN_GATES:
        raise ValueError(f"Unknown human gate: {gate_id}")
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in {"approved", "rejected", "needs_changes"}:
        raise ValueError("decision must be approved, rejected, or needs_changes")
    approver_name = str(payload.get("approver_name", "")).strip()
    role = str(payload.get("role", "")).strip()
    if not approver_name or not role:
        raise ValueError("approver_name and role are required")
    return HumanGateDecision(
        gate_id=gate_id,
        approver_name=approver_name,
        role=role,
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision=decision,
        comments=str(payload.get("comments", "")).strip(),
        risk_acceptance=str(payload.get("risk_acceptance", "")).strip(),
    )
