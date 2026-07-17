from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_runtime_readiness() -> None:
    snapshot = first_run_snapshot()

    assert "Post Materialization: READY" in snapshot
    assert "Runtime Readiness: READY" in snapshot
    assert "First Inference Gate: NOT_READY" in snapshot
    assert "Wheelhouse: VERIFIED" in snapshot
    assert "Runtime Integrity: INTEGRITY_VERIFIED" in snapshot
    assert "Runtime Readiness Blockers:" in snapshot
    assert "Next Manual Step:" in snapshot
    assert "Safe Mode: True" in snapshot


def test_inventory_and_chat_render_runtime_readiness() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Post Materialization: READY" in snapshot
        assert "Runtime Readiness: READY" in snapshot
        assert "First Inference Gate: NOT_READY" in snapshot
        assert "Runtime Readiness Blockers:" in snapshot
