from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_public_release_status() -> None:
    snapshot = first_run_snapshot()

    assert "ALPHA READY:" in snapshot
    assert "BETA BLOCKED:" in snapshot
    assert "PUBLIC RELEASE BLOCKED:" in snapshot
    assert "Installer RC status:" in snapshot
    assert "Runtime compatibility:" in snapshot
    assert "Embedded runtime installer readiness:" in snapshot
    assert "Qwen2.5 blocked by backend:" in snapshot


def test_inventory_and_chat_render_public_release_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    assert "ALPHA READY:" in inventory
    assert "PUBLIC RELEASE BLOCKED:" in inventory
    assert "Next Release Step:" in inventory
    assert "ALPHA READY:" in chat
    assert "BETA BLOCKED:" in chat
    assert "PUBLIC RELEASE BLOCKED:" in chat
