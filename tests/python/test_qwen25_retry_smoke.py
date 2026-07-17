from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)
from agentic_network.runtime_engine.local_model_activation import LOCAL_TEST_TOKEN, run_qwen25_retry_smoke


class _ReadyBackend:
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


def test_qwen25_retry_blocks_without_token(tmp_path: Path) -> None:
    result = run_qwen25_retry_smoke(confirm=True, approval_token=None, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert "approval_token_invalid_or_missing" in result["errors"]


def test_qwen25_retry_blocks_without_confirmation(tmp_path: Path) -> None:
    result = run_qwen25_retry_smoke(confirm=False, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert "confirmation_required" in result["errors"]


def test_qwen25_retry_unavailable_backend_does_not_attempt_load(tmp_path: Path) -> None:
    result = run_qwen25_retry_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    if result["readiness_status"] == "UNAVAILABLE":
        assert result["status"] == "UNAVAILABLE"
        assert result["real_load_attempted"] is False


def test_qwen25_retry_ready_backend_allows_smoke_and_unloads(tmp_path: Path) -> None:
    result = run_qwen25_retry_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_ReadyBackend(),
    )

    assert result["status"] == "PASSED"
    assert result["real_load_attempted"] is True
    assert result["real_inference_attempted"] is True
    assert result["loaded_models_after"] == []
    assert result["safe_mode_final"] is True
    assert {Path(path).name for path in result["artifacts"]} == {
        "112_qwen25_retry_smoke.json",
        "113_qwen25_retry_smoke.md",
    }
