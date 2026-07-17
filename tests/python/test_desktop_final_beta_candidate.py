from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_final_beta_candidate_status() -> None:
    snapshot = first_run_snapshot()

    assert "Manual Runtime Checklist: MANUAL_STEPS_REQUIRED" in snapshot
    assert "Runtime Integrity: INTEGRITY_VERIFIED" in snapshot
    assert "Wheelhouse Validation: VERIFIED" in snapshot
    assert "Beta Final Gate: BETA_FINAL_READY" in snapshot
    assert "Known Blockers:" in snapshot
    assert "Final Next Step:" in snapshot
    assert "Safe Mode: True" in snapshot


def test_inventory_and_chat_render_final_beta_candidate_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "Manual Runtime Checklist: MANUAL_STEPS_REQUIRED" in snapshot
        assert "Runtime Integrity: INTEGRITY_VERIFIED" in snapshot
        assert "Wheelhouse Validation: VERIFIED" in snapshot
        assert "Beta Final Gate: BETA_FINAL_READY" in snapshot
