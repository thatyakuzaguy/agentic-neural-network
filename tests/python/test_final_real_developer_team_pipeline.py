from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_real_developer_team_pipeline_safe_default(tmp_path: Path) -> None:
    result = activation.run_final_real_developer_team_pipeline(
        project_root=tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["status"] == "FINAL_ENGINEERING_PIPELINE_PASSED"
    assert result["product_agent"]["bridge_used"] is True
    assert result["reviewer"]["model_name"] == activation.DEEPSEEK14B_MODEL_NAME
    assert result["reviewer"]["backend"] == "llama_cpp"
    assert result["approved_output"]["protected_paths_modified"] is False


def test_final_real_developer_team_pipeline_can_use_real_stage_contract(monkeypatch, tmp_path: Path) -> None:
    def fake_stage(role_key, task, context, routing, target, **kwargs):
        return {
            "status": "PASSED",
            "role": routing["routes"][role_key]["role"],
            "role_key": role_key,
            "real_model_used": True,
            "bridge_used": False,
            "model_name": routing["routes"][role_key]["model_name"],
            "backend": "llama_cpp" if role_key in {"reviewer", "final_reviewer", "code_agent", "test_engineer"} else "transformers_peft_external",
            "load_success": True,
            "inference_success": True,
            "unload_success": True,
            "safe_rollback": "PASSED",
            "duration_seconds": 0.01,
            "peak_vram_mb": 123,
            "active_models_after": 0,
            "parallel_llm_loads_after": 0,
            "generated_text": "PASS",
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr(activation, "_run_final_role_stage", fake_stage)
    result = activation.run_final_real_developer_team_pipeline(
        approval_token=activation.LOCAL_TEST_TOKEN,
        confirm_real_models=True,
        project_root=tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["status"] == "FINAL_ENGINEERING_PIPELINE_PASSED"
    assert result["product_agent"]["real_model_used"] is True
    assert result["reviewer"]["real_model_used"] is True
