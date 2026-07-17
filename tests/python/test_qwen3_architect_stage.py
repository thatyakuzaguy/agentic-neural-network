from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_qwen3_architect_stage_bridge_mode_and_sequential() -> None:
    stage = activation.build_qwen3_architect_stage()

    assert stage["status"] == "QWEN3_BRIDGE_MODE"
    assert stage["qwen3_loaded"] is False
    assert stage["real_inference_attempted"] is False
    assert stage["active_models_after"] == 0
    assert stage["parallel_llm_loads_after"] == 0
    assert "requirements" in stage["output"]
    assert "architecture" in stage["output"]

