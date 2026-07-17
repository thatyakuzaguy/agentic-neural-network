from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.skills import PermissionDecision, SkillAuditLogger, SkillPermissionStore, SkillRegistry
from agentic_network.skills.runtime import execute_skill


README = """# FastAPI

Install with pip and run examples.
FastAPI uses dependency injection and routers for API design.
Usage example: create an app and add routes.
"""

PYPROJECT = """[project]
name = "fastapi"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 120
"""


def _enabled_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.enable_skill("github")
    return registry


def _store(tmp_path: Path) -> SkillPermissionStore:
    return SkillPermissionStore(tmp_path / "config" / "ann_skill_permissions.json")


def _audit(tmp_path: Path) -> SkillAuditLogger:
    return SkillAuditLogger(tmp_path / "outputs" / "skills")


def _allow_both(store: SkillPermissionStore, decision: PermissionDecision = PermissionDecision.ALLOW_ALWAYS) -> None:
    store.set_permission("github", "network", decision)
    store.set_permission("github", "git_read", decision)


def _lookup_payload(path: str = "README.md", max_bytes: int = 120_000) -> dict[str, object]:
    return {
        "repo": "tiangolo/fastapi",
        "path": path,
        "ref": "master",
        "allowed_domains": ["api.github.com", "raw.githubusercontent.com"],
        "max_bytes": max_bytes,
    }


def _patterns_payload(paths: list[str] | None = None, max_files: int = 5) -> dict[str, object]:
    return {
        "repo": "tiangolo/fastapi",
        "paths": paths or ["README.md", "pyproject.toml"],
        "ref": "master",
        "allowed_domains": ["api.github.com", "raw.githubusercontent.com"],
        "max_files": max_files,
        "max_bytes_per_file": 120_000,
        "pattern_types": ["project_structure", "testing", "configuration", "api_design", "documentation"],
    }


def _content_response(path: str, content: str, size: int | None = None) -> dict[str, object]:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return {"type": "file", "path": path, "size": size if size is not None else len(content.encode("utf-8")), "encoding": "base64", "content": encoded}


def _fake_fetch_json(url: str) -> object:
    if "/contents/README.md" in url:
        return _content_response("README.md", README)
    if "/contents/pyproject.toml" in url:
        return _content_response("pyproject.toml", PYPROJECT)
    if "/contents/secret.env" in url:
        return _content_response("secret.env", "API_KEY=sk-123456789012345678901234\nSAFE=value\n")
    if "/contents/big.txt" in url:
        return _content_response("big.txt", "x" * 20, size=200_000)
    raise AssertionError(f"Unexpected URL: {url}")


def test_lookup_file_blocked_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    store.set_permission("github", "network", PermissionDecision.ASK_ALWAYS)
    store.set_permission("github", "git_read", PermissionDecision.ALLOW_ALWAYS)

    result = execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "network" in result.errors[0]


def test_lookup_file_blocked_without_git_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    store.set_permission("github", "network", PermissionDecision.ALLOW_ALWAYS)
    store.set_permission("github", "git_read", PermissionDecision.ASK_ALWAYS)

    result = execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "git_read" in result.errors[0]


def test_lookup_file_allowed_once_for_network_and_git_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store, PermissionDecision.ALLOW_ONCE)

    result = execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "SUCCESS"
    assert result.output["path"] == "README.md"
    assert "FastAPI" in result.output["content_preview"]


def test_allow_once_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store, PermissionDecision.ALLOW_ONCE)

    execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert store.get_permission("github", "network") == PermissionDecision.ASK_ALWAYS
    assert store.get_permission("github", "git_read") == PermissionDecision.ASK_ALWAYS


def test_allowed_domains_blocks_unapproved_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_fetch(_url: str) -> object:
        raise AssertionError("Blocked domains must not be fetched.")

    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", fail_fetch)
    store = _store(tmp_path)
    _allow_both(store)
    payload = _lookup_payload()
    payload["allowed_domains"] = ["raw.githubusercontent.com"]

    result = execute_skill("github", "lookup_file", payload, registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "blocked_domain:api.github.com" in result.errors


def test_path_traversal_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_file", _lookup_payload("../README.md"), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "FAILED"
    assert "traversal" in result.errors[0]


def test_binary_file_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_file", _lookup_payload("logo.png"), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "BLOCKED"
    assert "binary_file_blocked" in result.errors


def test_file_too_large_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_file", _lookup_payload("big.txt", max_bytes=1_000), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "FAILED"
    assert "file_too_large" in result.errors[0]


def test_secret_like_content_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_file", _lookup_payload("secret.env"), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "SUCCESS"
    assert result.output["redacted"] is True
    assert "sk-123456789012345678901234" not in result.output["content_preview"]


def test_lookup_file_generates_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    root = tmp_path / "outputs" / "skills" / "github"
    assert (root / "github_file_lookup_request.json").is_file()
    assert (root / "github_file_lookup_result.json").is_file()
    assert (root / "github_file_content_redacted.txt").is_file()


def test_extract_patterns_generates_patterns_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert (tmp_path / "outputs" / "skills" / "github" / "github_patterns.json").is_file()


def test_extract_patterns_detects_testing_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    names = {pattern["name"] for pattern in result.output["patterns"]}
    assert "pytest_usage" in names


def test_extract_patterns_detects_configuration_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    names = {pattern["name"] for pattern in result.output["patterns"]}
    assert "pyproject_sections" in names
    assert "ruff_config" in names


def test_extract_patterns_respects_max_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill(
        "github",
        "extract_patterns",
        _patterns_payload(["README.md", "pyproject.toml"], max_files=1),
        registry=_enabled_registry(),
        store=store,
        audit_logger=_audit(tmp_path),
    )

    assert result.output["files_analyzed"] == ["README.md"]


def test_extract_patterns_does_not_use_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.status == "SUCCESS"
    assert "llm" not in json.dumps(result.output).lower()


def test_no_git_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GitHub pattern extraction must not invoke git clone or subprocess.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    assert execute_skill(
        "github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path)
    ).status == "SUCCESS"


def test_no_terminal_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GitHub pattern extraction must not execute terminal.")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    result = execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert result.output["terminal_used"] is False


def test_no_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **kwargs: object) -> None:
        if kwargs.get("shell") is True:
            raise AssertionError("shell=True is forbidden.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    assert execute_skill("github", "lookup_file", _lookup_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path)).status == "SUCCESS"


def test_no_dependency_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / ".venv").exists()


def test_no_project_modification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentic_network.skills_builtin.github.runtime.fetch_json", _fake_fetch_json)
    before = Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8")
    store = _store(tmp_path)
    _allow_both(store)

    execute_skill("github", "extract_patterns", _patterns_payload(), registry=_enabled_registry(), store=store, audit_logger=_audit(tmp_path))

    assert Path("D:/AgenticEngineeringNetwork/README.md").read_text(encoding="utf-8") == before
