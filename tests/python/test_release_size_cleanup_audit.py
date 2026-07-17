from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_release_size_cleanup_audit_is_report_only(monkeypatch) -> None:
    monkeypatch.setattr(activation, "_directory_size", lambda *_args, **_kwargs: 1024)
    monkeypatch.setattr(activation, "_estimate_release_candidate_size", lambda *_args, **_kwargs: 2048)
    audit = activation.build_release_size_cleanup_audit()

    assert audit["status"] == "RELEASE_SIZE_CLEANUP_AUDIT_READY"
    assert audit["scan_only"] is True
    assert audit["deletions_performed"] is False
    assert audit["repo_size_bytes"] > 0
    assert audit["release_candidate_estimated_size_bytes"] > 0
    assert any(candidate["path"] == "**/__pycache__" for candidate in audit["safe_cleanup_candidates"])
    assert any("models" in candidate for candidate in audit["never_delete_candidates"])
    assert any("training" in candidate for candidate in audit["never_delete_candidates"])
