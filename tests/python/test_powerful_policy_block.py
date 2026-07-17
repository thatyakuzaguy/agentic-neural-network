from __future__ import annotations

from agentic_network.model_routing.router import resolve_model_route
from agentic_network.runtime_engine.local_model_activation import build_local_model_preflight
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request


def test_powerful_routes_to_deepseek_but_policy_blocks_real_load() -> None:
    route = resolve_model_route("architect", "POWERFUL")
    policy = load_model_policy()
    decision = validate_model_load_request(route.selected_model, "deepseek_unsloth", "POWERFUL", policy=policy)

    assert route.selected_model == "deepseek_r1_distill_qwen_14b"
    assert decision.allowed is False
    assert "real_model_load_blocked_by_policy" in decision.errors


def test_powerful_preflight_reports_blocked() -> None:
    preflight = build_local_model_preflight()

    assert preflight["powerful"]["model"] == "deepseek_r1_distill_qwen_14b"
    assert preflight["powerful"]["blocked"] is True
    assert "real_model_load_blocked_by_policy" in preflight["powerful"]["reason"]
