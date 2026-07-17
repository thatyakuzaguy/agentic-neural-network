from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def _fake_child() -> dict[str, object]:
    return {
        "status": "FIRST_REAL_INFERENCE_PASSED",
        "returncode": 0,
        "real_load_attempted": True,
        "real_load_success": True,
        "real_inference_attempted": True,
        "real_inference_success": True,
        "generated_text": "```python\n# main.py\n```\n```python\n# schemas.py\n```\n```python\n# crud.py\n```\n```python\n# models.py\n```\n```python\n# tests/test_main.py\n```\n# README.md",
        "tokens_generated": 128,
        "prompt_tokens": 80,
        "load_time_seconds": 1.0,
        "inference_time_seconds": 2.0,
        "vram_samples": [{"memory_used_mb": 1234.0}],
    }


def test_developer_team_pipeline_real_coder_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: tmp_path / "model.gguf")
    monkeypatch.setattr(activation, "_run_qwen25_external_child_process", lambda *_args, **_kwargs: _fake_child())
    (tmp_path / "model.gguf").write_text("model", encoding="utf-8")

    result = activation.build_developer_team_pipeline(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real_coder=True,
    )

    assert result["status"] == "TEAM_PIPELINE_PARTIAL"
    assert result["qwen2_5"]["status"] == "PASSED"
    assert result["qwen2_5"]["real_inference_attempted"] is True
    assert result["safe_rollback"] == "PASSED"
    assert (tmp_path / "262_product_architect_output.json").is_file()
    assert (tmp_path / "264_coder_output.json").is_file()
    assert (tmp_path / "266_powerful_review.json").is_file()
    assert (tmp_path / "268_consensus.json").is_file()
    assert (tmp_path / "269_patch_quality.json").is_file()
    assert (tmp_path / "270_test_results.json").is_file()
    assert (tmp_path / "271_action_plan.json").is_file()

