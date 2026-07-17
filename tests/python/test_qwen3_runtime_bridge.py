from __future__ import annotations

from agentic_network.runtime_engine.loader import get_loaded_models
from agentic_network.runtime_engine.local_model_activation import build_qwen3_runtime_bridge


def test_qwen3_runtime_bridge_default_is_non_executing() -> None:
    before = get_loaded_models()
    bridge = build_qwen3_runtime_bridge()

    assert bridge["status"] in {"BLOCKED", "READY"}
    assert bridge["model_name"] == "qwen3_8b_product_v9_repaired_v2_bullets"
    assert bridge["mode"] == "FAST"
    assert bridge["sequential_only"] is True
    assert bridge["model_load_attempted"] is False
    assert bridge["real_inference_attempted"] is False
    assert bridge["qwen3_loaded"] is False
    assert get_loaded_models() == before


def test_qwen3_runtime_bridge_ready_when_existing_gate_passes(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_qwen3_runtime_activation_gate",
        lambda **_kwargs: {
            "status": "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION",
            "model_name": "qwen3_8b_product_v9_repaired_v2_bullets",
            "mode": "FAST",
            "adapter": "qwen3-8b-product-agent-v9-repaired-v2-bullets",
        },
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.prepare_qwen3_controlled_activation",
        lambda: {"status": "QWEN3_PREPARED"},
    )

    bridge = build_qwen3_runtime_bridge()

    assert bridge["status"] == "READY"
    assert bridge["blockers"] == []

