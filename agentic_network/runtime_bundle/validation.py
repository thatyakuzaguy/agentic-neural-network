"""Validation for ANN Runtime Bundle manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentic_network.runtime_bundle.manifest import RuntimeManifest
from agentic_network.runtime_bundle.runtime import build_runtime_manifest


@dataclass(frozen=True)
class RuntimeBundleValidation:
    """Validation result for the detected runtime bundle."""

    status: str
    python_runtime_kind: str
    available_backends: list[str]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_runtime_bundle(manifest: RuntimeManifest | None = None) -> RuntimeBundleValidation:
    """Validate runtime bundle detection without installing or executing tools."""

    bundle = manifest or build_runtime_manifest()
    warnings = list(bundle.warnings)
    errors = list(bundle.errors)
    if not bundle.python_executable:
        errors.append("python_executable_missing")
    if not bundle.available_backends:
        errors.append("runtime_backends_missing")
    if "mock" not in bundle.available_backends:
        warnings.append("mock_backend_missing")
    if bundle.python_runtime.kind not in {"embedded", "venv", "conda", "system"}:
        errors.append(f"unknown_python_runtime:{bundle.python_runtime.kind}")
    if bundle.pyside_version is None:
        warnings.append("pyside6_missing")
    if bundle.torch_version is None:
        warnings.append("torch_missing")
    if bundle.transformers_version is None:
        warnings.append("transformers_missing")
    return RuntimeBundleValidation(
        status="VALID" if not errors else "INVALID",
        python_runtime_kind=bundle.python_runtime.kind,
        available_backends=list(bundle.available_backends),
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )


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
