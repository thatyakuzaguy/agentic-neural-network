"""Logical model loader enforcing ANN sequential VRAM policy.

This foundation does not download, inspect, or load physical model files. It
tracks one logical active model at a time so future real loaders can plug into
the same safety contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from agentic_network.runtime_engine.backend_registry import get_backend
from agentic_network.runtime_engine.model_policy import validate_model_load_request


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ann_runtime_engine.json"
_LOADED_MODELS: list[str] = []
_METRICS: dict[str, Any] = {
    "load_count": 0,
    "unload_count": 0,
    "active_models": 0,
    "parallel_llm_loads": 0,
    "peak_active_models": 0,
    "peak_vram_mb": 0,
    "backend_name": "mock",
    "backend_status": "UNKNOWN",
    "last_load_status": "UNKNOWN",
    "last_generate_status": "UNKNOWN",
    "last_unload_status": "UNKNOWN",
    "events": [],
}


def load_model(model_name: str, backend_name: str | None = None) -> dict[str, Any]:
    """Load one logical model, unloading any previous model first."""

    started = perf_counter()
    clean_name = model_name.strip()
    if not clean_name:
        return {"status": "BLOCKED", "model_name": "", "load_time_ms": 0, "errors": ["model_name_required"]}
    config = _load_config()
    if int(config.get("max_loaded_models", 1)) != 1 or bool(config.get("allow_parallel_llms", False)):
        return {
            "status": "BLOCKED",
            "model_name": clean_name,
            "load_time_ms": 0,
            "errors": ["runtime_policy_must_remain_sequential"],
        }
    if _LOADED_MODELS and _LOADED_MODELS[0] != clean_name:
        unload_model(_LOADED_MODELS[0], backend_name=backend_name)
    backend = get_backend(backend_name, config=config)
    policy_decision = validate_model_load_request(clean_name, backend.name, str(config.get("default_mode", "FAST")))
    if not policy_decision.allowed:
        _METRICS["backend_name"] = backend.name
        _METRICS["backend_status"] = "BLOCKED_BY_POLICY"
        _METRICS["last_load_status"] = "BLOCKED"
        _update_active_metrics()
        return {
            "status": "BLOCKED",
            "model_name": clean_name,
            "backend": backend.name,
            "backend_status": "BLOCKED_BY_POLICY",
            "load_time_ms": _elapsed_ms(started),
            "errors": policy_decision.errors,
            "warnings": policy_decision.warnings,
            "backend_result": {
                "status": "BLOCKED",
                "model_name": clean_name,
                "backend": backend.name,
                "loaded": False,
                "errors": policy_decision.errors,
                "warnings": policy_decision.warnings,
            },
            "policy_decision": policy_decision.to_dict(),
        }
    health = backend.health_check()
    load = backend.load_model(clean_name)
    _METRICS["backend_name"] = backend.name
    _METRICS["backend_status"] = health.status
    _METRICS["last_load_status"] = load.status
    if not load.loaded:
        _update_active_metrics()
        return {
            "status": load.status,
            "model_name": clean_name,
            "backend": backend.name,
            "backend_status": health.status,
            "load_time_ms": _elapsed_ms(started),
            "errors": load.errors,
            "warnings": [*health.warnings, *load.warnings],
            "backend_result": load.to_dict(),
        }
    if not _LOADED_MODELS:
        _LOADED_MODELS.append(clean_name)
        _METRICS["load_count"] = int(_METRICS["load_count"]) + 1
        _record_event("load", clean_name, backend.name)
    _update_active_metrics()
    return {
        "status": "LOADED",
        "model_name": clean_name,
        "backend": backend.name,
        "backend_status": health.status,
        "load_time_ms": _elapsed_ms(started),
        "errors": [],
        "warnings": [*health.warnings, *load.warnings],
        "backend_result": load.to_dict(),
    }


def unload_model(model_name: str, backend_name: str | None = None) -> dict[str, Any]:
    """Unload one logical model if it is active."""

    started = perf_counter()
    clean_name = model_name.strip()
    config = _load_config()
    backend = get_backend(backend_name, config=config)
    unload = backend.unload_model(clean_name)
    _METRICS["backend_name"] = backend.name
    _METRICS["last_unload_status"] = unload.status
    if clean_name in _LOADED_MODELS:
        _LOADED_MODELS.remove(clean_name)
        _METRICS["unload_count"] = int(_METRICS["unload_count"]) + 1
        _record_event("unload", clean_name, backend.name)
    _update_active_metrics()
    return {
        "status": unload.status,
        "model_name": clean_name,
        "backend": backend.name,
        "unload_time_ms": _elapsed_ms(started),
        "errors": unload.errors,
        "warnings": unload.warnings,
        "backend_result": unload.to_dict(),
    }


def get_loaded_models() -> list[str]:
    """Return currently loaded logical models."""

    return list(_LOADED_MODELS)


def get_runtime_metrics() -> dict[str, Any]:
    """Return runtime metrics without mutating protected areas."""

    _update_active_metrics()
    return {**_METRICS, "events": list(_METRICS["events"])}


def record_generate_status(backend_name: str, status: str) -> None:
    """Record backend generation status without changing loaded model state."""

    _METRICS["backend_name"] = backend_name
    _METRICS["last_generate_status"] = status
    _update_active_metrics()


def reset_runtime_state() -> None:
    """Reset logical loader state for tests and deterministic smoke runs."""

    _LOADED_MODELS.clear()
    _METRICS.update(
        {
            "load_count": 0,
            "unload_count": 0,
            "active_models": 0,
            "parallel_llm_loads": 0,
            "peak_active_models": 0,
            "peak_vram_mb": 0,
            "backend_name": "mock",
            "backend_status": "UNKNOWN",
            "last_load_status": "UNKNOWN",
            "last_generate_status": "UNKNOWN",
            "last_unload_status": "UNKNOWN",
            "events": [],
        }
    )


def _load_config() -> dict[str, Any]:
    try:
        payload = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"max_loaded_models": 1, "allow_parallel_llms": False}
    return payload if isinstance(payload, dict) else {"max_loaded_models": 1, "allow_parallel_llms": False}


def _update_active_metrics() -> None:
    active = len(_LOADED_MODELS)
    _METRICS["active_models"] = active
    _METRICS["peak_active_models"] = max(int(_METRICS["peak_active_models"]), active)
    _METRICS["parallel_llm_loads"] = max(0, active - 1)
    _METRICS["peak_vram_mb"] = max(int(_METRICS["peak_vram_mb"]), _estimate_vram_mb(_LOADED_MODELS[0]) if active else 0)


def _record_event(action: str, model_name: str, backend_name: str) -> None:
    _METRICS["events"].append(
        {
            "action": action,
            "model_name": model_name,
            "backend": backend_name,
            "active_models": len(_LOADED_MODELS),
        }
    )


def _estimate_vram_mb(model_name: str) -> int:
    lowered = model_name.lower()
    if "14b" in lowered:
        return 14000
    if "qwen3" in lowered:
        return 7000
    return 4096


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))
