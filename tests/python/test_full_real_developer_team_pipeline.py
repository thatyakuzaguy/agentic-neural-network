from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from tests.python.test_developer_team_pipeline import _fake_child
from tests.python.test_qwen3_deepseek_real_stages import _fake_hf_child


def test_full_real_developer_team_pipeline_passes_with_all_real_stages(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model"
    adapter = tmp_path / "adapter"
    model.mkdir()
    adapter.mkdir()
    (model / "model-00001-of-00001.safetensors").write_text("", encoding="utf-8")
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda path: adapter if "adapter" in str(path) or "training" in str(path) else model)
    monkeypatch.setattr(activation, "_directory_file_size_mb", lambda *_args, **_kwargs: 1000.0)
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {"cuda_available": True, "gpu_name": "test-gpu", "vram_total_mb": 24000.0},
    )
    monkeypatch.setattr(activation, "_query_nvidia_smi_memory", lambda: {"available": True, "free_mb": 20000.0})
    monkeypatch.setattr(activation, "_run_hf_external_child_process", lambda **_kwargs: _fake_hf_child())
    monkeypatch.setattr(activation, "_run_qwen25_external_child_process", lambda *_args, **_kwargs: _fake_child())
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )

    result = activation.build_full_real_developer_team_pipeline(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real=True,
    )

    assert result["status"] == "TEAM_PIPELINE_PASSED"
    assert result["qwen3"]["status"] == "QWEN3_REAL_PASSED"
    assert result["qwen2_5"]["status"] == "PASSED"
    assert result["deepseek"]["status"] == "DEEPSEEK_REAL_PASSED"
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert (tmp_path / "288_full_team_pipeline.json").is_file()
    assert (tmp_path / "297_full_team_action_plan.md").is_file()
