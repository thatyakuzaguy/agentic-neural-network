from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_post_cleanup_release_size_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    (tmp_path / "outputs").mkdir()
    (tmp_path / "agentic_network").mkdir()

    report = activation.build_post_cleanup_release_size_report()

    assert report["status"] == "POST_CLEANUP_RELEASE_SIZE_READY"
    assert "before_cleanup" in report
    assert "after_cleanup" in report
    assert "bytes_reclaimed" in report
    assert report["next_manual_cleanup_options"]
