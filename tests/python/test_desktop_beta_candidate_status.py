from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_beta_candidate_status() -> None:
    snapshot = first_run_snapshot()

    assert "External Runtime: FULLY_MATERIALIZED" in snapshot
    assert "Wheelhouse Population: READY" in snapshot
    assert "Embedded Runtime Candidate: BETA_CANDIDATE_READY" in snapshot
    assert "First Real Inference: FIRST_REAL_INFERENCE_PASSED_EXTERNAL" in snapshot
    assert "Beta Candidate: True" in snapshot
    assert "Runtime Missing Components:" in snapshot
    assert "Safe Mode: True" in snapshot
    assert "Next Step:" in snapshot


def test_inventory_and_chat_render_beta_candidate_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    for snapshot in (inventory, chat):
        assert "External Runtime: FULLY_MATERIALIZED" in snapshot
        assert "Wheelhouse Population: READY" in snapshot
        assert "Embedded Runtime Candidate: BETA_CANDIDATE_READY" in snapshot
        assert "First Real Inference: FIRST_REAL_INFERENCE_PASSED_EXTERNAL" in snapshot
        assert "Beta Candidate: True" in snapshot
