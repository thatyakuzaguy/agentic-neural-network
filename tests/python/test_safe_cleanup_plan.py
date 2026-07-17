from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_safe_cleanup_plan_classifies_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "outputs" / "model_activation" / "old_run").mkdir(parents=True)
    (tmp_path / "models").mkdir()

    plan = activation.build_safe_cleanup_plan()

    assert plan["status"] == "CLEANUP_PLAN_READY"
    assert any(".pytest_cache" in entry["path"] for entry in plan["safe_to_delete_now"])
    assert any("old_run" in entry["path"] for entry in plan["requires_confirmation"])
    assert any("models" in entry["path"] for entry in plan["never_delete"])
    assert plan["deletion_requires_confirm_cleanup"] is True
    assert plan["deletion_requires_local_token"] is True
