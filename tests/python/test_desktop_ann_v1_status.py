from __future__ import annotations

import inspect

from agentic_network.desktop_app.views import chat_view, first_run_view, model_inventory_view
from agentic_network.runtime_engine import local_model_activation as activation


def test_ann_v1_desktop_status_lines_include_release_candidate_state() -> None:
    lines = activation.ann_v1_desktop_status_lines()
    text = "\n".join(lines)

    assert "ANN v1.0" in text
    assert "Final Real Pipeline:" in text
    assert "Developer Team:" in text
    assert "Qwen3:" in text
    assert "Qwen2.5:" in text
    assert "DeepSeek GGUF:" in text
    assert "Sequential Runtime:" in text
    assert "Release: v1.0 Candidate" in text


def test_existing_desktop_views_are_wired_to_ann_v1_status_helper() -> None:
    for function in (
        first_run_view.first_run_snapshot,
        chat_view.chat_runtime_snapshot,
        model_inventory_view.model_inventory_snapshot,
    ):
        source = inspect.getsource(function)
        assert "ann_v1_desktop_status_lines" in source
