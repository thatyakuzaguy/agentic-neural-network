from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_desktop_renders_guided_runtime_steps() -> None:
    snapshot = first_run_snapshot()

    assert "Guided Runtime Activation: GUIDED_PARTIAL" in snapshot
    assert "Step 1: Materialize Runtime: COMPLETED" in snapshot
    assert "Step 2: Populate Wheelhouse: COMPLETED" in snapshot
    assert "Step 3: Verify Hashes: COMPLETED" in snapshot
    assert "Step 4: Validate Runtime: COMPLETED" in snapshot
    assert "Step 5: Check Launch Guard: BLOCKED" in snapshot
    assert "Step 6: Run First Qwen2.5 Smoke: COMPLETED_EXTERNAL" in snapshot
    assert "Run First Qwen2.5 Smoke Button: DISABLED" in snapshot
    assert "Smoke Button Gate: BUTTON_DISABLED" in snapshot


def test_inventory_and_chat_render_guided_runtime_steps() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Guided Runtime Activation: GUIDED_PARTIAL" in snapshot
        assert "Run First Qwen2.5 Smoke Button: DISABLED" in snapshot
        assert "Smoke Button Gate: BUTTON_DISABLED" in snapshot
        assert "Final Release Bridge: FINAL_RELEASE_BLOCKED" in snapshot
