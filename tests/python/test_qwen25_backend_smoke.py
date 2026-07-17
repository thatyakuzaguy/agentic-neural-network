from __future__ import annotations

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)
from agentic_network.runtime_engine.local_model_activation import LOCAL_TEST_TOKEN, run_controlled_qwen25_smoke


class _UnavailableBackend:
    name = "llama_cpp"

    def health_check(self) -> BackendHealthResult:
        return BackendHealthResult(
            status="UNAVAILABLE",
            backend=self.name,
            available=False,
            errors=["llama_cpp_binding_unavailable"],
            warnings=[],
        )


class _SuccessfulBackend:
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
            text="ANN_QWEN25_SMOKE_OK",
            tokens_in=len(prompt.split()),
            tokens_out=1,
            duration_ms=1,
            errors=[],
            warnings=[],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(status="UNLOADED", model_name=model_name, backend=self.name, unloaded=True, errors=[], warnings=[])


def test_qwen25_backend_unavailable_is_reported(tmp_path) -> None:
    result = run_controlled_qwen25_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_UnavailableBackend(),
    )

    assert result["status"] == "UNAVAILABLE"
    assert "llama_cpp_binding_unavailable" in result["errors"]
    assert result["mock_fallback"] is True


def test_qwen25_backend_success_path_unloads(tmp_path) -> None:
    result = run_controlled_qwen25_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_SuccessfulBackend(),
    )

    assert result["status"] == "PASSED"
    assert result["real_load_attempted"] is True
    assert result["real_inference_attempted"] is True
    assert result["safe_mode_final"] is True
    assert result["loaded_models_after"] == []
