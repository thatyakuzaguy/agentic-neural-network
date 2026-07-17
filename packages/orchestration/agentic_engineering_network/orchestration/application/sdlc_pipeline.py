from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SdlcPhase:
    name: str
    inputs: list[str]
    outputs: list[str]
    validation_checks: list[str]
    failure_criteria: list[str]
    approval_gates: list[str]
    retry_strategy: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_senior_sdlc_pipeline() -> list[dict[str, object]]:
    phases = [
        SdlcPhase("intake", ["raw idea", "workspace directory", "approval mode"], ["run record"], ["path is allowed", "idea is non-empty"], ["unsafe path", "empty idea"], ["workspace gate"], "Ask for a narrower idea only when category is missing."),
        SdlcPhase("discovery", ["run record"], ["product discovery report"], ["ICP exists", "value proposition exists", "risks listed"], ["no buyer/user", "no problem statement"], ["product gate"], "Return clarifying questions and block weak product plans."),
        SdlcPhase("specification", ["discovery report"], ["requirements quality report"], ["ambiguity scan", "NFR coverage", "acceptance criteria"], ["missing critical NFR", "unbounded scope"], ["requirements gate"], "Refine requirements and regenerate acceptance criteria."),
        SdlcPhase("architecture", ["requirements report"], ["architecture decision record", "API contracts"], ["bounded contexts", "data ownership", "deployment topology"], ["missing tenancy boundary", "no migration plan"], ["architecture gate"], "Revise contracts before code generation."),
        SdlcPhase("planning", ["architecture"], ["task graph", "approval plan"], ["dependencies", "risk order", "test plan"], ["missing release path"], ["planning gate"], "Reorder tasks by risk and unblockers."),
        SdlcPhase("implementation", ["task graph"], ["generated diffs"], ["typed code", "validation", "observability"], ["secret in source", "untyped API boundary"], ["file approval gates"], "Apply deterministic fixes, then provider diffs."),
        SdlcPhase("code review", ["generated diffs"], ["review findings"], ["maintainability", "SOLID boundaries", "contract consistency"], ["critical code smell", "missing tests"], ["code review gate"], "Request targeted Qwen patch or human review."),
        SdlcPhase("testing", ["implemented project"], ["test report"], ["unit", "integration", "contract", "E2E", "smoke"], ["red critical tests"], ["QA gate"], "Retry only deterministic/flaky tests; fix code for deterministic failures."),
        SdlcPhase("security review", ["implemented project"], ["threat model", "security findings"], ["STRIDE", "secrets", "RBAC", "API abuse", "dependencies"], ["critical vulnerability"], ["security gate"], "Block release until critical findings are fixed."),
        SdlcPhase("documentation", ["reviewed project"], ["docs bundle"], ["setup", "runbook", "limitations", "operational docs"], ["missing setup path"], ["docs gate"], "Regenerate docs from source of truth."),
        SdlcPhase("release readiness", ["docs and test reports"], ["release package"], ["scorecard", "backup", "rollback", "deploy config"], ["critical gate failed"], ["release gate"], "Escalate to human if gates remain below threshold."),
    ]
    return [phase.to_dict() for phase in phases]
