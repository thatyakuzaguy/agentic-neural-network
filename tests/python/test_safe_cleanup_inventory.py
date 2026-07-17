from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_safe_cleanup_inventory_reports_candidates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / ".ruff_cache").mkdir()
    (tmp_path / "pkg" / "__pycache__").mkdir(parents=True)
    run = tmp_path / "outputs" / "model_activation" / "old_run"
    run.mkdir(parents=True)
    (run / "_stage_child.py").write_text("print('x')", encoding="utf-8")
    (run / "_stage_child_result.json").write_text("{}", encoding="utf-8")
    protected = tmp_path / "outputs" / "model_activation" / "ANN_V1_RELEASE_HARDENING"
    protected.mkdir(parents=True)

    inventory = activation.build_safe_cleanup_inventory()

    assert inventory["status"] == "CLEANUP_INVENTORY_READY"
    assert inventory["pycache_size_bytes"] >= 0
    assert inventory["pytest_cache_size_bytes"] >= 0
    assert inventory["ruff_cache_size_bytes"] >= 0
    assert any(entry["path"].endswith("_stage_child.py") for entry in inventory["temporary_smoke_child_scripts"])
    assert any("ANN_V1_RELEASE_HARDENING" in path for path in inventory["never_delete_candidates"])
