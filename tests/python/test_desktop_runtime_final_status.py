from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_desktop_renders_runtime_final_status() -> None:
    snapshot = first_run_snapshot()

    assert "Runtime Collection: COLLECTION_READY" in snapshot
    assert "Wheelhouse Registry:" in snapshot
    assert "Embedded Inventory: INVENTORY_READY" in snapshot
    assert "Runtime Verification: INTEGRITY_VERIFIED" in snapshot
    assert "Payload Readiness: PAYLOAD_READY" in snapshot
    assert "Runtime Final Gap: RUNTIME_FINAL_GAP_RELEASE_BLOCKED" in snapshot
    assert "First Inference Blockers:" in snapshot
    assert "External Verified Runtime:" in snapshot
    assert "Embedded Runtime:" in snapshot
    assert "Qwen2.5 External Smoke:" in snapshot
    assert "Final Release:" in snapshot


def test_inventory_and_chat_render_runtime_final_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Runtime Collection: COLLECTION_READY" in snapshot
        assert "Embedded Inventory: INVENTORY_READY" in snapshot
        assert "Runtime Verification: INTEGRITY_VERIFIED" in snapshot
        assert "Payload Readiness: PAYLOAD_READY" in snapshot
        assert "Runtime Final Gap: RUNTIME_FINAL_GAP_RELEASE_BLOCKED" in snapshot
        assert "External Verified Runtime:" in snapshot
        assert "Embedded Runtime:" in snapshot
        assert "Qwen2.5 External Smoke:" in snapshot
        assert "Final Release:" in snapshot
