"""Runtime Bundle detection for ANN Desktop.

This module only detects local runtime capabilities. It does not download,
install, import training stacks, execute subprocesses, or scan protected model
directories.
"""

from __future__ import annotations

import json
import os
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from agentic_network.runtime_bundle.manifest import PythonRuntime, RuntimeManifest
from agentic_network.runtime_engine.backend_registry import list_available_backends, load_runtime_config
from agentic_network.runtime_engine.model_inventory import load_model_inventory


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ann_runtime_bundle.json"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "outputs" / "runtime_bundle"
PACKAGE_NAMES = {
    "torch": "torch",
    "transformers": "transformers",
    "PySide6": "PySide6",
}


def build_runtime_manifest(config_path: str | Path | None = None) -> RuntimeManifest:
    """Build a read-only runtime manifest for ANN Desktop."""

    config = _load_config(config_path)
    warnings: list[str] = []
    errors: list[str] = []
    candidates = _detect_python_candidates(config)
    active_runtime = candidates[0] if candidates else _current_python_runtime("system", 4)
    versions = {name: _package_version(package) for name, package in PACKAGE_NAMES.items()}
    if versions["PySide6"] is None:
        warnings.append("PySide6 is not importable; the native desktop UI requires it or a bundled copy.")
    runtime_config = load_runtime_config()
    configured_backends = runtime_config.get("available_backends")
    available_backends = (
        [str(item) for item in configured_backends]
        if isinstance(configured_backends, list)
        else list_available_backends()
    )
    inventory = load_model_inventory()
    if inventory.errors:
        warnings.extend(inventory.errors)
    installed_models = [record.to_dict() for record in inventory.models]
    dependencies = list_runtime_dependencies(config_path=config_path)
    estimated_size = estimate_runtime_size(config_path=config_path)
    return RuntimeManifest(
        python_version=sys.version.split()[0],
        python_executable=sys.executable,
        python_runtime=active_runtime,
        python_candidates=candidates,
        torch_version=versions["torch"],
        transformers_version=versions["transformers"],
        pyside_version=versions["PySide6"],
        runtime_engine_version=str(runtime_config.get("version", "local")),
        installed_models=installed_models,
        available_backends=available_backends,
        runtime_dependencies=dependencies,
        estimated_size_mb=estimated_size,
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )


def list_runtime_dependencies(config_path: str | Path | None = None) -> list[dict[str, Any]]:
    """List local runtime dependency availability without installing anything."""

    config = _load_config(config_path)
    dependency_names = config.get("dependencies")
    if not isinstance(dependency_names, list):
        dependency_names = ["python", "torch", "transformers", "PySide6", "runtime_engine"]
    dependencies: list[dict[str, Any]] = []
    for name in dependency_names:
        clean_name = str(name)
        if clean_name == "python":
            dependencies.append(
                {
                    "name": "python",
                    "version": sys.version.split()[0],
                    "available": True,
                    "source": sys.executable,
                }
            )
        elif clean_name == "runtime_engine":
            dependencies.append(
                {
                    "name": "runtime_engine",
                    "version": str(load_runtime_config().get("version", "local")),
                    "available": True,
                    "source": "agentic_network.runtime_engine",
                }
            )
        else:
            version = _package_version(clean_name)
            dependencies.append(
                {
                    "name": clean_name,
                    "version": version,
                    "available": version is not None,
                    "source": _package_location(clean_name),
                }
            )
    return dependencies


def estimate_runtime_size(config_path: str | Path | None = None) -> float:
    """Estimate detected runtime size in MB using only declared local files."""

    config = _load_config(config_path)
    include_python = bool(config.get("include_python_executable_size", True))
    total = 0
    if include_python:
        total += _safe_file_size(Path(sys.executable))
    for package in ("torch", "transformers", "PySide6"):
        location = _package_location(package)
        if location:
            total += _safe_file_size(Path(location))
    return round(total / (1024 * 1024), 3)


