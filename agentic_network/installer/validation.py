"""Installer validation and first-run checks."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_network.installer.paths import contains_traversal, is_c_drive, normalize_install_path


@dataclass(frozen=True)
class ValidationResult:
    """Generic installer validation result."""

    valid: bool
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeValidationResult:
    """First-run runtime validation result."""

    status: str
    python_executable: str
    python_version: str
    pyside6_available: bool
    desktop_importable: bool
    install_root: str
    data_root: str
    outputs_root: str
    projects_root: str
    models_root: str
    runtime_config_exists: bool
    model_policy_exists: bool
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_install_plan(plan: Any) -> ValidationResult:
    """Validate an InstallPlan without writing files."""

    errors = list(getattr(plan, "errors", []))
    warnings = list(getattr(plan, "warnings", []))
    install_root = normalize_install_path(getattr(plan, "install_root", ""))
    source_root = normalize_install_path(getattr(plan, "source_root", ""))
    if contains_traversal(getattr(plan, "install_root", "")):
        errors.append("install_root_path_traversal_blocked")
    if is_c_drive(getattr(plan, "install_root", "")):
        errors.append("install_root_c_drive_blocked")
    if source_root == install_root:
        errors.append("install_root_must_not_equal_source_root")
    for file_path in getattr(plan, "files_to_copy", []):
        lowered = str(file_path).lower().replace("\\", "/")
        if any(
            blocked in lowered
            for blocked in ("/.git/", "/models/", "/training/", "/outputs/", "/unsloth_compiled_cache/")
        ):
            errors.append(f"protected_source_planned:{file_path}")
    return ValidationResult(valid=not errors, warnings=_dedupe(warnings), errors=_dedupe(errors))


def validate_runtime_requirements(install_root: str | Path | None = None) -> RuntimeValidationResult:
    """Perform local first-run validation without installing dependencies."""

    root = normalize_install_path(install_root or Path("D:/ANN"))
    data_root = root / "data"
    outputs_root = root / "outputs"
    projects_root = root / "projects"
    models_root = root / "models"
    warnings: list[str] = []
    errors: list[str] = []
    pyside6_available = importlib.util.find_spec("PySide6") is not None
    if not pyside6_available:
        warnings.append("PySide6 is not importable; ANN Desktop will not open until installed or bundled.")
    desktop_importable = importlib.util.find_spec("agentic_network.desktop_app.run") is not None
    if not desktop_importable:
        errors.append("ANN Desktop entrypoint is not importable.")
    runtime_config = root / "config" / "ann_runtime_engine.json"
    model_policy = root / "config" / "ann_model_policy.json"
    repo_runtime_config = Path(__file__).resolve().parents[2] / "config" / "ann_runtime_engine.json"
    repo_model_policy = Path(__file__).resolve().parents[2] / "config" / "ann_model_policy.json"
    runtime_config_exists = runtime_config.is_file() or repo_runtime_config.is_file()
    model_policy_exists = model_policy.is_file() or repo_model_policy.is_file()
    if not runtime_config_exists:
        errors.append("Runtime engine config is missing.")
    if not model_policy_exists:
        errors.append("Model policy config is missing.")
    for writable in (data_root, outputs_root, projects_root):
        if writable.exists() and not writable.is_dir():
            errors.append(f"writable_root_not_directory:{writable}")
    if not models_root.exists():
        warnings.append("Models path does not exist yet; this is allowed for base installer.")
    return RuntimeValidationResult(
        status="VALID" if not errors else "INVALID",
        python_executable=sys.executable,
        python_version=sys.version.split()[0],
        pyside6_available=pyside6_available,
        desktop_importable=desktop_importable,
        install_root=str(root),
        data_root=str(data_root),
        outputs_root=str(outputs_root),
        projects_root=str(projects_root),
        models_root=str(models_root),
        runtime_config_exists=runtime_config_exists,
        model_policy_exists=model_policy_exists,
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )


def write_runtime_validation(path: Path, result: RuntimeValidationResult) -> None:
    """Write a runtime validation report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


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

