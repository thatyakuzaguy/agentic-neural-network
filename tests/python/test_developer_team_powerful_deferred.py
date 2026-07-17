from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_network.runtime_engine import local_model_activation as activation


def _qwen3_passed() -> dict[str, Any]:
    return {
        "status": "QWEN3_REAL_PASSED",
        "architecture": ["FastAPI app", "Todo repository", "pytest suite"],
        "artifacts": [],
        "peak_vram_mb": 4096.0,
    }


def _qwen25_passed() -> dict[str, Any]:
    return {
        "status": "PASSED",
        "generated_text": "main.py schemas.py crud.py models.py tests/test_main.py pytest README.md",
        "artifacts": [],
        "peak_vram_mb": 6500.0,
    }


def test_team_pipeline_passes_with_powerful_deferred(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "deepseek"
    model.mkdir()
    (model / "model-00001-of-00002.safetensors").write_text("", encoding="utf-8")
    monkeypatch.setattr(activation, "run_qwen3_real_architect_stage", lambda **_kwargs: _qwen3_passed())
    monkeypatch.setattr(activation, "build_qwen25_real_coder_stage", lambda **_kwargs: _qwen25_passed())
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: model)
    monkeypatch.setattr(activation, "_directory_file_size_mb", lambda *_args, **_kwargs: 28600.0)
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {
            "cuda_available": True,
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "vram_total_mb": 8192.0,
        },
    )
    monkeypatch.setattr(activation, "_query_nvidia_smi_memory", lambda: {"available": True, "free_mb": 7000.0})
    monkeypatch.setattr(activation, "_deepseek_gguf_alternative_exists", lambda _path=None: False)
    monkeypatch.setattr(
        activation,
        "_run_hf_external_child_process",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unsafe DeepSeek load attempted")),
    )

    result = activation.build_full_real_developer_team_pipeline(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real=True,
    )

    assert result["status"] == "TEAM_PIPELINE_PASSED_WITH_POWERFUL_DEFERRED"
    assert result["qwen3"]["status"] == "QWEN3_REAL_PASSED"
    assert result["qwen2_5"]["status"] == "PASSED"
    assert result["deepseek"]["status"] == "DEEPSEEK_POWERFUL_DEFERRED"
    assert result["deepseek"]["real_load_attempted"] is False
    assert result["deepseek"]["real_inference_success"] is False
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert (tmp_path / "302_developer_team_final_status.json").is_file()
    assert (tmp_path / "303_developer_team_final_status.md").is_file()
