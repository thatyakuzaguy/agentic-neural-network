from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

import agentic_network.project_builder_orchestrator.runtime as orchestrator_runtime
from agentic_network.project_builder_orchestrator.runtime import run_end_to_end_project
from agentic_network.skill_evidence_agent.runtime import build_skill_evidence_bundle


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _documentation_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "skills" / "documentation"
    _write_json(
        root / "lookup_result.json",
        {
            "status": "SUCCESS",
            "query": "FastAPI dependency injection",
            "summary": "FastAPI dependency injection documentation summary.",
            "citations": ["https://fastapi.tiangolo.com/tutorial/dependencies/"],
            "errors": [],
        },
    )
    _write_json(
        root / "sources.json",
        [{"url": "https://fastapi.tiangolo.com/tutorial/dependencies/", "title": "Dependencies - FastAPI"}],
    )
    (root / "result_summary.md").write_text("# Documentation Lookup Result\n", encoding="utf-8")
    return root


def _github_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "skills" / "github"
    _write_json(
        root / "github_lookup_result.json",
        {
            "status": "SUCCESS",
            "repo": "tiangolo/fastapi",
            "description": "FastAPI framework.",
            "summary": "FastAPI repository metadata summary.",
            "errors": [],
        },
    )
    _write_json(root / "github_repo_metadata.json", {"full_name": "tiangolo/fastapi", "language": "Python"})
    _write_json(root / "github_file_tree.json", [{"path": "README.md", "size": 1000}])
    _write_json(
        root / "github_file_lookup_result.json",
        {
            "status": "SUCCESS",
            "repo": "tiangolo/fastapi",
            "path": "README.md",
            "content_preview": "# FastAPI\nUse pytest and pyproject patterns.",
            "redacted": False,
            "errors": [],
        },
    )
    _write_json(
        root / "github_patterns.json",
        {
            "status": "SUCCESS",
            "repo": "tiangolo/fastapi",
            "patterns": [{"pattern_type": "testing", "name": "pytest_usage", "file": "pyproject.toml"}],
            "summary": "Detected testing and configuration patterns.",
            "recommendations": ["Use pytest-based test planning."],
            "evidence_files": ["pyproject.toml"],
            "errors": [],
        },
    )
    (root / "github_pattern_summary.md").write_text("# GitHub Pattern Extraction Result\n", encoding="utf-8")
    return root


def _allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_CREATION_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_SCAFFOLD_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_PATCH_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_SELF_HEALING_TARGETS", "1")
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    monkeypatch.setenv("ANN_PROJECT_PATCH_TOKEN", "local-test-token")


def test_empty_skill_outputs_returns_empty(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([tmp_path / "outputs" / "skills" / "missing"], run_dir=tmp_path / "run")

    assert result.status == "EMPTY"
    assert result.evidence_items == []


def test_reads_documentation_lookup_artifacts(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_documentation_root(tmp_path)], run_dir=tmp_path / "run")

    assert result.status == "VALID"
    assert any(item["evidence_type"] == "documentation" for item in result.evidence_items)


def test_reads_github_repo_metadata_artifacts(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run")

    assert any(item["evidence_type"] == "github_metadata" for item in result.evidence_items)


def test_reads_github_file_lookup_artifacts(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run")

    assert any(item["evidence_type"] == "github_file" for item in result.evidence_items)


def test_reads_github_pattern_artifacts(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run")

    assert any(item["evidence_type"] == "github_pattern" for item in result.evidence_items)


def test_generates_bundle_md_and_json(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_documentation_root(tmp_path)], run_dir=tmp_path / "run")

    assert any(path.endswith("70_skill_evidence_bundle.md") for path in result.artifacts)
    assert any(path.endswith("70_skill_evidence_bundle.json") for path in result.artifacts)


def test_generates_summary_md(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_documentation_root(tmp_path)], run_dir=tmp_path / "run")

    assert any(path.endswith("71_skill_evidence_summary.md") for path in result.artifacts)


def test_blocks_path_traversal(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([tmp_path / ".." / "skills"], run_dir=tmp_path / "run")

    assert result.status == "BLOCKED"


def test_blocks_git(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([tmp_path / ".git" / "skills"], run_dir=tmp_path / "run")

    assert result.status == "BLOCKED"


def test_blocks_models(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([tmp_path / "models" / "skills"], run_dir=tmp_path / "run")

    assert result.status == "BLOCKED"


def test_blocks_training_datasets(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([tmp_path / "training" / "datasets" / "skills"], run_dir=tmp_path / "run")

    assert result.status == "BLOCKED"


def test_does_not_execute_documentation_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_imported_skill(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill evidence must not execute documentation skill.")

    monkeypatch.setattr("agentic_network.skills_builtin.documentation.runtime.documentation_lookup", fail_imported_skill)

    assert build_skill_evidence_bundle([_documentation_root(tmp_path)], run_dir=tmp_path / "run").status == "VALID"


def test_does_not_execute_github_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_imported_skill(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill evidence must not execute GitHub skill.")

    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.github_lookup_repo", fail_imported_skill)

    assert build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run").status == "VALID"


def test_does_not_use_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill evidence must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run").status == "VALID"


def test_does_not_execute_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill evidence must not execute terminal.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run").status == "VALID"


def test_does_not_apply_patches(tmp_path: Path) -> None:
    result = build_skill_evidence_bundle([_github_root(tmp_path)], run_dir=tmp_path / "run")

    assert result.status == "VALID"
    assert not (tmp_path / "run" / "patches").exists()


def test_integrates_with_e2e_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    root = _github_root(tmp_path)

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
        use_skill_evidence=True,
        skill_evidence_roots=[root],
    )

    assert result.skill_evidence_used is True
    assert result.skill_evidence_status == "VALID"
    assert result.skill_evidence_artifacts
    assert "consult_skill_evidence" in result.recommended_next_action


def test_e2e_without_skill_evidence_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)

    result = run_end_to_end_project(
        "Create a local CRM",
        tmp_path / "targets",
        approval_token="local-test-token",
        max_features=1,
        max_retries=1,
        confirm_create=True,
        confirm_apply=True,
        confirm_tests=True,
        use_skill_evidence=False,
    )

    assert result.skill_evidence_used is False
    assert result.skill_evidence_status == "SKIPPED"
    assert result.recommended_next_action == "add_project_tests"


def test_desktop_skill_evidence_view_loads(tmp_path: Path) -> None:
    from agentic_network.desktop_app.views.skill_evidence_view import (
        SKILL_EVIDENCE_MESSAGE,
        skill_evidence_snapshot,
    )

    result = build_skill_evidence_bundle([_documentation_root(tmp_path)], run_dir=tmp_path / "evidence")
    snapshot = skill_evidence_snapshot(Path(result.artifacts[0]).parent)

    assert "Skill Evidence" in snapshot
    assert "read-only advisory" in SKILL_EVIDENCE_MESSAGE


def test_project_builder_import_does_not_expose_execution_methods() -> None:
    assert hasattr(orchestrator_runtime, "run_end_to_end_project")
