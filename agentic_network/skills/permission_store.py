"""Persistent skill permission decisions."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_network.skills.models import PermissionDecision, SkillPermission


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERMISSION_STORE = REPO_ROOT / "config" / "ann_skill_permissions.json"
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


class SkillPermissionStore:
    """JSON-backed store for skill permission decisions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = _safe_store_path(path or DEFAULT_PERMISSION_STORE)

    def load_permissions(self) -> dict[str, dict[str, str]]:
        return load_permissions(self.path)

    def save_permissions(self, permissions: dict[str, dict[str, str]]) -> None:
        save_permissions(permissions, self.path)

    def set_permission(
        self,
        skill_name: str,
        permission: str,
        decision: PermissionDecision | str,
    ) -> None:
        _validate_skill_name(skill_name)
        _validate_permission(permission)
        resolved = PermissionDecision(str(decision))
        permissions = self.load_permissions()
        permissions.setdefault(skill_name, {})[permission] = resolved.value
        self.save_permissions(permissions)

    def remove_permission(self, skill_name: str, permission: str) -> None:
        _validate_skill_name(skill_name)
        _validate_permission(permission)
        permissions = self.load_permissions()
        if skill_name in permissions:
            permissions[skill_name].pop(permission, None)
            if not permissions[skill_name]:
                permissions.pop(skill_name)
        self.save_permissions(permissions)

    def get_permission(self, skill_name: str, permission: str) -> PermissionDecision:
        _validate_skill_name(skill_name)
        _validate_permission(permission)
        value = self.load_permissions().get(skill_name, {}).get(permission)
        return PermissionDecision(value) if value else PermissionDecision.ASK_ALWAYS

    def has_permission(self, skill_name: str, permission: str) -> bool:
        _validate_skill_name(skill_name)
        _validate_permission(permission)
        return permission in self.load_permissions().get(skill_name, {})


def load_permissions(path: str | Path = DEFAULT_PERMISSION_STORE) -> dict[str, dict[str, str]]:
    """Load permission decisions from disk."""

    resolved = _safe_store_path(path)
    if not resolved.is_file():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ann_skill_permissions.json must contain an object.")
    permissions: dict[str, dict[str, str]] = {}
    for skill_name, skill_permissions in payload.items():
        _validate_skill_name(str(skill_name))
        if not isinstance(skill_permissions, dict):
            raise ValueError("Skill permissions must be objects.")
        permissions[str(skill_name)] = {}
        for permission, decision in skill_permissions.items():
            _validate_permission(str(permission))
            permissions[str(skill_name)][str(permission)] = PermissionDecision(str(decision)).value
    return permissions


def save_permissions(
    permissions: dict[str, dict[str, str]],
    path: str | Path = DEFAULT_PERMISSION_STORE,
) -> None:
    """Persist permission decisions to disk."""

    resolved = _safe_store_path(path)
    normalized: dict[str, dict[str, str]] = {}
    for skill_name, skill_permissions in permissions.items():
        _validate_skill_name(skill_name)
        normalized[skill_name] = {}
        for permission, decision in skill_permissions.items():
            _validate_permission(permission)
            normalized[skill_name][permission] = PermissionDecision(str(decision)).value
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")


def _safe_store_path(path: str | Path) -> Path:
    raw = str(path)
    if any(part == ".." for part in raw.replace("\\", "/").split("/")):
        raise ValueError("Path traversal is not allowed for skill permission store.")
    resolved = Path(path).resolve()
    if _has_protected_part(resolved):
        raise ValueError("Skill permission store cannot be inside a protected path.")
    if resolved.suffix.lower() != ".json":
        raise ValueError("Skill permission store must be a JSON file.")
    return resolved


def _validate_skill_name(name: str) -> None:
    if not name or not all(char.isalnum() or char in {"_", "-"} for char in name):
        raise ValueError("Invalid skill name.")


def _validate_permission(permission: str) -> None:
    if permission not in {item.value for item in SkillPermission}:
        raise ValueError(f"Invalid skill permission: {permission}")


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)
