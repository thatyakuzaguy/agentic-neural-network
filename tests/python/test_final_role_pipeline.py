from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_role_pipeline_writes_expected_artifacts(tmp_path: Path) -> None:
    result = activation.run_final_engineering_pipeline(
        activation.FINAL_ENGINEERING_PIPELINE_TASK,
        tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["status"] == "FINAL_ENGINEERING_PIPELINE_PASSED"
    assert result["project_write_mode"] == "sandbox_real"
    assert result["approved_output"]["approved_for_source_apply"] is True
    assert (Path(result["approved_project_path"]) / "main.py").is_file()
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    for name in (
        "304_final_role_pipeline.json",
        "306_product_agent_real.json",
        "308_architect_agent_real.json",
        "310_code_agent_real.json",
        "312_test_engineer_real.json",
        "314_test_lint_sanity.json",
        "316_fixer_loop.json",
        "318_reviewer_real.json",
        "320_final_reviewer_real.json",
        "322_approved_output.json",
    ):
        assert (tmp_path / "artifacts" / name).is_file()


def test_final_role_pipeline_blocks_real_without_token(tmp_path: Path) -> None:
    result = activation.run_final_engineering_pipeline(
        "Create a FastAPI Todo API",
        tmp_path,
        confirm_real_models=True,
        approval_token="wrong",
        output_dir=tmp_path / "artifacts",
    )

    assert result["status"] == "FINAL_ENGINEERING_PIPELINE_FAILED"
    assert "approval_token_invalid_or_missing" in result["errors"]
    assert result["approved_output"]["status"] == "BLOCKED_OUTPUT"
