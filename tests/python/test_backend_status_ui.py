from __future__ import annotations

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot


def test_first_run_renders_backend_and_memory_status() -> None:
    snapshot = first_run_snapshot()

    assert "Backend readiness llama_cpp:" in snapshot
    assert "CUDA environment:" in snapshot
    assert "llama_cpp real status:" in snapshot
    assert "Memory probe:" in snapshot
    assert "Qwen3 preparation:" in snapshot
    assert "Qwen3 controlled activation:" in snapshot
    assert "DeepSeek POWERFUL preparation:" in snapshot
    assert "Retry Qwen2.5 Smoke" in snapshot


def test_model_inventory_renders_backend_status_safely() -> None:
    snapshot = model_inventory_snapshot()

    assert "Backend readiness llama_cpp:" in snapshot
    assert "CUDA environment:" in snapshot
    assert "llama_cpp real status:" in snapshot
    assert "Qwen3 preparation:" in snapshot
    assert "Qwen3 controlled activation:" in snapshot
    assert "DeepSeek POWERFUL preparation:" in snapshot
    assert "DeepSeek POWERFUL: blocked / untouched" in snapshot


def test_chat_snapshot_renders_backend_status_safely() -> None:
    snapshot = chat_runtime_snapshot()

    assert "Backend readiness llama_cpp:" in snapshot
    assert "CUDA environment:" in snapshot
    assert "llama_cpp real status:" in snapshot
    assert "Qwen2.5 real inference:" in snapshot
    assert "GPU/VRAM probe:" in snapshot
    assert "Qwen2.5 Controlled Activation" in snapshot
