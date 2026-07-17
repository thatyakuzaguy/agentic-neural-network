from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_runtime_live_status() -> None:
    snapshot = first_run_snapshot()

    assert "Runtime Materialization: READY" in snapshot
    assert "Beta Runtime: BETA_RUNTIME_READY" in snapshot
    assert "First Real Inference:" in snapshot
    assert "VRAM Usage:" in snapshot
    assert "Current Model: qwen2_5_coder_7b_v5" in snapshot
    assert "Unload Status: SKIPPED" in snapshot
    assert "Final Release Bridge: FINAL_RELEASE_BLOCKED" in snapshot


def test_inventory_and_chat_render_runtime_live_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Runtime Materialization: READY" in snapshot
        assert "Beta Runtime: BETA_RUNTIME_READY" in snapshot
        assert "First Real Inference:" in snapshot
        assert "Current Model: qwen2_5_coder_7b_v5" in snapshot
