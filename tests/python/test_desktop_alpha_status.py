from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_desktop_renders_alpha_status() -> None:
    snapshot = first_run_snapshot()

    assert "ALPHA READY:" in snapshot
    assert "BETA BLOCKED:" in snapshot
    assert "PUBLIC RELEASE BLOCKED:" in snapshot
    assert "Runtime Status:" in snapshot
    assert "Environment Status:" in snapshot
    assert "Known Limitations:" in snapshot
    assert "Next Milestone:" in snapshot
    assert "Beta Roadmap:" in snapshot
    assert "Alpha Smoke Matrix:" in snapshot
    assert "Manual Validation:" in snapshot


def test_inventory_and_chat_render_alpha_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    assert "Alpha Smoke Matrix:" in inventory
    assert "Beta Roadmap:" in inventory
    assert "Manual Validation:" in inventory
    assert "Alpha Smoke Matrix:" in chat
    assert "Beta Roadmap:" in chat
    assert "Manual Validation:" in chat
