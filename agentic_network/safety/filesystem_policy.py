"""Configurable filesystem safety policy for ANN runtime stages."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_PROJECT_ROOT = "/mnt/d/AgenticEngineeringNetwork"
DEFAULT_ALLOWED_ROOTS = ("/mnt/d", "/mnt/e")
DEFAULT_BLOCKED_ROOTS = ("/mnt/c", "C:\\")
DEFAULT_PROTECTED_PATHS = (
    ".git",
    "outputs",
    "knowledge",
    "training/datasets",
    "training/adapters",
    "/mnt/d/Models",
    "/mnt/e/Models",
)
MODEL_EXTENSIONS = {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx"}
WINDOWS_DRIVE_PATH = re.compile(r"^(?P<drive>[A-Za-z]):[\\/]*(?P<rest>.*)$")
WSL_DRIVE_PATH = re.compile(r"^/mnt/(?P<drive>[a-zA-Z])(?:/(?P<rest>.*))?$")


@dataclass(frozen=True)
class FilesystemPolicy:
    """Resolved filesystem policy used by path-sensitive ANN stages."""

    project_root: Path
    allowed_roots: tuple[Path, ...]
    blocked_roots: tuple[Path, ...]
    protected_paths: tuple[Path, ...]
    allow_external_paths: bool = False
    require_explicit_external_path_approval: bool = True
    external_path_approved: bool = False

    def normalize_path(self, path: str | Path) -> Path:
        """Normalize relative, WSL, and Windows-style paths without touching the file."""

        text = str(path).strip().strip('"').strip("'")
        if not text:
            return self.project_root
        windows_match = WINDOWS_DRIVE_PATH.match(text)
        if windows_match:
            drive = windows_match.group("drive").lower()
            rest = windows_match.group("rest").replace("\\", "/").strip("/")
            return Path(f"{drive.upper()}:/{rest}").resolve()
        wsl_match = WSL_DRIVE_PATH.match(text.replace("\\", "/"))
        if wsl_match:
            return Path(text)
        candidate = Path(text)
        if text.startswith("/"):
            return candidate
        if not candidate.is_absolute():
            project_key = _canonical_path_key(self.project_root)
            if _is_wsl_like_path(self.project_root) or str(self.project_root).replace("\\", "/").startswith("/tmp/"):
                relative_text = text.replace("\\", "/").strip("/")
                return Path(f"{project_key}/{relative_text}")
            candidate = self.project_root / candidate
        return candidate.resolve()

    def is_path_allowed(self, path: str | Path) -> bool:
        if self._has_path_traversal(path) or self.is_path_blocked(path):
            return False
        normalized = self.normalize_path(path)
        if any(_is_relative_to(normalized, root) for root in self.allowed_roots):
            return True
        if not self.allow_external_paths:
            return False
        if self.require_explicit_external_path_approval and not self.external_path_approved:
            return False
        return True

    def is_path_blocked(self, path: str | Path) -> bool:
        normalized = self.normalize_path(path)
        for blocked_root in self.blocked_roots:
            if not _is_relative_to(normalized, blocked_root):
                continue
            if self._is_explicitly_allowed_inside_blocked_root(normalized, blocked_root):
                continue
            return True
        return False

    def is_path_protected(self, path: str | Path) -> bool:
        normalized = self.normalize_path(path)
        if normalized.suffix.lower() in MODEL_EXTENSIONS:
            return True
        return any(_is_relative_to(normalized, protected) for protected in self.protected_paths)

    def validate_read_path(self, path: str | Path) -> list[str]:
        errors = self._base_path_errors(path)
        return _dedupe(errors)

    def validate_write_path(self, path: str | Path) -> list[str]:
        errors = self._base_path_errors(path)
        if self.is_path_protected(path):
            errors.append(f"protected_path_modified:{self._display_path(path)}")
        return _dedupe(errors)

    def validate_patch_target(self, path: str | Path) -> list[str]:
        return self.validate_write_path(path)

    def explain_path_rejection(self, path: str | Path) -> str:
        errors = self.validate_write_path(path)
        return ";".join(errors) if errors else ""

    def _base_path_errors(self, path: str | Path) -> list[str]:
        errors: list[str] = []
        if self._has_path_traversal(path):
            errors.append(f"path_traversal_present:{self._display_path(path)}")
        if self.is_path_blocked(path):
            errors.append("forbidden_c_path_present" if _is_c_path(path) else f"blocked_path:{self._display_path(path)}")
        if not self.is_path_allowed(path):
            normalized = self.normalize_path(path)
            if not any(_is_relative_to(normalized, root) for root in self.allowed_roots):
                if self.allow_external_paths and self.require_explicit_external_path_approval and not self.external_path_approved:
                    errors.append(f"external_path_approval_required:{self._display_path(path)}")
                else:
                    errors.append(f"path_outside_allowed_roots:{self._display_path(path)}")
        return errors

    def _has_path_traversal(self, path: str | Path) -> bool:
        text = str(path).replace("\\", "/")
        return any(part == ".." for part in text.split("/"))

    def _display_path(self, path: str | Path) -> str:
        try:
            normalized = self.normalize_path(path)
            try:
                return normalized.relative_to(self.project_root).as_posix()
            except ValueError:
                return normalized.as_posix()
        except OSError:
            return str(path)

    def _is_explicitly_allowed_inside_blocked_root(self, normalized: Path, blocked_root: Path) -> bool:
        for allowed_root in self.allowed_roots:
            if not _is_relative_to(normalized, allowed_root):
                continue
            if _is_relative_to(allowed_root, blocked_root) and not _is_relative_to(blocked_root, allowed_root):
                return True
        return False


def load_filesystem_policy(
    *,
    project_root: str | Path | None = None,
    allowed_roots: Iterable[str | Path] | None = None,
    blocked_roots: Iterable[str | Path] | None = None,
    protected_paths: Iterable[str | Path] | None = None,
    allow_external_paths: bool | None = None,
    require_explicit_external_path_approval: bool | None = None,
    external_path_approved: bool | None = None,
) -> FilesystemPolicy:
    """Load filesystem policy from explicit values and ANN_* environment variables."""

    root_text = str(project_root or os.getenv("ANN_PROJECT_ROOT") or DEFAULT_PROJECT_ROOT)
    root = _normalize_config_path(root_text)
    allow_external = _bool_value(
        os.getenv("ANN_ALLOW_EXTERNAL_PATHS"),
        DEFAULT_FALSE if allow_external_paths is None else allow_external_paths,
    )
    require_approval = _bool_value(
        os.getenv("ANN_REQUIRE_EXTERNAL_PATH_APPROVAL"),
        True if require_explicit_external_path_approval is None else require_explicit_external_path_approval,
    )
    approved_external = _bool_value(
        os.getenv("ANN_EXTERNAL_PATH_APPROVED"),
        False if external_path_approved is None else external_path_approved,
    )
    allowed_values = _configured_values(
        explicit=allowed_roots,
        env_name="ANN_ALLOWED_ROOTS",
        default=DEFAULT_ALLOWED_ROOTS,
    )
    blocked_values = _configured_values(
        explicit=blocked_roots,
        env_name="ANN_BLOCKED_ROOTS",
        default=DEFAULT_BLOCKED_ROOTS,
    )
    protected_values = _configured_values(
        explicit=protected_paths,
        env_name="ANN_PROTECTED_PATHS",
        default=DEFAULT_PROTECTED_PATHS,
    )
    resolved_allowed_roots = tuple(_normalize_config_path(value) for value in allowed_values)
    if not any(_is_relative_to(root, allowed_root) for allowed_root in resolved_allowed_roots):
        resolved_allowed_roots = (*resolved_allowed_roots, root)
    return FilesystemPolicy(
        project_root=root,
        allowed_roots=resolved_allowed_roots,
        blocked_roots=tuple(_normalize_config_path(value) for value in blocked_values),
        protected_paths=tuple(
            _normalize_config_path(value, project_root=root) for value in protected_values
        ),
        allow_external_paths=allow_external,
        require_explicit_external_path_approval=require_approval,
        external_path_approved=approved_external,
    )


def normalize_path(path: str | Path) -> Path:
    return load_filesystem_policy().normalize_path(path)


def is_path_allowed(path: str | Path) -> bool:
    return load_filesystem_policy().is_path_allowed(path)


def is_path_blocked(path: str | Path) -> bool:
    return load_filesystem_policy().is_path_blocked(path)


def is_path_protected(path: str | Path) -> bool:
    return load_filesystem_policy().is_path_protected(path)


def validate_read_path(path: str | Path) -> list[str]:
    return load_filesystem_policy().validate_read_path(path)


def validate_write_path(path: str | Path) -> list[str]:
    return load_filesystem_policy().validate_write_path(path)


def validate_patch_target(path: str | Path) -> list[str]:
    return load_filesystem_policy().validate_patch_target(path)


def explain_path_rejection(path: str | Path) -> str:
    return load_filesystem_policy().explain_path_rejection(path)


DEFAULT_FALSE = False


def _configured_values(
    *,
    explicit: Iterable[str | Path] | None,
    env_name: str,
    default: tuple[str, ...],
) -> tuple[str | Path, ...]:
    if explicit is not None:
        return tuple(explicit)
    value = os.getenv(env_name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _normalize_config_path(path: str | Path, *, project_root: Path | None = None) -> Path:
    text = str(path).strip().strip('"').strip("'")
    windows_match = WINDOWS_DRIVE_PATH.match(text)
    if windows_match:
        drive = windows_match.group("drive").lower()
        rest = windows_match.group("rest").replace("\\", "/").strip("/")
        return Path(f"{drive.upper()}:/{rest}").resolve()
    wsl_match = WSL_DRIVE_PATH.match(text.replace("\\", "/"))
    if wsl_match:
        return Path(text)
    candidate = Path(text)
    if text.startswith("/"):
        return candidate
    if not candidate.is_absolute() and project_root is not None:
        project_key = _canonical_path_key(project_root)
        if _is_wsl_like_path(project_root) or str(project_root).replace("\\", "/").startswith("/tmp/"):
            relative_text = text.replace("\\", "/").strip("/")
            return Path(f"{project_key}/{relative_text}")
        candidate = project_root / candidate
    return candidate.resolve()


def _bool_value(value: str | bool | None, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_relative_to(path: Path, parent: Path) -> bool:
    path_key = _canonical_path_key(path)
    parent_key = _canonical_path_key(parent)
    return path_key == parent_key or path_key.startswith(parent_key.rstrip("/") + "/")


def _is_c_path(path: str | Path) -> bool:
    text = str(path).strip().lower().replace("\\", "/")
    return text.startswith("/mnt/c") or text.startswith("c:/")


def _canonical_path_key(path: str | Path) -> str:
    text = str(path).strip().strip('"').strip("'").replace("\\", "/")
    windows_match = WINDOWS_DRIVE_PATH.match(text)
    if windows_match:
        drive = windows_match.group("drive").lower()
        rest = windows_match.group("rest").strip("/")
        return f"/mnt/{drive}/{rest}".rstrip("/").lower()
    wsl_match = WSL_DRIVE_PATH.match(text)
    if wsl_match:
        drive = wsl_match.group("drive").lower()
        rest = (wsl_match.group("rest") or "").strip("/")
        return f"/mnt/{drive}/{rest}".rstrip("/").lower()
    try:
        resolved = Path(text).resolve()
    except OSError:
        resolved = Path(text)
    normalized = str(resolved).replace("\\", "/")
    windows_match = WINDOWS_DRIVE_PATH.match(normalized)
    if windows_match:
        drive = windows_match.group("drive").lower()
        rest = windows_match.group("rest").strip("/")
        return f"/mnt/{drive}/{rest}".rstrip("/").lower()
    return normalized.rstrip("/").lower()


def _is_wsl_like_path(path: str | Path) -> bool:
    text = str(path).strip().strip('"').strip("'").replace("\\", "/")
    return bool(WSL_DRIVE_PATH.match(text))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
