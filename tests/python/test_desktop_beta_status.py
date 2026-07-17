from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_beta_status() -> None:
    snapshot = first_run_snapshot()

    assert "Beta Gate: BETA_BLOCKED" in snapshot
    assert "Embedded Runtime Layout:" in snapshot
    assert "Wheelhouse Materialization:" in snapshot
    assert "Clean Machine Emulator:" in snapshot
    assert "Beta Blockers:" in snapshot
    assert "Next Beta Step:" in snapshot
    assert "Qwen2.5 blocked by backend:" in snapshot
    assert "Qwen3 blocked: True" in snapshot
    assert "DeepSeek blocked: True" in snapshot


def test_model_inventory_and_chat_render_beta_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Beta Gate: BETA_BLOCKED" in snapshot
        assert "Embedded Runtime Layout:" in snapshot
        assert "Wheelhouse Materialization:" in snapshot
        assert "Clean Machine Emulator:" in snapshot
        assert "Qwen2.5 backend blocked: True" in snapshot
        assert "Qwen3 blocked: True" in snapshot
        assert "DeepSeek blocked: True" in snapshot
        assert "POWERFUL blocked: True" in snapshot
