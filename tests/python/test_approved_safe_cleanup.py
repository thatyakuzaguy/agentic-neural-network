from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_approved_safe_cleanup_requires_confirm_and_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()

    skipped = activation.run_approved_safe_cleanup(confirm_cleanup=False, approval_token=activation.LOCAL_TEST_TOKEN)
    blocked = activation.run_approved_safe_cleanup(confirm_cleanup=True, approval_token="wrong")

    assert skipped["status"] == "CLEANUP_SKIPPED"
    assert blocked["status"] == "CLEANUP_BLOCKED"
    assert cache.exists()


def test_approved_safe_cleanup_deletes_only_safe_temp_and_preserves_release(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs" / "model_activation")
    safe_cache = tmp_path / ".ruff_cache"
    safe_cache.mkdir()
    (safe_cache / "marker").write_text("cache", encoding="utf-8")
    child_run = tmp_path / "outputs" / "model_activation" / "old"
    child_run.mkdir(parents=True)
    child = child_run / "_x_child.py"
    child.write_text("print('x')", encoding="utf-8")
    protected = tmp_path / "outputs" / "model_activation" / "ANN_V1_RELEASE_HARDENING"
    protected.mkdir(parents=True)
    evidence = protected / "324_ann_v1_freeze_manifest.json"
    evidence.write_text("{}", encoding="utf-8")
    models = tmp_path / "models"
    models.mkdir()

    result = activation.run_approved_safe_cleanup(
        confirm_cleanup=True,
        approval_token=activation.LOCAL_TEST_TOKEN,
    )

    assert result["status"] == "CLEANUP_EXECUTED"
    assert not safe_cache.exists()
    assert not child.exists()
    assert evidence.exists()
    assert models.exists()
    assert result["bytes_reclaimed"] > 0
