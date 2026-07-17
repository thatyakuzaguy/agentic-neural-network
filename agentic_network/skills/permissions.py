"""Permission engine for ANN skills."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_network.skills.models import PermissionDecision, PermissionRequestResult
from agentic_network.skills.permission_store import SkillPermissionStore
from agentic_network.skills.registry import SkillRegistry


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ann_skills.json"


class PermissionEngine:
    """Evaluate skill permission requests without UI popups."""

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        config_path: str | Path | None = None,
        permission_store: SkillPermissionStore | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH).resolve()
        self.config = _load_config(self.config_path)
        self.permission_store = permission_store or SkillPermissionStore()

    def request_permission(
        self,
        skill_name: str,
        permission: str,
        reason: str,
    ) -> PermissionRequestResult:
        """Resolve one permission request."""

        skill = self.registry.get_skill(skill_name)
        if skill is None:
            return PermissionRequestResult(
                skill_name=skill_name,
                permission=permission,
                reason=reason,
                decision=PermissionDecision.DENY,
                errors=["skill_not_registered"],
            )
        if not skill.enabled:
            return PermissionRequestResult(
                skill_name=skill_name,
                permission=permission,
                reason=reason,
                decision=PermissionDecision.DENY,
                errors=["skill_disabled"],
            )
        if self.permission_store.has_permission(skill_name, permission):
            decision = self.permission_store.get_permission(skill_name, permission)
            persistent = decision in {PermissionDecision.ALLOW_ALWAYS, PermissionDecision.DENY_ALWAYS}
            if decision in {PermissionDecision.ALLOW_ONCE, PermissionDecision.DENY_ONCE}:
                self.permission_store.set_permission(skill_name, permission, PermissionDecision.ASK_ALWAYS)
            return PermissionRequestResult(
                skill_name=skill_name,
                permission=permission,
                reason=reason,
                decision=decision,
                errors=[],
                persistent=persistent,
            )
        overrides = self.config.get("permissions", {})
        keys = [
            f"{skill_name}.{permission}",
            _legacy_permission_key(skill_name, permission),
            permission,
        ]
        for key in keys:
            value = overrides.get(key)
            if isinstance(value, str):
                return PermissionRequestResult(
                    skill_name=skill_name,
                    permission=permission,
                    reason=reason,
                    decision=PermissionDecision(value),
                    errors=[],
                    persistent=False,
                )
        decision = skill.permissions.get(permission, PermissionDecision.DENY)
        return PermissionRequestResult(
            skill_name=skill_name,
            permission=permission,
            reason=reason,
            decision=decision,
            errors=[],
            persistent=False,
        )


def _load_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"permissions": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ann_skills.json must contain a JSON object.")
    permissions = payload.get("permissions")
    if permissions is None:
        payload["permissions"] = {}
    elif not isinstance(permissions, dict):
        raise ValueError("ann_skills.json permissions must be an object.")
    return payload


def _legacy_permission_key(skill_name: str, permission: str) -> str:
    if skill_name == "internet_search" and permission == "network":
        return "internet.search"
    if skill_name == "github" and permission == "git_read":
        return "github.read_repo"
    if skill_name == "package_registry" and permission == "network":
        return "package_registry.search"
    if skill_name == "documentation" and permission == "network":
        return "documentation.search"
    return f"{skill_name}.{permission}"


def permission_decision_allows(decision: PermissionDecision | str) -> bool:
    """Return whether a permission decision grants execution."""

    return PermissionDecision(str(decision)) in {
        PermissionDecision.ALLOW,
        PermissionDecision.ALLOW_ONCE,
        PermissionDecision.ALLOW_ALWAYS,
    }
