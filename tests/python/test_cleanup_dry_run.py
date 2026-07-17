from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_cleanup_dry_run_deletes_nothing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    cache = tmp_path / ".ruff_cache"
    cache.mkdir()
    marker = cache / "marker"
    marker.write_text("cache", encoding="utf-8")

    dry_run = activation.run_safe_cleanup_dry_run()

    assert dry_run["status"] == "CLEANUP_DRY_RUN_READY"
    assert str(cache) in dry_run["dirs_would_delete"]
    assert dry_run["bytes_reclaimable"] >= len("cache")
    assert marker.exists()
    assert dry_run["deletions_performed"] is False
