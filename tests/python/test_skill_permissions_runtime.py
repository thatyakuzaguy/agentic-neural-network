from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.desktop_app.views.skill_audit_view import audit_snapshot
from agentic_network.desktop_app.views.skill_permission_view import (
    permission_snapshot,
    update_skill_permission,
)
from agentic_network.skills import PermissionDecision, SkillAuditLogger, SkillPermissionStore, SkillRegistry
from agentic_network.skills.approval_runtime import request_skill_permission
from agentic_network.skills.permission_store import load_permissions, save_permissions


def _enabled_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.enable_skill("github")
    registry.enable_skill("internet_search")
    return registry


def test_permission_store_loads(tmp_path: Path) -> None:
    path = tmp_path / "config" / "ann_skill_permissions.json"
    path.parent.mkdir()
    path.write_text('{"github": {"git_read": "ASK_ALWAYS"}}', encoding="utf-8")

    assert load_permissions(path)["github"]["git_read"] == "ASK_ALWAYS"


def test_permission_store_saves(tmp_path: Path) -> None:
    path = tmp_path / "config" / "ann_skill_permissions.json"

    save_permissions({"github": {"git_read": "ALLOW_ALWAYS"}}, path)

    assert json.loads(path.read_text(encoding="utf-8"))["github"]["git_read"] == "ALLOW_ALWAYS"


def test_allow_once_works_and_resets(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ONCE)
    result = request_skill_permission(
        "github",
        "git_read",
        "Read repository metadata once.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    assert result.allowed is True
    assert result.decision == PermissionDecision.ALLOW_ONCE
    assert store.get_permission("github", "git_read") == PermissionDecision.ASK_ALWAYS


def test_deny_once_works_and_resets(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.DENY_ONCE)
    result = request_skill_permission(
        "github",
        "git_read",
        "Block one read.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    assert result.allowed is False
    assert result.decision == PermissionDecision.DENY_ONCE
    assert store.get_permission("github", "git_read") == PermissionDecision.ASK_ALWAYS


def test_allow_always_persists(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)
    result = request_skill_permission(
        "github",
        "git_read",
        "Always allow local git read permission.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    assert result.allowed is True
    assert result.persistent is True
    assert store.get_permission("github", "git_read") == PermissionDecision.ALLOW_ALWAYS


def test_deny_always_persists(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("internet_search", "network", PermissionDecision.DENY_ALWAYS)
    result = request_skill_permission(
        "internet_search",
        "network",
        "Always deny network.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    assert result.allowed is False
    assert result.persistent is True
    assert store.get_permission("internet_search", "network") == PermissionDecision.DENY_ALWAYS


def test_reset_returns_ask_always(tmp_path: Path) -> None:
    path = tmp_path / "config" / "ann_skill_permissions.json"
    update_skill_permission("github", "git_read", "Allow Always", store_path=path)
    decision = update_skill_permission("github", "git_read", "Reset", store_path=path)

    assert decision == PermissionDecision.ASK_ALWAYS
    assert SkillPermissionStore(path).get_permission("github", "git_read") == PermissionDecision.ASK_ALWAYS


def test_audit_entry_generated(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ONCE)
    request_skill_permission(
        "github",
        "git_read",
        "Generate audit entry.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    assert (tmp_path / "outputs" / "skills" / "github" / "audit.log").is_file()
    assert "ALLOW_ONCE" in (tmp_path / "outputs" / "skills" / "github" / "audit.log").read_text(encoding="utf-8")


def test_permission_history_generated(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.DENY_ONCE)
    request_skill_permission(
        "github",
        "git_read",
        "Generate permission history.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    history = json.loads(
        (tmp_path / "outputs" / "skills" / "github" / "permission_history.json").read_text(encoding="utf-8")
    )
    assert history[0]["decision"] == "DENY_ONCE"


def test_desktop_loads_permissions(tmp_path: Path) -> None:
    path = tmp_path / "config" / "ann_skill_permissions.json"
    update_skill_permission("github", "git_read", "Allow Always", store_path=path)
    snapshot = permission_snapshot(store=SkillPermissionStore(path))

    assert "github" in snapshot
    assert "current=ALLOW_ALWAYS" in snapshot


def test_desktop_updates_permissions(tmp_path: Path) -> None:
    path = tmp_path / "config" / "ann_skill_permissions.json"
    decision = update_skill_permission("internet_search", "network", "Deny Always", store_path=path)

    assert decision == PermissionDecision.DENY_ALWAYS
    assert SkillPermissionStore(path).get_permission("internet_search", "network") == PermissionDecision.DENY_ALWAYS


def test_invalid_permission_rejected(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")

    with pytest.raises(ValueError):
        store.set_permission("github", "not_real", PermissionDecision.ALLOW_ONCE)


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill permissions must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("internet_search", "network", PermissionDecision.ASK_ALWAYS)

    result = request_skill_permission(
        "internet_search",
        "network",
        "Permission check only.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )
    assert result.decision == PermissionDecision.ASK_ALWAYS


def test_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skill permissions must not execute terminal.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ONCE)

    assert request_skill_permission(
        "github",
        "git_read",
        "Permission check only.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    ).allowed


def test_no_ann_modification(tmp_path: Path) -> None:
    before = Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8")
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ONCE)

    assert Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8") == before


def test_no_git_access(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SkillPermissionStore(tmp_path / ".git" / "ann_skill_permissions.json")


def test_no_dependency_install(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ASK_ALWAYS)

    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / ".venv").exists()


def test_skill_audit_view_reads_history(tmp_path: Path) -> None:
    store = SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ONCE)
    request_skill_permission(
        "github",
        "git_read",
        "Audit view history.",
        registry=_enabled_registry(),
        store=store,
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    snapshot = audit_snapshot(tmp_path / "outputs" / "skills")
    assert "github" in snapshot
    assert "ALLOW_ONCE" in snapshot
