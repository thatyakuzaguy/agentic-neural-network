from __future__ import annotations

from agentic_network.runtime_engine.loader import get_loaded_models
from agentic_network.runtime_engine.local_model_activation import build_deepseek_powerful_bridge


def test_deepseek_powerful_bridge_default_is_non_executing() -> None:
    before = get_loaded_models()
    bridge = build_deepseek_powerful_bridge()

    assert bridge["status"] in {"BLOCKED", "READY"}
    assert bridge["model_name"] == "deepseek_r1_distill_qwen_14b"
    assert bridge["mode"] == "POWERFUL"
    assert bridge["sequential_only"] is True
    assert bridge["never_parallel"] is True
    assert bridge["model_load_attempted"] is False
    assert bridge["real_inference_attempted"] is False
    assert bridge["deepseek_loaded"] is False
    assert get_loaded_models() == before


def test_deepseek_powerful_bridge_ready_when_existing_gate_passes(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_deepseek_powerful_runtime_gate",
        lambda **_kwargs: {
            "status": "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE",
            "model_name": "deepseek_r1_distill_qwen_14b",
            "mode": "POWERFUL",
        },
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.prepare_deepseek_powerful_activation",
        lambda: {"status": "DEEPSEEK_PREPARED"},
    )

    bridge = build_deepseek_powerful_bridge()

    assert bridge["status"] == "READY"
    assert bridge["blockers"] == []

