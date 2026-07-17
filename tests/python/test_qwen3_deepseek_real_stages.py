from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def _fake_hf_child(text: str = "requirements architecture acceptance criteria risks implementation bugs security tests") -> dict[str, object]:
    return {
        "status": "REAL_INFERENCE_PASSED",
        "returncode": 0,
        "real_load_attempted": True,
        "real_load_success": True,
        "real_inference_attempted": True,
        "real_inference_success": True,
        "generated_text": text,
        "tokens_generated": 64,
        "prompt_tokens": 32,
        "load_time_seconds": 1.0,
        "inference_time_seconds": 1.0,
        "vram_samples": [{"memory_used_mb": 2048.0}],
    }


def test_qwen3_real_stage_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "qwen3"
    adapter = tmp_path / "adapter"
    model.mkdir()
    adapter.mkdir()
    monkeypatch.setattr(
        activation,
        "_resolve_runtime_filesystem_path",
        lambda path: adapter if "adapter" in str(path) or "training" in str(path) else model,
    )
    monkeypatch.setattr(activation, "_run_hf_external_child_process", lambda **_kwargs: _fake_hf_child())

    result = activation.run_qwen3_real_architect_stage(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real=True,
    )

    assert result["status"] == "QWEN3_REAL_PASSED"
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert (tmp_path / "272_qwen3_real_load.json").is_file()
    assert (tmp_path / "278_qwen3_safe_rollback.json").is_file()


def test_deepseek_real_stage_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "deepseek"
    model.mkdir()
    (model / "model-00001-of-00001.safetensors").write_text("", encoding="utf-8")
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: model)
    monkeypatch.setattr(activation, "_directory_file_size_mb", lambda *_args, **_kwargs: 1000.0)
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {"cuda_available": True, "gpu_name": "test-gpu", "vram_total_mb": 24000.0},
    )
    monkeypatch.setattr(activation, "_query_nvidia_smi_memory", lambda: {"available": True, "free_mb": 20000.0})
    monkeypatch.setattr(activation, "_run_hf_external_child_process", lambda **_kwargs: _fake_hf_child())

    result = activation.run_deepseek_real_reviewer_stage(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real=True,
    )

    assert result["status"] == "DEEPSEEK_REAL_PASSED"
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert (tmp_path / "280_deepseek_real_load.json").is_file()
    assert (tmp_path / "286_deepseek_safe_rollback.json").is_file()
