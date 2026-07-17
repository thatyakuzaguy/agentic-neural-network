from __future__ import annotations

from agentic_engineering_network.orchestration.application.human_gates import summarize_human_gates
from agentic_engineering_network.orchestration.application.risk_register import unresolved_critical_count


def evaluate_release_readiness(
    human_gate_decisions: list[dict[str, object]],
    risks: list[dict[str, object]],
    security_checklist_passed: bool,
    legal_reviewed: bool,
    architecture_decisions_exist: bool,
    tests_passed: bool,
    deployment_checklist_passed: bool,
) -> dict[str, object]:
    gates = summarize_human_gates(human_gate_decisions)
    unresolved_critical = unresolved_critical_count(risks)
    blockers: list[str] = []
    if not gates["complete"]:
        blockers.append("required human approvals are incomplete")
    if unresolved_critical:
        blockers.append("critical risks remain unresolved or unaccepted")
    if not security_checklist_passed:
        blockers.append("security checklist has not passed")
    if not legal_reviewed:
        blockers.append("legal/compliance review is not marked complete")
    if not architecture_decisions_exist:
        blockers.append("architecture decision records are missing")
    if not tests_passed:
        blockers.append("tests are not marked passed")
    if not deployment_checklist_passed:
        blockers.append("deployment checklist has not passed")
    return {
        "status": "blocked" if blockers else "ready_for_human_release_decision",
        "blockers": blockers,
        "human_gates": gates,
        "unresolved_critical_risks": unresolved_critical,
        "checks": {
            "security_checklist_passed": security_checklist_passed,
            "legal_reviewed": legal_reviewed,
            "architecture_decisions_exist": architecture_decisions_exist,
            "tests_passed": tests_passed,
            "deployment_checklist_passed": deployment_checklist_passed,
        },
        "responsibility_statement": (
            "This platform can assist at a senior/staff level, but production responsibility remains "
            "with qualified human owners."
        ),
    }
