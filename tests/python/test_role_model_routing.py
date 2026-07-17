from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_role_model_routing_uses_requested_models() -> None:
    routing = activation.build_final_role_model_routing()
    routes = routing["routes"]

    assert routes["product_agent"]["model_name"] == activation.QWEN3_MODEL_NAME
    assert routes["architect_agent"]["model_name"] == activation.QWEN3_MODEL_NAME
    assert routes["code_agent"]["model_name"] == activation.QWEN25_MODEL_NAME
    assert routes["fixer_agent"]["model_name"] == activation.QWEN25_MODEL_NAME
    assert routes["test_engineer"]["model_name"] == activation.QWEN25_MODEL_NAME
    assert routes["reviewer"]["model_name"] == activation.DEEPSEEK14B_MODEL_NAME
    assert routes["reviewer"]["backend"] == "llama_cpp"
    assert routes["reviewer"]["model_path"] == activation.DEEPSEEK14B_GGUF_PATH
    assert routes["reviewer"]["n_gpu_layer_fallbacks"] == [20, 16, 12, 8, 4]
    assert routing["active_models_limit"] == 1
    assert routing["parallel_llm_loads"] == 0
