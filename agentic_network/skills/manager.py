"""High-level manager for ANN skills."""

from __future__ import annotations

import time
from pathlib import Path

from agentic_network.skills.audit import SkillAuditLogger
from agentic_network.skills.executor import SkillExecutionResult, SkillExecutor
from agentic_network.skills.models import PermissionRequestResult, Skill
from agentic_network.skills.permissions import PermissionEngine
from agentic_network.skills.permission_store import SkillPermissionStore
from agentic_network.skills.registry import SkillRegistry


class SkillsManager:
    """Facade over registry, permissions, and audit logging."""

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        permission_engine: PermissionEngine | None = None,
        audit_logger: SkillAuditLogger | None = None,
        permission_store: SkillPermissionStore | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.permission_store = permission_store or SkillPermissionStore()
        self.permission_engine = permission_engine or PermissionEngine(
            self.registry,
            permission_store=self.permission_store,
        )
        self.audit_logger = audit_logger or SkillAuditLogger()
        self.executor = SkillExecutor(
            registry=self.registry,
            store=self.permission_store,
            audit_logger=self.audit_logger,
        )

    def register_skill(self, manifest_path: str | Path) -> Skill:
        return self.registry.register_skill(manifest_path)

    def unregister_skill(self, name: str) -> None:
        self.registry.unregister_skill(name)

    def list_skills(self) -> list[Skill]:
        return self.registry.list_skills()

    def get_skill(self, name: str) -> Skill | None:
        return self.registry.get_skill(name)

    def enable_skill(self, name: str) -> Skill:
        return self.registry.enable_skill(name)

    def disable_skill(self, name: str) -> Skill:
        return self.registry.disable_skill(name)

    def request_permission(
        self,
        skill_name: str,
        permission: str,
        reason: str,
    ) -> PermissionRequestResult:
        started = time.perf_counter()
        result = self.permission_engine.request_permission(skill_name, permission, reason)
        skill = self.registry.get_skill(skill_name)
        if skill is None or skill.audit_enabled:
            self.audit_logger.log_permission_request(result, started_at=started)
        return result

    def set_permission(self, skill_name: str, permission: str, decision: str) -> None:
        self.permission_store.set_permission(skill_name, permission, decision)

    def reset_permission(self, skill_name: str, permission: str) -> None:
        self.permission_store.remove_permission(skill_name, permission)

    def execute_skill(
        self,
        skill_name: str,
        action: str,
        payload: dict[str, object] | None = None,
    ) -> SkillExecutionResult:
        """Execute one sandboxed skill action."""

        return self.executor.execute_skill(skill_name, action, payload)
