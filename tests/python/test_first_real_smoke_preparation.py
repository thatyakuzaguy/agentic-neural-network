from __future__ import annotations

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import build_first_real_smoke_preparation


def test_first_real_smoke_preparation_default_is_non_executing() -> None:
    before = get_loaded_models()
    preparation = build_first_real_smoke_preparation()

    assert preparation["status"] in {"BLOCKED", "READY", "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"}
    assert preparation["model_name"] == "qwen2_5_coder_7b_v5"
    assert preparation["mode"] == "FAST"
    assert preparation["backend"] == "llama_cpp"
    assert preparation["model_load_attempted"] is False
    assert preparation["real_inference_attempted"] is False
    assert preparation["safety"]["model_load"] is False
    assert preparation["safety"]["inference"] is False
    assert get_loaded_models() == before
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_first_real_smoke_preparation_ready_when_all_gates_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_embedded_python_evidence",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_wheelhouse_readiness",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_real_inference_launch_guard",
        lambda **_kwargs: {"status": "PASSED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_qwen25_smoke_button_gate",
        lambda _root=None: {"status": "BUTTON_READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_controlled_first_inference_gate",
        lambda *_args, **_kwargs: {"status": "READY_FOR_CONTROLLED_SMOKE"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_first_real_inference_live_status",
        lambda _root=None: {"status": "READY_FOR_CONTROLLED_SMOKE"},
    )

    preparation = build_first_real_smoke_preparation()

    assert preparation["status"] == "READY"
    assert preparation["load_run_unload_allowed_after_confirmation"] is True
