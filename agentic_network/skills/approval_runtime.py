"""Approval runtime for skill permission requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.skills.audit import SkillAuditLogger
from agentic_network.skills.models import PermissionDecision, PermissionRequestResult
from agentic_network.skills.permission_store import SkillPermissionStore
from agentic_network.skills.registry import SkillRegistry


@dataclass(frozen=True)
class SkillPermissionApprovalResult:
    """Resolved skill permission approval result."""

    allowed: bool
    decision: PermissionDecision
    persistent: bool
    reason: str
    timestamp: str
    skill_name: str
    permission: str
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        return payload


def request_skill_permission(
    skill_name: str,
    permission: str,
    reason: str,
    *,
    registry: SkillRegistry | None = None,
    store: SkillPermissionStore | None = None,
    audit_logger: SkillAuditLogger | None = None,
) -> SkillPermissionApprovalResult:
    """Resolve a skill permission request without executing the skill."""

    resolved_registry = registry or SkillRegistry()
    resolved_store = store or SkillPermissionStore()
    resolved_audit = audit_logger or SkillAuditLogger()
    errors: list[str] = []
    skill = resolved_registry.get_skill(skill_name)
    if skill is None:
        decision = PermissionDecision.DENY
        errors.append("skill_not_registered")
    elif not skill.enabled:
        decision = PermissionDecision.DENY
        errors.append("skill_disabled")
    else:
        decision = resolved_store.get_permission(skill_name, permission)
    allowed = decision in {
        PermissionDecision.ALLOW,
        PermissionDecision.ALLOW_ONCE,
        PermissionDecision.ALLOW_ALWAYS,
    }
    persistent = decision in {PermissionDecision.ALLOW_ALWAYS, PermissionDecision.DENY_ALWAYS}
    if decision in {PermissionDecision.ALLOW_ONCE, PermissionDecision.DENY_ONCE}:
        resolved_store.set_permission(skill_name, permission, PermissionDecision.ASK_ALWAYS)
    request_result = PermissionRequestResult(
        skill_name=skill_name,
        permission=permission,
        reason=reason,
        decision=decision,
        errors=errors,
        persistent=persistent,
    )
    resolved_audit.log_permission_request(
        request_result,
        success=allowed,
        user_action=decision.value,
    )
    return SkillPermissionApprovalResult(
        allowed=allowed,
        decision=decision,
        persistent=persistent,
        reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
        skill_name=skill_name,
        permission=permission,
        errors=errors,
    )


def set_skill_permission(
    skill_name: str,
    permission: str,
    decision: PermissionDecision | str,
    *,
    store_path: str | Path | None = None,
) -> None:
    """Persist a desktop-selected skill permission decision."""

    SkillPermissionStore(store_path).set_permission(skill_name, permission, decision)


def reset_skill_permission(
    skill_name: str,
    permission: str,
    *,
    store_path: str | Path | None = None,
) -> None:
    """Reset a skill permission to ASK_ALWAYS by removing its override."""

    SkillPermissionStore(store_path).remove_permission(skill_name, permission)
