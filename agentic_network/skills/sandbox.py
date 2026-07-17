"""Sandbox policy for ANN skill execution.

The v10.2 sandbox is intentionally conservative. It creates an isolated local
workspace for each skill, evaluates explicit stored permissions, and exposes no
network, terminal, package-install, or repository-write capability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from agentic_network.skills.models import PermissionDecision, SkillPermission
from agentic_network.skills.permission_store import SkillPermissionStore
from agentic_network.skills.permissions import permission_decision_allows
from agentic_network.skills.registry import SkillRegistry


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_OUTPUTS_ROOT = REPO_ROOT / "outputs" / "skills"
DEFAULT_CONFIG_ROOT = REPO_ROOT / "config"
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


class SandboxStatus(StrEnum):
    """Sandbox evaluation statuses."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SandboxResult:
    """Result of evaluating a skill execution sandbox."""

    status: SandboxStatus
    skill_name: str
    requested_permissions: list[str]
    granted_permissions: list[str]
    allowed_paths: list[str]
    blocked_paths: list[str]
    network_allowed: bool
    git_allowed: bool
    terminal_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def create_skill_workspace(
    skill_name: str,
    *,
    outputs_root: str | Path | None = None,
) -> Path:
    """Create the isolated writable workspace for one skill."""

    safe_name = safe_skill_name(skill_name)
    root = Path(outputs_root or DEFAULT_SKILL_OUTPUTS_ROOT).resolve()
    if _has_protected_part(root):
        raise ValueError("Skill workspace root cannot be inside a protected path.")
    workspace = (root / safe_name / "workspace").resolve()
    if not _is_relative_to(workspace, root):
        raise ValueError("Skill workspace path escaped the outputs root.")
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "tmp").mkdir(exist_ok=True)
    return workspace


def evaluate_skill_sandbox(
    skill_name: str,
    requested_permissions: list[str],
    *,
    registry: SkillRegistry | None = None,
    store: SkillPermissionStore | None = None,
    outputs_root: str | Path | None = None,
) -> SandboxResult:
    """Evaluate whether a skill action may run inside the local sandbox."""

    resolved_registry = registry or SkillRegistry()
    resolved_store = store or SkillPermissionStore()
    safe_name = safe_skill_name(skill_name)
    workspace = create_skill_workspace(safe_name, outputs_root=outputs_root)
    allowed_paths = [str(workspace), str(DEFAULT_CONFIG_ROOT.resolve())]
    blocked_paths = [
        str(REPO_ROOT),
        str(REPO_ROOT / ".git"),
        str(REPO_ROOT / "models"),
        str(REPO_ROOT / "training"),
        str(REPO_ROOT / "datasets"),
        str(REPO_ROOT / "adapters"),
        str(REPO_ROOT / "memory"),
        str(REPO_ROOT / "knowledge"),
        str(REPO_ROOT / "unsloth_compiled_cache"),
        "C:\\",
        "/mnt/c",
    ]
    invalid_permissions = [item for item in requested_permissions if not _is_known_permission(item)]
    if invalid_permissions:
        return _blocked(
            safe_name,
            requested_permissions,
            [],
            allowed_paths,
            blocked_paths,
            f"Invalid permissions requested: {', '.join(invalid_permissions)}",
        )
    skill = resolved_registry.get_skill(safe_name)
    if skill is None:
        return _blocked(safe_name, requested_permissions, [], allowed_paths, blocked_paths, "Skill is not registered.")
    if not skill.enabled:
        return _blocked(safe_name, requested_permissions, [], allowed_paths, blocked_paths, "Skill is disabled.")

    granted: list[str] = []
    denied: list[str] = []
    blocked: list[str] = []
    for permission in requested_permissions:
        decision = resolved_store.get_permission(safe_name, permission)
        if permission_decision_allows(decision):
            granted.append(permission)
            if decision == PermissionDecision.ALLOW_ONCE:
                resolved_store.set_permission(safe_name, permission, PermissionDecision.ASK_ALWAYS)
        elif decision in {PermissionDecision.DENY, PermissionDecision.DENY_ONCE, PermissionDecision.DENY_ALWAYS}:
            denied.append(permission)
            if decision == PermissionDecision.DENY_ONCE:
                resolved_store.set_permission(safe_name, permission, PermissionDecision.ASK_ALWAYS)
        else:
            blocked.append(permission)

    network_allowed = SkillPermission.NETWORK.value in granted
    git_allowed = any(permission in granted for permission in {SkillPermission.GIT_READ.value, SkillPermission.GIT_WRITE.value})
    terminal_allowed = SkillPermission.TERMINAL_EXECUTE.value in granted
    if terminal_allowed:
        return _blocked(
            safe_name,
            requested_permissions,
            granted,
            allowed_paths,
            blocked_paths,
            "Terminal execution is not available in v10.2 sandbox.",
        )
    if denied:
        return SandboxResult(
            status=SandboxStatus.DENIED,
            skill_name=safe_name,
            requested_permissions=requested_permissions,
            granted_permissions=granted,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            network_allowed=network_allowed,
            git_allowed=git_allowed,
            terminal_allowed=False,
            reason=f"Permission denied: {', '.join(denied)}",
        )
    if blocked:
        return _blocked(
            safe_name,
            requested_permissions,
            granted,
            allowed_paths,
            blocked_paths,
            f"Permission requires explicit approval: {', '.join(blocked)}",
        )
    return SandboxResult(
        status=SandboxStatus.ALLOWED,
        skill_name=safe_name,
        requested_permissions=requested_permissions,
        granted_permissions=granted,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        network_allowed=network_allowed,
        git_allowed=git_allowed,
        terminal_allowed=False,
        reason="Sandbox permissions granted for local permission_test only.",
    )


def validate_workspace_path(path: str | Path, workspace: str | Path) -> Path:
    """Validate a skill write path against its isolated workspace."""

    resolved = Path(path).resolve()
    resolved_workspace = Path(workspace).resolve()
    if not _is_relative_to(resolved, resolved_workspace):
        if _is_blocked_windows_root(resolved) or _has_protected_part(resolved):
            raise ValueError("Skill path points to a protected location.")
        raise ValueError("Skill writes are restricted to the skill workspace.")
    relative = resolved.relative_to(resolved_workspace)
    if _has_protected_part(relative):
        raise ValueError("Skill path points to a protected location.")
    return resolved


def safe_skill_name(skill_name: str) -> str:
    """Normalize and validate a skill name for filesystem use."""

    if not skill_name or not all(char.isalnum() or char in {"_", "-"} for char in skill_name):
        raise ValueError("Invalid skill name.")
    return skill_name


def _blocked(
    skill_name: str,
    requested_permissions: list[str],
    granted_permissions: list[str],
    allowed_paths: list[str],
    blocked_paths: list[str],
    reason: str,
) -> SandboxResult:
    return SandboxResult(
        status=SandboxStatus.BLOCKED,
        skill_name=skill_name,
        requested_permissions=requested_permissions,
        granted_permissions=granted_permissions,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        network_allowed=SkillPermission.NETWORK.value in granted_permissions,
        git_allowed=any(
            permission in granted_permissions for permission in {SkillPermission.GIT_READ.value, SkillPermission.GIT_WRITE.value}
        ),
        terminal_allowed=False,
        reason=reason,
    )


def _is_known_permission(permission: str) -> bool:
    return permission in {item.value for item in SkillPermission}


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_blocked_windows_root(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    anchor = path.anchor.lower().replace("\\", "/")
    return anchor.startswith("c:/") or normalized == "/mnt/c" or normalized.startswith("/mnt/c/")
