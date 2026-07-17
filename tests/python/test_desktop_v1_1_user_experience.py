from __future__ import annotations

import inspect

from agentic_network.desktop_app.views import (
    chat_view,
    first_run_view,
    model_inventory_view,
    project_manager_view,
)
from agentic_network.runtime_engine import local_model_activation as activation


def test_ann_v1_1_desktop_status_lines_are_normal_user_focused() -> None:
    text = "\n".join(activation.ann_v1_1_desktop_status_lines())

    assert "ANN v1.1" in text
    assert "Release Candidate" in text
    assert "Local-first" in text
    assert "No cloud required" in text
    assert "Ready to build projects:" in text
    assert "Runtime mode:" in text
    assert "What do you want ANN to build or fix?" in text


def test_existing_desktop_views_are_wired_to_v1_1_status() -> None:
    for item in (
        first_run_view.first_run_snapshot,
        chat_view.chat_runtime_snapshot,
        model_inventory_view.model_inventory_snapshot,
        project_manager_view,
    ):
        source = inspect.getsource(item)
        assert "ann_v1_1_desktop_status_lines" in source
