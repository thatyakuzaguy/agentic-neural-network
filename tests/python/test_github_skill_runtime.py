from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.skills import PermissionDecision, SkillAuditLogger, SkillPermissionStore, SkillRegistry
from agentic_network.skills.runtime import execute_skill


def _enabled_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.enable_skill("github")
    return registry


def _store(tmp_path: Path) -> SkillPermissionStore:
    return SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")


def _audit(tmp_path: Path) -> SkillAuditLogger:
    return SkillAuditLogger(tmp_path / "outputs" / "skills")


def _payload(allowed_domains: list[str] | None = None) -> dict[str, object]:
    return {
        "repo": "tiangolo/fastapi",
        "max_files": 20,
        "allowed_domains": allowed_domains
        if allowed_domains is not None
        else ["api.github.com", "github.com", "raw.githubusercontent.com"],
    }


def _fake_fetch_json(url: str) -> object:
    if url.endswith("/repos/tiangolo/fastapi"):
        return {
            "full_name": "tiangolo/fastapi",
            "description": "FastAPI framework, high performance, easy to learn.",
            "default_branch": "master",
            "stargazers_count": 90000,
            "forks_count": 8000,
            "language": "Python",
            "license": {"spdx_id": "MIT"},
            "topics": ["api", "fastapi", "python"],
            "html_url": "https://github.com/tiangolo/fastapi",
        }
    if "/git/trees/master" in url:
        return {
            "tree": [
                {"path": "README.md", "mode": "100644", "type": "blob", "size": 1000},
                {"path": "docs/index.md", "mode": "100644", "type": "blob", "size": 2000},
                {"path": "logo.png", "mode": "100644", "type": "blob", "size": 100},
            ]
        }
    raise AssertionError(f"Unexpected GitHub URL: {url}")


def _allow_both(store: SkillPermissionStore, decision: PermissionDecision = PermissionDecision.ALLOW_ALWAYS) -> None:
    store.set_permission("github", "network", decision)
    store.set_permission("github", "git_read", decision)


def test_lookup_repo_blocked_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    store.set_permission("github", "network", PermissionDecision.ASK_ALWAYS)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "network" in result.errors[0]


def test_lookup_repo_blocked_without_git_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    store.set_permission("github", "network", PermissionDecision.ALLOW_ALWAYS)
    store.set_permission("github", "git_read", PermissionDecision.ASK_ALWAYS)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "git_read" in result.errors[0]


def test_lookup_repo_allowed_once_for_network_and_git_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store, PermissionDecision.ALLOW_ONCE)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "SUCCESS"
    assert result.output["repo"] == "tiangolo/fastapi"
    assert result.output["default_branch"] == "master"
    assert result.output["files_sample"][0]["path"] == "README.md"


def test_allow_once_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store, PermissionDecision.ALLOW_ONCE)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert store.get_permission("github", "network") == PermissionDecision.ASK_ALWAYS
    assert store.get_permission("github", "git_read") == PermissionDecision.ASK_ALWAYS


def test_deny_always_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    store.set_permission("github", "network", PermissionDecision.DENY_ALWAYS)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "Permission denied" in result.errors[0]


def test_allowed_domains_blocks_unapproved_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_fetch(_url: str) -> object:
        raise AssertionError("Blocked domains must not be fetched.")

    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", fail_fetch)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill(
        "github",
        "lookup_repo",
        _payload(["github.com"]),
        registry=_enabled_registry(),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "FAILED"
    assert "blocked_domain:api.github.com" in result.errors


def test_no_git_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GitHub skill must not invoke git clone or any subprocess.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "SUCCESS"


def test_no_terminal_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GitHub skill must not execute terminal.")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.output["terminal_used"] is False


def test_no_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **kwargs: object) -> None:
        if kwargs.get("shell") is True:
            raise AssertionError("shell=True is forbidden.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    assert execute_skill(
        "github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path)
    ).status == "SUCCESS"


def test_no_dependency_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / ".venv").exists()


def test_no_project_modification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    before = Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8")
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8") == before


def test_artifacts_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    root = tmp_path / "outputs" / "skills" / "github"
    assert (root / "github_lookup_request.json").is_file()
    assert (root / "github_lookup_result.json").is_file()
    assert (root / "runtime.json").is_file()
    assert (root / "execution.json").is_file()
    assert (root / "permission_used.json").is_file()
    assert (root / "audit.log").is_file()


def test_metadata_artifact_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    metadata = json.loads((tmp_path / "outputs" / "skills" / "github" / "github_repo_metadata.json").read_text())
    assert metadata["full_name"] == "tiangolo/fastapi"


def test_file_tree_artifact_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    file_tree = json.loads((tmp_path / "outputs" / "skills" / "github" / "github_file_tree.json").read_text())
    assert [item["path"] for item in file_tree] == ["README.md", "docs/index.md"]


def test_result_summary_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    summary = (tmp_path / "outputs" / "skills" / "github" / "result_summary.md").read_text(encoding="utf-8")
    assert "tiangolo/fastapi" in summary
    assert "Files sampled" in summary


def test_sandbox_workspace_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_repo", _payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    workspace = Path(str(result.output["workspace"]))
    assert workspace.is_dir()
    assert workspace.parent == tmp_path / "outputs" / "skills" / "github"
