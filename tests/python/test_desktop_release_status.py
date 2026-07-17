from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_release_candidate_status() -> None:
    snapshot = first_run_snapshot()

    assert "Lockfile status:" in snapshot
    assert "Wheelhouse integrity:" in snapshot
    assert "Installer RC status:" in snapshot
    assert "Clean machine validation status:" in snapshot
    assert "Next release step:" in snapshot
    assert "Ready for real inference: True via external WSL runtime" in snapshot


def test_inventory_and_chat_render_release_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    assert "Installer RC status:" in inventory
    assert "Clean machine validation status:" in inventory
    assert "Lockfile status:" in chat
    assert "Installer RC status:" in chat
    assert "Qwen2.5 blocked by backend" in chat
