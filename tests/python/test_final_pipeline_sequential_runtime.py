from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_pipeline_preserves_sequential_runtime_state(tmp_path: Path) -> None:
    result = activation.run_final_engineering_pipeline(
        "Create a FastAPI Todo API",
        tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["sequential_runtime"] == "ACTIVE"
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert result["safe_rollback"] == "PASSED"
    for key in ("product_agent", "architect_agent", "code_agent", "test_engineer", "reviewer", "final_reviewer"):
        assert result[key]["active_models_after"] == 0
        assert result[key]["parallel_llm_loads_after"] == 0
        assert result[key]["safe_rollback"] == "PASSED"
