"""Local model inventory for ANN embedded runtime foundation.

The inventory only validates explicitly declared paths. It never scans model
directories, downloads model files, opens GGUF weights, or writes adapters.
"""

from __future__ import annotations

import json
import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from agentic_network.runtime_engine.backend_registry import list_available_backends
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY_PATH = REPO_ROOT / "config" / "ann_model_inventory.json"


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating one declared model path."""

    status: str
    exists: bool
    adapter_exists: bool
    backend_available: bool
    load_allowed: bool
    load_blocked_reason: str
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelRecord:
    """One model entry declared in ANN local inventory."""

    model_name: str
    name: str
    family: str
    mode: str
    backend: str
    path: str
    source_path: str
    distribution_path: str
    adapter_path: str | None
    quantization: str
    estimated_vram_mb: int
    enabled: bool
    fallback_backend: str | None = None
    model_declared: bool = True
    path_exists: bool = False
    adapter_exists: bool = False
    backend_available: bool = False
    load_allowed: bool = False
    load_blocked_reason: str = "not_evaluated"
    status: str = "declared"
    exists: bool = False
    validation_status: str = "UNKNOWN"
    errors: list[str] | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors or [])
        payload["warnings"] = list(self.warnings or [])
        return payload


@dataclass(frozen=True)
class ModelInventory:
    """Loaded model inventory."""

    version: int
    models: list[ModelRecord]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "models": [model.to_dict() for model in self.models],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def load_model_inventory(config_path: str | Path | None = None) -> ModelInventory:
    """Load and validate the local model inventory config."""

    path = Path(config_path or DEFAULT_INVENTORY_PATH)
    errors: list[str] = []
    warnings: list[str] = []
    if _has_traversal(str(path)):
        return ModelInventory(version=1, models=[], errors=["inventory_path_traversal_blocked"], warnings=[])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ModelInventory(version=1, models=[], errors=[f"inventory_missing:{path}"], warnings=[])
    except json.JSONDecodeError:
        return ModelInventory(version=1, models=[], errors=[f"inventory_invalid_json:{path}"], warnings=[])
    if not isinstance(payload, dict):
        return ModelInventory(version=1, models=[], errors=["inventory_not_object"], warnings=[])
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        return ModelInventory(version=int(payload.get("version", 1)), models=[], errors=["inventory_models_not_list"], warnings=[])
    records: list[ModelRecord] = []
    for item in raw_models:
        if not isinstance(item, dict):
            warnings.append("inventory_model_entry_not_object")
            continue
        record = _record_from_payload(item)
        validation = validate_model_path(record)
        records.append(
            ModelRecord(
                model_name=record.model_name,
                name=record.name,
                family=record.family,
                mode=record.mode,
                backend=record.backend,
                path=record.path,
                source_path=record.source_path,
                distribution_path=record.distribution_path,
                adapter_path=record.adapter_path,
                quantization=record.quantization,
                estimated_vram_mb=record.estimated_vram_mb,
                enabled=record.enabled,
                fallback_backend=record.fallback_backend,
                model_declared=True,
                path_exists=validation.exists,
                adapter_exists=validation.adapter_exists,
                backend_available=validation.backend_available,
                load_allowed=validation.load_allowed,
                load_blocked_reason=validation.load_blocked_reason,
                status=_inventory_status(record, validation),
                exists=validation.exists,
                validation_status=validation.status,
                errors=validation.errors,
                warnings=validation.warnings,
            )
        )
    return ModelInventory(version=int(payload.get("version", 1)), models=records, errors=errors, warnings=warnings)


def list_available_models(config_path: str | Path | None = None) -> list[ModelRecord]:
    """Return declared models from the local inventory."""

    return load_model_inventory(config_path).models


def resolve_model_record(model_name: str, config_path: str | Path | None = None) -> ModelRecord | None:
    """Resolve a model record by exact declared name."""

    clean_name = model_name.strip()
    for record in list_available_models(config_path):
        if record.name == clean_name:
            return record
    return None


def validate_model_path(model_record: ModelRecord) -> ValidationResult:
    """Validate one declared model path without opening model files."""

    errors: list[str] = []
    warnings: list[str] = []
    if not model_record.name:
        errors.append("model_name_required")
    if not model_record.path:
        errors.append("model_path_required")
        return ValidationResult(
            status="INVALID",
            exists=False,
            adapter_exists=False,
            backend_available=False,
            load_allowed=False,
            load_blocked_reason="model_path_required",
            errors=errors,
            warnings=warnings,
        )
    if _has_traversal(model_record.path):
        errors.append("model_path_traversal_blocked")
    if _is_blocked_c_drive(model_record.path):
        errors.append("model_path_c_drive_blocked")
    if not _is_allowed_declared_root(model_record.path):
        errors.append("model_path_root_not_allowed")
    adapter_path = model_record.adapter_path
    if adapter_path:
        if _has_traversal(adapter_path):
            errors.append("adapter_path_traversal_blocked")
        if _is_blocked_c_drive(adapter_path):
            errors.append("adapter_path_c_drive_blocked")
        if not _is_allowed_declared_root(adapter_path):
            errors.append("adapter_path_root_not_allowed")
    exists = False if errors else Path(model_record.path).exists()
    adapter_exists = bool(adapter_path) and not errors and Path(str(adapter_path)).exists()
    backend_available = _backend_available(model_record.backend)
    policy = load_model_policy()
    decision = validate_model_load_request(model_record.name, model_record.backend, model_record.mode, policy=policy)
    load_allowed = decision.allowed and exists and backend_available and model_record.enabled
    load_blocked_reason = "allowed_by_policy" if load_allowed else _load_blocked_reason(decision, exists, backend_available)
    if not model_record.enabled:
        warnings.append("model_disabled")
        status = "DISABLED" if not errors else "BLOCKED"
    elif errors:
        status = "BLOCKED"
    elif exists:
        status = "VALID"
    else:
        status = "MISSING"
        warnings.append("declared_model_path_missing")
    return ValidationResult(
        status=status,
        exists=exists,
        adapter_exists=adapter_exists,
        backend_available=backend_available,
        load_allowed=load_allowed,
        load_blocked_reason=load_blocked_reason,
        errors=errors,
        warnings=warnings,
    )


def _record_from_payload(payload: dict[str, Any]) -> ModelRecord:
    model_name = str(payload.get("model_name") or payload.get("name") or "")
    source_path = str(payload.get("source_path") or payload.get("path") or "")
    return ModelRecord(
        model_name=model_name,
        name=str(payload.get("name") or model_name),
        family=str(payload.get("family") or ""),
        mode=str(payload.get("mode") or ""),
        backend=str(payload.get("backend") or ""),
        path=source_path,
        source_path=source_path,
        distribution_path=str(payload.get("distribution_path") or source_path),
        adapter_path=str(payload["adapter_path"]) if payload.get("adapter_path") is not None else None,
        quantization=str(payload.get("quantization") or ""),
        estimated_vram_mb=int(payload.get("estimated_vram_mb") or 0),
        enabled=bool(payload.get("enabled", False)),
        fallback_backend=str(payload["fallback_backend"]) if payload.get("fallback_backend") is not None else None,
        status=str(payload.get("status") or "declared"),
    )


def _backend_available(backend: str) -> bool:
    clean_backend = backend.strip().lower()
    if clean_backend in list_available_backends():
        return True
    if clean_backend == "deepseek_unsloth":
        return importlib.util.find_spec("agentic_network.models.deepseek_unsloth") is not None
    return False


def _load_blocked_reason(decision: Any, exists: bool, backend_available: bool) -> str:
    if decision.errors:
        return ";".join(decision.errors)
    if not exists:
        return "model_path_missing"
    if not backend_available:
        return "backend_unavailable"
    return "model_disabled_or_not_configured"


def _inventory_status(record: ModelRecord, validation: ValidationResult) -> str:
    declared = str(record.status).strip()
    valid_statuses = {
        "declared",
        "detected",
        "missing",
        "blocked_by_policy",
        "mock_only",
        "safe_mode",
        "not_configured",
        "detected_but_blocked_by_policy",
    }
    if declared in valid_statuses:
        if "real_model_load_blocked_by_policy" in validation.load_blocked_reason and validation.exists:
            return "detected_but_blocked_by_policy"
        return declared
    if validation.errors:
        return "blocked_by_policy"
    if validation.exists:
        return "detected"
    return "missing"


def _is_allowed_declared_root(raw_path: str) -> bool:
    normalized = raw_path.replace("\\", "/")
    if normalized.startswith("/mnt/d/") or normalized.startswith("/mnt/e/"):
        return True
    drive = PureWindowsPath(raw_path).drive.lower()
    return drive in {"d:", "e:"}


def _is_blocked_c_drive(raw_path: str) -> bool:
    normalized = raw_path.replace("\\", "/").lower()
    drive = PureWindowsPath(raw_path).drive.lower()
    posix = PurePosixPath(normalized)
    return drive == "c:" or posix.parts[:2] == ("/", "mnt") and len(posix.parts) > 2 and posix.parts[2] == "c"


def _has_traversal(raw_path: str) -> bool:
    return any(part == ".." for part in raw_path.replace("\\", "/").split("/"))
