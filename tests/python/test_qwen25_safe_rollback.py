from __future__ import annotations

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics, load_model, reset_runtime_state
from agentic_network.runtime_engine.local_model_activation import LOCAL_TEST_TOKEN, run_controlled_qwen25_smoke


class _BadOutputBackend:
    name = "llama_cpp"

    def health_check(self) -> BackendHealthResult:
        return BackendHealthResult(status="AVAILABLE", backend=self.name, available=True, errors=[], warnings=[])

    def load_model(self, model_name: str) -> BackendLoadResult:
        return BackendLoadResult(status="LOADED", model_name=model_name, backend=self.name, loaded=True, errors=[], warnings=[])

    def generate(self, model_name: str, prompt: str) -> BackendGenerateResult:
        return BackendGenerateResult(
            status="SUCCESS",
            model_name=model_name,
            backend=self.name,
            text="WRONG",
            tokens_in=len(prompt.split()),
            tokens_out=1,
            duration_ms=1,
            errors=[],
            warnings=[],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(status="UNLOADED", model_name=model_name, backend=self.name, unloaded=True, errors=[], warnings=[])


def test_qwen25_smoke_rolls_back_after_failed_generation(tmp_path) -> None:
    reset_runtime_state()

    result = run_controlled_qwen25_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_BadOutputBackend(),
    )

    assert result["status"] == "LOAD_FAILED"
    assert result["safe_mode_final"] is True
    assert get_loaded_models() == []
    assert get_runtime_metrics()["parallel_llm_loads"] == 0


def test_qwen25_smoke_blocks_if_model_already_active(tmp_path) -> None:
    reset_runtime_state()
    load_model("qwen3_product_finetuned")

    result = run_controlled_qwen25_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert "active_model_present_before_smoke" in result["errors"]
    assert result["real_load_attempted"] is False
    reset_runtime_state()
