from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_desktop_surfaces_offline_runtime_gap() -> None:
    snapshot = first_run_snapshot()

    assert "ANN ready / Environment not ready:" in snapshot
    assert "Offline wheelhouse status:" in snapshot
    assert "Runtime checks scripts status:" in snapshot
    assert "Embedded runtime installer readiness:" in snapshot
    assert "Do not install from ANN: true" in snapshot
    assert "Qwen2.5 blocked by backend:" in snapshot
    assert "POWERFUL blocked:" in snapshot


def test_model_inventory_and_chat_render_offline_status() -> None:
    inventory = model_inventory_snapshot()
    chat = chat_runtime_snapshot()

    assert "Offline wheelhouse status:" in inventory
    assert "Runtime checks scripts status:" in inventory
    assert "Do not install from ANN: true" in inventory
    assert "Offline wheelhouse status:" in chat
    assert "Embedded Python readiness:" in chat
    assert "Qwen2.5 blocked by backend" in chat
