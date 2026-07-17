from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.desktop_app.views.skill_runtime_view import runtime_snapshot
from agentic_network.skills import PermissionDecision, SkillAuditLogger, SkillPermissionStore, SkillRegistry
from agentic_network.skills.runtime import execute_skill
from agentic_network.skills.sandbox import (
    SandboxStatus,
    create_skill_workspace,
    evaluate_skill_sandbox,
    validate_workspace_path,
)


def _enabled_registry(*names: str) -> SkillRegistry:
    registry = SkillRegistry()
    for name in names:
        registry.enable_skill(name)
    return registry


def _store(tmp_path: Path) -> SkillPermissionStore:
    return SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")


def _audit(tmp_path: Path) -> SkillAuditLogger:
    return SkillAuditLogger(tmp_path / "outputs" / "skills")


def test_sandbox_created(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = evaluate_skill_sandbox(
        "github",
        ["git_read"],
        registry=_enabled_registry("github"),
        store=store,
        outputs_root=tmp_path / "outputs" / "skills",
    )

    assert result.status == SandboxStatus.ALLOWED
    assert "git_read" in result.granted_permissions


def test_workspace_created(tmp_path: Path) -> None:
    workspace = create_skill_workspace("github", outputs_root=tmp_path / "outputs" / "skills")

    assert workspace.is_dir()
    assert workspace.name == "workspace"
    assert (workspace / "tmp").is_dir()


def test_permission_allow_always_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill(
        "github",
        "permission_test",
        {"smoke": True},
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "SUCCESS"
    assert result.output["message"] == "permission granted"
    assert store.get_permission("github", "git_read") == PermissionDecision.ALLOW_ALWAYS


def test_permission_deny_always_blocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.DENY_ALWAYS)

    result = execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "FAILED"
    assert "Permission denied" in result.errors[0]


def test_ask_always_blocked_without_approval(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ASK_ALWAYS)

    result = execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "BLOCKED"
    assert "explicit approval" in result.errors[0]


def test_runtime_audit_created(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("documentation", "network", PermissionDecision.ALLOW_ALWAYS)

    execute_skill(
        "documentation",
        "permission_test",
        registry=_enabled_registry("documentation"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert (tmp_path / "outputs" / "skills" / "documentation" / "runtime.json").is_file()
    assert (tmp_path / "outputs" / "skills" / "documentation" / "permission_used.json").is_file()


def test_execution_log_created(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("package_registry", "network", PermissionDecision.ALLOW_ALWAYS)

    execute_skill(
        "package_registry",
        "permission_test",
        registry=_enabled_registry("package_registry"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    execution = tmp_path / "outputs" / "skills" / "package_registry" / "execution.json"
    assert execution.is_file()
    assert json.loads(execution.read_text(encoding="utf-8"))["status"] == "SUCCESS"


def test_block_c_drive(tmp_path: Path) -> None:
    workspace = create_skill_workspace("github", outputs_root=tmp_path / "outputs" / "skills")

    with pytest.raises(ValueError):
        validate_workspace_path("C:\\temp\\skill-output.txt", workspace)


def test_block_mnt_c(tmp_path: Path) -> None:
    workspace = create_skill_workspace("github", outputs_root=tmp_path / "outputs" / "skills")

    with pytest.raises(ValueError):
        validate_workspace_path("/mnt/c/temp/skill-output.txt", workspace)


def test_block_git(tmp_path: Path) -> None:
    workspace = create_skill_workspace("github", outputs_root=tmp_path / "outputs" / "skills")

    with pytest.raises(ValueError):
        validate_workspace_path(workspace / ".git" / "config", workspace)


def test_block_ann_repo_write(tmp_path: Path) -> None:
    workspace = create_skill_workspace("github", outputs_root=tmp_path / "outputs" / "skills")

    with pytest.raises(ValueError):
        validate_workspace_path("D:/AgenticEngineeringNetwork/README.md", workspace)


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill runtime must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    store = _store(tmp_path)
    store.set_permission("internet_search", "network", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill(
        "internet_search",
        "permission_test",
        registry=_enabled_registry("internet_search"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "SUCCESS"
    assert result.output["internet_used"] is False


def test_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill runtime must not execute terminal.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "SUCCESS"
    assert result.output["terminal_used"] is False


def test_no_dependency_install(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("package_registry", "network", PermissionDecision.ALLOW_ALWAYS)

    execute_skill(
        "package_registry",
        "permission_test",
        registry=_enabled_registry("package_registry"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / ".venv").exists()


def test_desktop_runtime_loads(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)
    execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    snapshot = runtime_snapshot(tmp_path / "outputs" / "skills")

    assert "Skill Runtime" in snapshot
    assert "github" in snapshot
    assert "SUCCESS" in snapshot


def test_runtime_smoke_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.status == "SUCCESS"
    assert Path(result.audit_path).is_dir()


def test_github_permission_test_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    assert execute_skill(
        "github",
        "permission_test",
        registry=_enabled_registry("github"),
        store=store,
        audit_logger=_audit(tmp_path),
    ).status == "SUCCESS"


def test_documentation_permission_test_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("documentation", "network", PermissionDecision.ALLOW_ALWAYS)

    assert execute_skill(
        "documentation",
        "permission_test",
        registry=_enabled_registry("documentation"),
        store=store,
        audit_logger=_audit(tmp_path),
    ).status == "SUCCESS"


def test_package_registry_permission_test_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("package_registry", "network", PermissionDecision.ALLOW_ALWAYS)

    assert execute_skill(
        "package_registry",
        "permission_test",
        registry=_enabled_registry("package_registry"),
        store=store,
        audit_logger=_audit(tmp_path),
    ).status == "SUCCESS"


def test_internet_permission_test_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_permission("internet_search", "network", PermissionDecision.ALLOW_ALWAYS)

    assert execute_skill(
        "internet_search",
        "permission_test",
        registry=_enabled_registry("internet_search"),
        store=store,
        audit_logger=_audit(tmp_path),
    ).status == "SUCCESS"
