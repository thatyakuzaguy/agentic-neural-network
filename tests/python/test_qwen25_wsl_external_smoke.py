from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_qwen25_wsl_external_smoke_requires_token(tmp_path: Path) -> None:
    result = activation.run_qwen25_first_real_inference_wsl(
        approval_token=None,
        manual_confirmation=True,
        output_dir=tmp_path,
    )

    assert result["status"] == "FIRST_REAL_INFERENCE_FAILED"
    assert result["real_load_attempted"] is False
    assert "approval_token_invalid_or_missing" in result["errors"]


def test_qwen25_wsl_external_smoke_uses_child_and_rolls_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda **_kwargs: {
            "status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL",
            "selected_runtime_source": "wsl_conda",
            "runtime_type": "external_wsl_conda",
        },
    )
    monkeypatch.setattr(
        activation,
        "_run_wsl_qwen25_smoke_child",
        lambda **_kwargs: {
            "status": "FIRST_REAL_INFERENCE_PASSED",
            "real_load_attempted": True,
            "real_load_success": True,
            "real_inference_attempted": True,
            "real_inference_success": True,
            "generated_text": "Hi there",
            "tokens_generated": 2,
            "prompt_tokens": 1,
            "peak_vram_mb": 2048,
            "load_time_seconds": 1.25,
            "inference_time_seconds": 0.5,
            "returncode": 0,
            "stderr": "",
        },
    )

    result = activation.run_qwen25_first_real_inference_wsl(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
    )

    assert result["status"] == "FIRST_REAL_INFERENCE_PASSED"
    assert result["runtime_type"] == "external_wsl_conda"
    assert result["real_load_success"] is True
    assert result["real_inference_success"] is True
    assert result["generated_text"] == "Hi there"
    assert result["safe_mode_final"] is True
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert (tmp_path / "346_qwen25_wsl_external_smoke.json").is_file()
    assert (tmp_path / "348_qwen25_wsl_external_smoke_child.json").is_file()
