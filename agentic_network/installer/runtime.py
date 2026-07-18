"""Installer planning/runtime for the self-contained ANN Windows desktop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_network.installer.paths import (
    BLOCKED_PARTS,
    contains_traversal,
    get_default_install_root,
    is_c_drive,
    is_excluded_path,
    is_relative_to,
    normalize_install_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_DIRS = (
    "agentic_network",
    "apps",
    "packages",
    "scripts",
    "desktop",
    "installer",
    "data",
    "projects",
    "outputs",
    "logs",
    "models",
    "adapters",
    "config",
    "runtime",
)
TOP_LEVEL_INCLUDE = {
    "agentic_network",
    "apps",
    "packages",
    "scripts",
    "config",
    "installer",
    "pyproject.toml",
    "package.json",
    "README.md",
    "start.ps1",
    "stop.ps1",
}


@dataclass(frozen=True)
class InstallPlan:
    """Plan for installing ANN without copying protected/heavy areas."""

    source_root: str
    install_root: str
    files_to_copy: list[str]
    dirs_to_create: list[str]
    excluded_paths: list[str]
    estimated_size_mb: float
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LauncherResult:
    """Result of launcher creation."""

    status: str
    launcher_path: str
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShortcutResult:
    """Shortcut plan/result."""

    status: str
    shortcut_path: str
    target_path: str
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UninstallPlan:
    """Plan for uninstalling ANN while preserving user data by default."""

    install_root: str
    paths_to_remove: list[str]
    paths_to_keep: list[str]
    keep_projects: bool
    keep_models: bool
    keep_outputs: bool
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_install_plan(source_root: str | Path, install_root: str | Path | None = None) -> InstallPlan:
    """Build a deterministic install plan without copying anything."""

    source = normalize_install_path(source_root)
    target = normalize_install_path(install_root or get_default_install_root())
    warnings: list[str] = []
    errors: list[str] = []
    if contains_traversal(source_root):
        errors.append("source_root_path_traversal_blocked")
    if contains_traversal(install_root or ""):
        errors.append("install_root_path_traversal_blocked")
    if is_c_drive(install_root or target):
        errors.append("install_root_c_drive_blocked")
    if not source.exists() or not source.is_dir():
        errors.append("source_root_missing")
    files: list[str] = []
    excluded: list[str] = []
    if not errors:
        for item in sorted(source.iterdir(), key=lambda path: path.name.lower()):
            if item.name not in TOP_LEVEL_INCLUDE:
                if item.name.lower() in BLOCKED_PARTS:
                    excluded.append(str(item))
                continue
            if is_excluded_path(item, source):
                excluded.append(str(item))
                continue
            if item.is_file():
                files.append(str(item))
                continue
            for path in sorted(item.rglob("*"), key=lambda candidate: str(candidate).lower()):
                if is_excluded_path(path, source):
                    if path.is_dir():
                        excluded.append(str(path))
                    continue
                if path.is_file():
                    files.append(str(path))
    dirs = [str(target / name) for name in INSTALL_DIRS]
    if not any(path.endswith("ann_launcher.ps1") for path in files):
        warnings.append("launcher will be generated during install.")
    return InstallPlan(
        source_root=str(source),
        install_root=str(target),
        files_to_copy=files,
        dirs_to_create=dirs,
        excluded_paths=_dedupe(excluded),
        estimated_size_mb=_estimated_size_mb(files),
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )


def create_launcher(install_root: str | Path) -> LauncherResult:
    """Create an ANN launcher script inside install_root/installer."""

    root = normalize_install_path(install_root)
    errors = _validate_mutation_root(root)
    launcher = root / "installer" / "ann_launcher.ps1"
    if errors:
        return LauncherResult("BLOCKED", str(launcher), [], errors)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(_launcher_script(root), encoding="utf-8")
    return LauncherResult("CREATED", str(launcher), [], [])


def create_shortcut(install_root: str | Path, shortcut_location: str | Path | None = None) -> ShortcutResult:
    """Create a safe shortcut command file placeholder for alpha installs."""

    root = normalize_install_path(install_root)
    errors = _validate_mutation_root(root)
    target = root / "desktop" / "ANN.exe"
    shortcut = normalize_install_path(shortcut_location) if shortcut_location else root / "ANN Desktop.lnk.cmd"
    if not is_relative_to(shortcut.parent.resolve(), root) and shortcut_location is None:
        errors.append("shortcut_location_invalid")
    if errors:
        return ShortcutResult("BLOCKED", str(shortcut), str(target), [], errors)
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    shortcut.write_text(f'"{target}"\n', encoding="utf-8")
    return ShortcutResult("CREATED", str(shortcut), str(target), ["PowerShell creates a real .lnk in installer script."], [])


def build_uninstall_plan(
    install_root: str | Path,
    *,
    keep_projects: bool = True,
    keep_models: bool = True,
    keep_outputs: bool = True,
) -> UninstallPlan:
    """Build an uninstall plan that preserves user data by default."""

    root = normalize_install_path(install_root)
    errors = _validate_mutation_root(root)
    keep_names = set()
    if keep_projects:
        keep_names.add("projects")
    if keep_models:
        keep_names.add("models")
    if keep_outputs:
        keep_names.add("outputs")
        keep_names.add("data")
        keep_names.add("logs")
    keep = [str(root / name) for name in sorted(keep_names)]
    removable = [
        "agentic_network",
        "apps",
        "packages",
        "scripts",
        "desktop",
        "installer",
        "runtime",
        "config",
        "adapters",
        "ANN Desktop.lnk.cmd",
        "install_manifest.json",
        "install_log.txt",
    ]
    remove = [str(root / name) for name in removable if name not in keep_names]
    return UninstallPlan(
        install_root=str(root),
        paths_to_remove=remove,
        paths_to_keep=keep,
        keep_projects=keep_projects,
        keep_models=keep_models,
        keep_outputs=keep_outputs,
        warnings=[],
        errors=errors,
    )


def write_install_manifest(install_root: str | Path, plan: InstallPlan) -> Path:
    """Write install manifest inside install root."""

    root = normalize_install_path(install_root)
    errors = _validate_mutation_root(root)
    if errors:
        raise ValueError("; ".join(errors))
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "install_manifest.json"
    manifest.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    return manifest


def _validate_mutation_root(root: Path) -> list[str]:
    errors: list[str] = []
    if contains_traversal(root):
        errors.append("install_root_path_traversal_blocked")
    if is_c_drive(root):
        errors.append("install_root_c_drive_blocked")
    if root == REPO_ROOT or is_relative_to(REPO_ROOT, root):
        errors.append("install_root_must_not_contain_source_repo")
    return errors


def _launcher_script(root: Path) -> str:
    desktop = root / "desktop" / "ANN.exe"
    python = root / "runtime" / "python" / "python.exe"
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$desktop = '{desktop}'",
            f"$python = '{python}'",
            f"$env:PYTHONPATH = '{root}'",
            f"Set-Location '{root}'",
            "if (Test-Path -LiteralPath $desktop) { Start-Process -FilePath $desktop; exit 0 }",
            "if (-not (Test-Path -LiteralPath $python)) { throw 'Embedded Python missing.' }",
            "& $python -m agentic_network.desktop_app.run",
            "",
        ]
    )


def _estimated_size_mb(files: list[str]) -> float:
    total = 0
    for item in files:
        try:
            total += Path(item).stat().st_size
        except OSError:
            continue
    return round(total / (1024 * 1024), 3)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
