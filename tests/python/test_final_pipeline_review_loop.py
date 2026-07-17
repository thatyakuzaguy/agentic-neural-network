from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_pipeline_triggers_fixer_when_review_fails(monkeypatch, tmp_path: Path) -> None:
    original = activation._run_final_role_stage

    def fake_stage(role_key, *args, **kwargs):
        stage = original(role_key, *args, **kwargs)
        if role_key == "reviewer":
            stage["generated_text"] = "FAIL: missing error handling"
        return stage

    monkeypatch.setattr(activation, "_run_final_role_stage", fake_stage)
    result = activation.run_final_engineering_pipeline(
        "Create a FastAPI Todo API",
        tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["review_fix_loop"]["status"] == "PASSED"
    assert result["review_fix_loop"]["attempt_count"] == 1
