from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_desktop_views_include_final_pipeline_status(monkeypatch, tmp_path: Path) -> None:
    artifact_root = tmp_path / "model_activation"
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", artifact_root)
    activation.run_final_engineering_pipeline(
        "Create a FastAPI Todo API",
        tmp_path,
        output_dir=artifact_root / "run",
    )

    status = activation.build_final_pipeline_desktop_status()
    assert status["status"] == "FINAL_ENGINEERING_PIPELINE_PASSED"
    for view_path in (
        activation.REPO_ROOT / "agentic_network" / "desktop_app" / "views" / "chat_view.py",
        activation.REPO_ROOT / "agentic_network" / "desktop_app" / "views" / "first_run_view.py",
        activation.REPO_ROOT / "agentic_network" / "desktop_app" / "views" / "model_inventory_view.py",
    ):
        source = view_path.read_text(encoding="utf-8")
        assert "build_final_pipeline_desktop_status" in source
        assert "Final Engineering Pipeline" in source
