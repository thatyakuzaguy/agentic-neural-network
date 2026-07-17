from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.backends.base import BackendGenerateResult, BackendLoadResult, BackendUnloadResult
from agentic_network.runtime_engine.loader import get_loaded_models, reset_runtime_state
from agentic_network.runtime_engine.local_model_activation import (
    LOCAL_TEST_TOKEN,
    run_qwen25_real_inference_smoke,
)


class _SuccessfulRealBackend:
    name = "llama_cpp"

    def load_model(self, model_name: str) -> BackendLoadResult:
        return BackendLoadResult(status="LOADED", model_name=model_name, backend=self.name, loaded=True, errors=[], warnings=[])

    def generate(self, model_name: str, prompt: str) -> BackendGenerateResult:
        return BackendGenerateResult(
            status="SUCCESS",
            model_name=model_name,
            backend=self.name,
            text="ANN_QWEN25_REAL_INFERENCE_OK",
            tokens_in=len(prompt.split()),
            tokens_out=1,
            duration_ms=1,
            errors=[],
            warnings=[],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(status="UNLOADED", model_name=model_name, backend=self.name, unloaded=True, errors=[], warnings=[])


class _MismatchedRealBackend(_SuccessfulRealBackend):
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


def test_qwen25_real_inference_blocks_without_token(tmp_path: Path) -> None:
    reset_runtime_state()

    result = run_qwen25_real_inference_smoke(confirm=True, approval_token=None, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert "approval_token_invalid_or_missing" in result["errors"]


def test_qwen25_real_inference_blocks_without_confirmation(tmp_path: Path) -> None:
    reset_runtime_state()

    result = run_qwen25_real_inference_smoke(confirm=False, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert "confirmation_required" in result["errors"]


def test_qwen25_real_inference_success_path_unloads_and_writes_artifacts(tmp_path: Path) -> None:
    reset_runtime_state()

    result = run_qwen25_real_inference_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_SuccessfulRealBackend(),
    )

    assert result["status"] == "PASSED"
    assert result["real_load_attempted"] is True
    assert result["real_inference_attempted"] is True
    assert result["real_load_succeeded"] is True
    assert result["real_inference_succeeded"] is True
    assert result["loaded_models_after"] == []
    assert get_loaded_models() == []
    assert {Path(path).name for path in result["artifacts"]} == {
        "122_qwen25_real_inference.json",
        "123_qwen25_real_inference.md",
        "124_runtime_benchmark.json",
        "125_runtime_benchmark.md",
    }
    payload = json.loads((tmp_path / "122_qwen25_real_inference.json").read_text(encoding="utf-8"))
    assert payload["response"] == "ANN_QWEN25_REAL_INFERENCE_OK"


def test_qwen25_real_inference_output_mismatch_is_failure(tmp_path: Path) -> None:
    reset_runtime_state()

    result = run_qwen25_real_inference_smoke(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        output_dir=tmp_path,
        backend=_MismatchedRealBackend(),
    )

    assert result["status"] == "FAILED_OUTPUT_MISMATCH"
    assert result["safe_mode_final"] is True
    assert result["loaded_models_after"] == []
