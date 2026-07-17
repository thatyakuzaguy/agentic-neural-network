from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.skills import (
    PermissionDecision,
    PermissionEngine,
    SkillAuditLogger,
    SkillRegistry,
    SkillsManager,
)


def _manifest(path: Path, name: str = "demo_skill") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"name: {name}",
                "version: 1.0",
                "description: Demo skill manifest.",
                "enabled: false",
                "requires_user_approval: true",
                "audit_enabled: true",
                "permissions:",
                "  network: ASK_ALWAYS",
                "  filesystem_read: ALLOW",
                "  filesystem_write: DENY",
                "  git_read: ASK_ALWAYS",
                "  git_write: DENY",
                "  terminal_execute: DENY",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _config(path: Path, permissions: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": permissions}, indent=2), encoding="utf-8")
    return path


def test_register_skill(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    skill = registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))

    assert skill.name == "demo_skill"
    assert registry.get_skill("demo_skill") is not None


def test_enable_skill(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))

    skill = registry.enable_skill("demo_skill")

    assert skill.enabled is True


def test_disable_skill(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")

    skill = registry.disable_skill("demo_skill")

    assert skill.enabled is False


def test_list_skills_includes_builtins() -> None:
    names = {skill.name for skill in SkillRegistry().list_skills()}

    assert {"internet_search", "github", "documentation", "package_registry"} <= names


def test_permission_request_allow(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")
    engine = PermissionEngine(
        registry,
        _config(tmp_path / "config" / "ann_skills.json", {"demo_skill.filesystem_read": "ALLOW"}),
    )

    result = engine.request_permission("demo_skill", "filesystem_read", "Read docs.")

    assert result.decision == PermissionDecision.ALLOW


def test_permission_request_deny(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")
    engine = PermissionEngine(
        registry,
        _config(tmp_path / "config" / "ann_skills.json", {"demo_skill.filesystem_write": "DENY"}),
    )

    result = engine.request_permission("demo_skill", "filesystem_write", "Write a file.")

    assert result.decision == PermissionDecision.DENY


def test_permission_request_ask_always(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")
    engine = PermissionEngine(
        registry,
        _config(tmp_path / "config" / "ann_skills.json", {"demo_skill.network": "ASK_ALWAYS"}),
    )

    result = engine.request_permission("demo_skill", "network", "Search docs.")

    assert result.decision == PermissionDecision.ASK_ALWAYS


def test_audit_log_generated(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")
    manager = SkillsManager(
        registry=registry,
        permission_engine=PermissionEngine(
            registry,
            _config(tmp_path / "config" / "ann_skills.json", {"demo_skill.filesystem_read": "ALLOW"}),
        ),
        audit_logger=SkillAuditLogger(tmp_path / "outputs" / "skills"),
    )

    result = manager.request_permission("demo_skill", "filesystem_read", "Read local manifest.")

    assert result.decision == PermissionDecision.ALLOW
    assert (tmp_path / "outputs" / "skills" / "demo_skill" / "execution.json").is_file()
    assert (tmp_path / "outputs" / "skills" / "demo_skill" / "request.json").is_file()
    assert (tmp_path / "outputs" / "skills" / "demo_skill" / "result_summary.md").is_file()
    assert (tmp_path / "outputs" / "skills" / "demo_skill" / "audit.log").is_file()


def test_invalid_manifest_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "skill" / "manifest.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("name: bad\n", encoding="utf-8")

    with pytest.raises(ValueError):
        SkillRegistry(builtin_root=tmp_path / "none").register_skill(bad)


def test_desktop_loads_skills() -> None:
    from agentic_network.desktop_app.navigation import navigation_labels
    from agentic_network.desktop_app.views.skills_view import skills_snapshot

    snapshot = skills_snapshot()

    assert "Skills" in navigation_labels()
    assert "internet_search" in snapshot
    assert "github" in snapshot


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skills foundation must not use internet.")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = PermissionEngine(registry, _config(tmp_path / "config.json", {})).request_permission(
        "demo_skill", "network", "Check permission only."
    )
    assert result.decision == PermissionDecision.ASK_ALWAYS


def test_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))
    registry.enable_skill("demo_skill")

    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Skills foundation must not execute terminal.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    result = PermissionEngine(registry, _config(tmp_path / "config.json", {})).request_permission(
        "demo_skill", "terminal_execute", "Check permission only."
    )
    assert result.decision == PermissionDecision.DENY


def test_no_ann_modification(tmp_path: Path) -> None:
    before = Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8")
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))

    assert Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8") == before


def test_no_git_access(tmp_path: Path) -> None:
    protected = tmp_path / ".git" / "manifest.yaml"
    protected.parent.mkdir()
    protected.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        SkillRegistry(builtin_root=tmp_path / "none").register_skill(protected)


def test_no_dependency_installation(tmp_path: Path) -> None:
    registry = SkillRegistry(builtin_root=tmp_path / "none")
    registry.register_skill(_manifest(tmp_path / "skill" / "manifest.yaml"))

    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / ".venv").exists()
