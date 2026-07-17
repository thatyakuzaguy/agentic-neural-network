"""Deterministic agent-to-model routing for local ANN execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_network.model_routing.models import (
    DEFAULT_VRAM_POLICY,
    ModelRouteDecision,
    VALID_MODES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ann_model_routing.json"
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


def resolve_model_route(
    agent_name: str,
    mode: str = "FAST",
    config_path: str | Path | None = None,
) -> ModelRouteDecision:
    """Resolve the model route for one agent without loading or checking models."""

    normalized_agent = _normalize_agent(agent_name)
    normalized_mode = mode.strip().upper()
    errors: list[str] = []
    warnings: list[str] = []
    config = _load_config(config_path, errors)
    vram_policy = str(config.get("vram_policy") or DEFAULT_VRAM_POLICY)
    fallback_model = _fallback_model(config, normalized_mode)
    if errors:
        return ModelRouteDecision(
            status="BLOCKED",
            agent_name=normalized_agent,
            mode=normalized_mode,
            selected_model="",
            fallback_model=fallback_model,
            vram_policy=vram_policy,
            sequential_required=vram_policy.upper() == DEFAULT_VRAM_POLICY,
            reason="Routing config failed safe validation.",
            warnings=warnings,
            errors=errors,
        )
    if normalized_mode not in VALID_MODES or normalized_mode not in _modes(config):
        return ModelRouteDecision(
            status="INVALID",
            agent_name=normalized_agent,
            mode=normalized_mode,
            selected_model="",
            fallback_model=fallback_model,
            vram_policy=vram_policy,
            sequential_required=vram_policy.upper() == DEFAULT_VRAM_POLICY,
            reason=f"Invalid execution mode: {normalized_mode}.",
            warnings=warnings,
            errors=[f"invalid_mode:{normalized_mode}"],
        )
    routes = config.get("agent_routes") if isinstance(config.get("agent_routes"), dict) else {}
    route = routes.get(normalized_agent)
    if isinstance(route, dict) and isinstance(route.get(normalized_mode), str):
        return ModelRouteDecision(
            status="VALID",
            agent_name=normalized_agent,
            mode=normalized_mode,
            selected_model=str(route[normalized_mode]),
            fallback_model=fallback_model,
            vram_policy=vram_policy,
            sequential_required=vram_policy.upper() == DEFAULT_VRAM_POLICY,
            reason="Agent route resolved from routing config.",
            warnings=warnings,
            errors=[],
        )
    warnings.append(f"unknown_agent_route:{normalized_agent}")
    return ModelRouteDecision(
        status="FALLBACK",
        agent_name=normalized_agent,
        mode=normalized_mode,
        selected_model=fallback_model,
        fallback_model=fallback_model,
        vram_policy=vram_policy,
        sequential_required=vram_policy.upper() == DEFAULT_VRAM_POLICY,
        reason="Agent route missing; fallback model selected.",
        warnings=warnings,
        errors=[],
    )


def load_routing_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load routing config for read-only desktop and test consumers."""

    errors: list[str] = []
    config = _load_config(config_path, errors)
    if errors:
        return {"status": "BLOCKED", "errors": errors}
    return config


def _load_config(config_path: str | Path | None, errors: list[str]) -> dict[str, Any]:
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    raw = str(path)
    if _has_traversal(raw):
        errors.append("config_path_traversal_blocked")
        return {}
    resolved = path.resolve()
    if _has_protected_part(resolved):
        errors.append(f"config_path_protected_path_blocked:{resolved}")
        return {}
    if not resolved.is_file():
        errors.append(f"config_missing:{resolved}")
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"config_invalid_json:{resolved}")
        return {}
    if not isinstance(payload, dict):
        errors.append("config_not_object")
        return {}
    return payload


def _modes(config: dict[str, Any]) -> set[str]:
    modes = config.get("modes")
    if not isinstance(modes, dict):
        return set()
    return {str(key).upper() for key in modes}


def _fallback_model(config: dict[str, Any], mode: str) -> str:
    routes = config.get("agent_routes") if isinstance(config.get("agent_routes"), dict) else {}
    fallback_route = routes.get("fallback") if isinstance(routes, dict) else {}
    if isinstance(fallback_route, dict) and isinstance(fallback_route.get(mode), str):
        return str(fallback_route[mode])
    modes = config.get("modes") if isinstance(config.get("modes"), dict) else {}
    mode_config = modes.get(mode) if isinstance(modes, dict) else {}
    if isinstance(mode_config, dict) and isinstance(mode_config.get("fallback_model"), str):
        return str(mode_config["fallback_model"])
    return "qwen3_base"


def _normalize_agent(agent_name: str) -> str:
    normalized = agent_name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "product_agent": "product",
        "requirements": "product",
        "planner": "product",
        "solution_architect": "architect",
        "frontend": "code",
        "backend": "code",
        "database": "code",
        "qa": "test",
        "test_engineer": "test",
        "security_agent": "security",
        "code_review": "reviewer",
        "final": "reviewer",
        "final_reviewer": "reviewer",
    }
    return aliases.get(normalized, normalized or "fallback")


def _has_traversal(raw: str) -> bool:
    return any(part == ".." for part in raw.replace("\\", "/").split("/"))


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)
