from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_pipeline_triggers_fixer_when_tests_fail(monkeypatch, tmp_path: Path) -> None:
    def failing_tests(*_args, **_kwargs):
        return {
            "status": "FAILED",
            "summary": "pytest failed",
            "real_model_used": False,
            "bridge_used": True,
            "model_name": "test_lint_sanity",
            "backend": "existing_test_runner_gate",
            "load_success": False,
            "inference_success": False,
            "unload_success": True,
            "safe_rollback": "PASSED",
            "duration_seconds": 0.0,
            "warnings": [],
            "errors": ["pytest failed"],
        }

    monkeypatch.setattr(activation, "_final_test_lint_sanity", failing_tests)
    result = activation.run_final_engineering_pipeline(
        "Create a FastAPI Todo API",
        tmp_path,
        output_dir=tmp_path / "artifacts",
    )

    assert result["test_lint_sanity"]["status"] == "FAILED"
    assert result["fixer_loop"]["status"] == "PASSED"
    assert result["fixer_loop"]["attempt_count"] == 1
    assert result["status"] == "FINAL_ENGINEERING_PIPELINE_FAILED"
