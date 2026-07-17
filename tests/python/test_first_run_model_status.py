from __future__ import annotations

from agentic_network.desktop_app.views.first_run_view import build_first_run_state, first_run_snapshot


def test_first_run_model_status_shows_safe_mode_and_models() -> None:
    state = build_first_run_state()
    snapshot = first_run_snapshot()

    assert state["model_preflight"]["runtime"]["safe_mode"] is True
    assert state["model_preflight"]["policy"]["allow_real_model_load"] is False
    assert "Qwen2.5-Coder-7B" in snapshot
    assert "Qwen3-8B" in snapshot
    assert "DeepSeek-R1-Distill-Qwen-14B" in snapshot
    assert "Real Load: disabled" in snapshot
    assert (
        "Actions available in Desktop: Validate Models, Validate Backend, Retry Qwen2.5 Smoke, "
        "Refresh Inventory, Open Model Inventory."
    ) in snapshot