def write_runtime_bundle_artifacts(run_dir: str | Path, manifest: RuntimeManifest | None = None) -> list[str]:
    """Write runtime bundle artifacts 84 and 87 into a run directory."""

    from agentic_network.runtime_bundle.validation import validate_runtime_bundle

    target = Path(run_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    bundle_manifest = manifest or build_runtime_manifest()
    validation = validate_runtime_bundle(bundle_manifest)
    manifest_path = target / "84_runtime_bundle_manifest.json"
    validation_path = target / "87_runtime_validation.md"
    manifest_path.write_text(json.dumps(bundle_manifest.to_dict(), indent=2), encoding="utf-8")
    validation_path.write_text(_validation_markdown(bundle_manifest, validation.to_dict()), encoding="utf-8")
    return [str(manifest_path), str(validation_path)]


def _detect_python_candidates(config: dict[str, Any]) -> list[PythonRuntime]:
    candidates: list[PythonRuntime] = []
    configured_embedded = config.get("embedded_python_executable")
    if isinstance(configured_embedded, str) and configured_embedded.strip():
        path = Path(configured_embedded)
        if path.is_file():
            candidates.append(_runtime_from_path("embedded", path, 1, path == Path(sys.executable)))
    current_kind = _classify_current_python()
    candidates.append(_current_python_runtime(current_kind, _runtime_priority(current_kind)))
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_python = Path(conda_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
        if conda_python.is_file() and conda_python != Path(sys.executable):
            candidates.append(_runtime_from_path("conda", conda_python, 3, False))
    venv_prefix = os.environ.get("VIRTUAL_ENV")
    if venv_prefix:
        venv_python = Path(venv_prefix) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if venv_python.is_file() and venv_python != Path(sys.executable):
            candidates.append(_runtime_from_path("venv", venv_python, 2, False))
    unique: dict[str, PythonRuntime] = {}
    for candidate in candidates:
        unique.setdefault(candidate.executable.lower(), candidate)
    return sorted(unique.values(), key=lambda item: item.priority)


def _classify_current_python() -> str:
    executable = Path(sys.executable)
    if (executable.with_suffix("._pth")).is_file() or "embedded" in str(executable).lower():
        return "embedded"
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix) or os.environ.get("VIRTUAL_ENV"):
        return "venv"
    if os.environ.get("CONDA_PREFIX"):
        return "conda"
    return "system"


def _runtime_priority(kind: str) -> int:
    return {"embedded": 1, "venv": 2, "conda": 3, "system": 4}.get(kind, 9)


def _current_python_runtime(kind: str, priority: int) -> PythonRuntime:
    return PythonRuntime(
        kind=kind,
        executable=sys.executable,
        version=sys.version.split()[0],
        priority=priority,
        active=True,
    )


def _runtime_from_path(kind: str, path: Path, priority: int, active: bool) -> PythonRuntime:
    return PythonRuntime(
        kind=kind,
        executable=str(path.resolve()),
        version=sys.version.split()[0] if active else "unknown",
        priority=priority,
        active=active,
    )


def _package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _package_location(package_name: str) -> str | None:
    try:
        distribution = metadata.distribution(package_name)
    except metadata.PackageNotFoundError:
        return None
    files = list(distribution.files or [])
    if not files:
        return None
    located = distribution.locate_file(files[0])
    return str(located)


def _safe_file_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    return 0


def _load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validation_markdown(manifest: RuntimeManifest, validation: dict[str, Any]) -> str:
    lines = [
        "# ANN Runtime Bundle Validation",
        "",
        f"Status: {validation.get('status')}",
        f"Python runtime: {manifest.python_runtime.kind}",
        f"Python executable: {manifest.python_executable}",
        f"Runtime engine: {manifest.runtime_engine_version}",
        f"Available backends: {', '.join(manifest.available_backends)}",
        f"Estimated size MB: {manifest.estimated_size_mb}",
        "",
        "## Warnings",
        *[f"- {warning}" for warning in validation.get("warnings", [])],
        "",
        "## Errors",
        *[f"- {error}" for error in validation.get("errors", [])],
        "",
        "Safety: detection only; no internet, downloads, dependency installation, training, or model modification.",
        "",
    ]
    return "\n".join(lines)


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
