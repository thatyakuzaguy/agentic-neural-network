"""Typed models for ANN skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class PermissionDecision(StrEnum):
    """Supported skill permission decisions."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    ASK_ALWAYS = "ASK_ALWAYS"
    ALLOW_ONCE = "ALLOW_ONCE"
    ALLOW_ALWAYS = "ALLOW_ALWAYS"
    DENY_ONCE = "DENY_ONCE"
    DENY_ALWAYS = "DENY_ALWAYS"


class SkillPermission(StrEnum):
    """Known permission categories for skills."""

    NETWORK = "network"
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    GIT_READ = "git_read"
    GIT_WRITE = "git_write"
    TERMINAL_EXECUTE = "terminal_execute"


@dataclass(frozen=True)
class Skill:
    """Installed skill manifest."""

    name: str
    version: str
    description: str
    enabled: bool
    requires_user_approval: bool
    permissions: dict[str, PermissionDecision]
    audit_enabled: bool = True
    manifest_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["permissions"] = {key: value.value for key, value in self.permissions.items()}
        return payload


@dataclass(frozen=True)
class PermissionRequestResult:
    """Result of evaluating a skill permission request."""

    skill_name: str
    permission: str
    reason: str
    decision: PermissionDecision
    errors: list[str] = field(default_factory=list)
    persistent: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        return payload


@dataclass(frozen=True)
class SkillAuditRecord:
    """Audit record for a skill permission or future execution event."""

    timestamp: str
    skill: str
    requested_permission: str
    decision: str
    duration: float
    success: bool
    errors: list[str]
    reason: str
    user_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
