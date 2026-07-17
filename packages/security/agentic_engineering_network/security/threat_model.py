from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.orchestration.domain.quality import (
    Finding,
    SeniorGateResult,
    gate_status,
)


@dataclass(frozen=True)
class ThreatModel:
    stride: dict[str, list[str]]
    dependency_checks: list[str]
    auth_review: list[str]
    rbac_review: list[str]
    api_abuse_review: list[str]
    input_validation_review: list[str]
    rate_limit_review: list[str]
    gate: SeniorGateResult

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "gate": self.gate.to_dict()}


def build_threat_model() -> ThreatModel:
    gate = SeniorGateResult(
        "Security gate",
        gate_status(78, 0),
        78,
        [
            Finding(
                "medium",
                "security",
                "Security review is strong for local scaffolds but still requires live dependency scanning and auth policy review before production.",
                "Run CI security scans and review tenant/RBAC policies against the real domain.",
            )
        ],
        ["Incorrect tenant isolation can expose customer data.", "Webhook replay can mutate billing state."],
        ["Run secret scan and dependency audit in CI.", "Review generated RBAC matrix before release."],
        ["Add DAST scanning after a staging URL exists.", "Add abuse-case tests for high-volume API paths."],
        ["A senior security engineer should review threat model evidence for production deployments."],
    )
    return ThreatModel(
        stride={
            "spoofing": ["API token/session review", "webhook signature verification"],
            "tampering": ["immutable audit log checks", "migration review"],
            "repudiation": ["actor, tenant, timestamp, and request metadata in audit events"],
            "information_disclosure": ["tenant isolation", "secret scanning", "safe error messages"],
            "denial_of_service": ["rate limiting", "bounded correction loops", "Docker resource awareness"],
            "elevation_of_privilege": ["RBAC matrix", "admin-token checks", "approval gates"],
        },
        dependency_checks=["pip-audit", "npm audit", "container base image review", "license review"],
        auth_review=["token presence", "session expiry plan", "admin operation separation", "MFA for production admins"],
        rbac_review=["role-permission matrix", "tenant membership enforcement", "deny-by-default policies"],
        api_abuse_review=["rate limit by client", "payload size limits", "idempotency for billing/webhooks"],
        input_validation_review=["Pydantic schemas", "path containment", "workspace drive restrictions"],
        rate_limit_review=["AEN_RATE_LIMIT_REQUESTS_PER_MINUTE", "429 response checks", "per-client bucket"],
        gate=gate,
    )
