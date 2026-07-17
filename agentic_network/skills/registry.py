"""Skill registry and manifest loading."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from agentic_network.skills.models import PermissionDecision, Skill, SkillPermission


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_SKILLS_ROOT = REPO_ROOT / "agentic_network" / "skills_builtin"
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


class SkillRegistry:
    """In-memory registry for installed skills."""

    def __init__(self, builtin_root: str | Path | None = None) -> None:
        self.builtin_root = Path(builtin_root or BUILTIN_SKILLS_ROOT).resolve()
        self._skills: dict[str, Skill] = {}
        self.load_builtin_skills()

    def register_skill(self, manifest_path: str | Path) -> Skill:
        """Register one skill manifest."""

        path = _resolve_manifest_path(manifest_path)
        skill = _skill_from_manifest(path)
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill
        return skill

    def unregister_skill(self, name: str) -> None:
        """Remove a skill from the registry."""

        self._skills.pop(name, None)

    def list_skills(self) -> list[Skill]:
        """Return installed skills sorted by name."""

        return [self._skills[name] for name in sorted(self._skills)]

    def get_skill(self, name: str) -> Skill | None:
        """Return a skill by name."""

        return self._skills.get(name)

    def enable_skill(self, name: str) -> Skill:
        """Enable a registered skill."""

        skill = self._require_skill(name)
        updated = replace(skill, enabled=True)
        self._skills[name] = updated
        return updated

    def disable_skill(self, name: str) -> Skill:
        """Disable a registered skill."""

        skill = self._require_skill(name)
        updated = replace(skill, enabled=False)
        self._skills[name] = updated
        return updated

    def load_builtin_skills(self) -> None:
        """Load all builtin manifests without executing them."""

        if not self.builtin_root.is_dir():
            return
        for manifest in sorted(self.builtin_root.glob("*/manifest.yaml")):
            skill = _skill_from_manifest(manifest)
            self._skills[skill.name] = skill

    def _require_skill(self, name: str) -> Skill:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(f"Skill not registered: {name}")
        return skill


def _resolve_manifest_path(manifest_path: str | Path) -> Path:
    raw = str(manifest_path)
    if any(part == ".." for part in raw.replace("\\", "/").split("/")):
        raise ValueError("Path traversal is not allowed for skill manifests.")
    path = Path(manifest_path).resolve()
    if _has_protected_part(path):
        raise ValueError("Protected paths cannot be used as skill manifests.")
    if path.name != "manifest.yaml" or not path.is_file():
        raise ValueError("Skill manifest must be a manifest.yaml file.")
    return path


def _skill_from_manifest(path: Path) -> Skill:
    payload = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    required = ["name", "version", "description", "enabled", "requires_user_approval", "permissions"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Invalid skill manifest missing fields: {', '.join(missing)}")
    if not isinstance(payload["permissions"], dict):
        raise ValueError("Invalid skill manifest: permissions must be a mapping.")
    name = _safe_name(str(payload["name"]))
    permissions: dict[str, PermissionDecision] = {}
    for key, value in payload["permissions"].items():
        permission = str(key).strip()
        if permission not in {item.value for item in SkillPermission}:
            raise ValueError(f"Invalid skill permission: {permission}")
        permissions[permission] = PermissionDecision(str(value).strip())
    return Skill(
        name=name,
        version=str(payload["version"]).strip(),
        description=str(payload["description"]).strip(),
        enabled=_bool_value(payload["enabled"]),
        requires_user_approval=_bool_value(payload["requires_user_approval"]),
        permissions=permissions,
        audit_enabled=_bool_value(payload.get("audit_enabled", True)),
        manifest_path=str(path),
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current_map: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith(" ") and current_map:
            key, value = _split_key_value(raw_line.strip())
            payload[current_map][key] = _coerce_scalar(value)
            continue
        key, value = _split_key_value(raw_line.strip())
        if value == "":
            payload[key] = {}
            current_map = key
        else:
            payload[key] = _coerce_scalar(value)
            current_map = None
    return payload


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Invalid manifest line: {line}")
    key, value = line.split(":", 1)
    key = key.strip()
    if not key:
        raise ValueError("Invalid manifest line with empty key.")
    return key, value.strip().strip('"').strip("'")


def _coerce_scalar(value: str) -> object:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _safe_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or not all(char.isalnum() or char in {"_", "-"} for char in cleaned):
        raise ValueError("Invalid skill name.")
    return cleaned


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)
