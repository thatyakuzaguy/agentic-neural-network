from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_deepseek_reviewer_stage_bridge_mode_no_powerful_activation() -> None:
    stage = activation.build_deepseek_reviewer_stage(coder_output={"generated_text": "main.py"})

    assert stage["status"] == "DEEPSEEK_BRIDGE_MODE"
    assert stage["deepseek_loaded"] is False
    assert stage["powerful_activated"] is False
    assert stage["real_inference_attempted"] is False
    assert stage["active_models_after"] == 0
    assert stage["parallel_llm_loads_after"] == 0
    assert "bugs" in stage["review"]

