from __future__ import annotations

from agentic_engineering_network.orchestration.application.intelligence import RESPONSIBILITY_STATEMENT


def build_approval_packets() -> dict[str, object]:
    owners = {
        "Product Owner": ["market evidence", "ICP", "pricing validation", "GTM risks"],
        "Architect": ["ADRs", "tradeoffs", "alternatives", "failure modes", "cost assumptions"],
        "Security Owner": ["STRIDE", "OWASP", "secret scan", "dependency scan", "residual risks"],
        "Compliance Owner": ["policy drafts", "jurisdiction review", "evidence checklist", "gap analysis"],
        "Release Owner": ["tests", "deployment checklist", "rollback", "monitoring", "incident plan"],
    }
    return {
        "responsibility_statement": RESPONSIBILITY_STATEMENT,
        "packets": [
            {
                "owner": owner,
                "executive_summary": f"{owner} decision packet prepared for rapid approve/reject.",
                "findings": [f"Review {item}." for item in items],
                "risks": ["Residual risk must be accepted by the named owner."],
                "evidence": items,
                "recommendations": ["Approve only when evidence is sufficient.", "Reject or request changes when evidence is missing."],
                "required_actions": ["Record approver name, role, comments, decision, and risk acceptance."],
            }
            for owner, items in owners.items()
        ],
    }
