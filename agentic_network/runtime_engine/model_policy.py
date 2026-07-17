"""Local model runtime policy for ANN embedded backends."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "ann_model_policy.json"


@dataclass(frozen=True)
class ModelPolicy:
    """Runtime policy controlling local model loading."""

    version: int
    allow_real_model_load: bool
    allow_model_download: bool
    allow_training: bool
    allow_adapter_write: bool
    allow_dataset_write: bool
    max_loaded_models: int
    vram_policy: str
    default_backend: str
    allowed_backends: list[str]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    """Decision for one model load request."""

    allowed: bool
    reason: str
    warnings: list[str]
    errors: list[str]
    model_name: str
    backend: str
    mode: str
    real_model_load_attempted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_model_policy(config_path: str | Path | None = None) -> ModelPolicy:
    """Load model policy with fail-safe defaults."""

    path = Path(config_path or DEFAULT_POLICY_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_policy(errors=[f"policy_missing:{path}"])
    except json.JSONDecodeError:
        return _default_policy(errors=[f"policy_invalid_json:{path}"])
    if not isinstance(payload, dict):
        return _default_policy(errors=["policy_not_object"])
    allowed = payload.get("allowed_backends")
    return ModelPolicy(
        version=int(payload.get("version", 1)),
        allow_real_model_load=bool(payload.get("allow_real_model_load", False)),
        allow_model_download=bool(payload.get("allow_model_download", False)),
        allow_training=bool(payload.get("allow_training", False)),
        allow_adapter_write=bool(payload.get("allow_adapter_write", False)),
        allow_dataset_write=bool(payload.get("allow_dataset_write", False)),
        max_loaded_models=int(payload.get("max_loaded_models", 1)),
        vram_policy=str(payload.get("vram_policy", "SEQUENTIAL")),
        default_backend=str(payload.get("default_backend", "mock")),
        allowed_backends=[str(item).strip().lower() for item in allowed] if isinstance(allowed, list) else ["mock"],
        errors=[],
        warnings=[],
    )


def validate_model_load_request(
    model_name: str,
    backend: str,
    mode: str,
    *,
    policy: ModelPolicy | None = None,
) -> PolicyDecision:
    """Validate a model load request against local-only policy."""

    loaded_policy = policy or load_model_policy()
    clean_backend = backend.strip().lower()
    clean_model = model_name.strip()
    clean_mode = mode.strip().upper()
    errors: list[str] = []
    warnings: list[str] = []
    if loaded_policy.errors:
        errors.extend(loaded_policy.errors)
    if not clean_model:
        errors.append("model_name_required")
    if clean_backend not in loaded_policy.allowed_backends:
        errors.append(f"backend_not_allowed:{clean_backend}")
    if loaded_policy.max_loaded_models != 1 or loaded_policy.vram_policy.upper() != "SEQUENTIAL":
        errors.append("runtime_policy_must_remain_sequential")
    if loaded_policy.allow_model_download:
        errors.append("model_downloads_must_remain_disabled")
    if loaded_policy.allow_training:
        errors.append("training_must_remain_disabled")
    if loaded_policy.allow_adapter_write:
        errors.append("adapter_writes_must_remain_disabled")
    if loaded_policy.allow_dataset_write:
        errors.append("dataset_writes_must_remain_disabled")
    if clean_backend != "mock" and not loaded_policy.allow_real_model_load:
        errors.append("real_model_load_blocked_by_policy")
    allowed = not errors
    reason = "allowed_by_policy" if allowed else "blocked_by_policy"
    if clean_backend == "mock":
        warnings.append("mock_backend_does_not_load_real_models")
    return PolicyDecision(
        allowed=allowed,
        reason=reason,
        warnings=warnings,
        errors=errors,
        model_name=clean_model,
        backend=clean_backend,
        mode=clean_mode,
        real_model_load_attempted=False,
    )


def _default_policy(errors: list[str] | None = None) -> ModelPolicy:
    return ModelPolicy(
        version=1,
        allow_real_model_load=False,
        allow_model_download=False,
        allow_training=False,
        allow_adapter_write=False,
        allow_dataset_write=False,
        max_loaded_models=1,
        vram_policy="SEQUENTIAL",
        default_backend="mock",
        allowed_backends=["mock"],
        errors=errors or [],
        warnings=[],
    )

