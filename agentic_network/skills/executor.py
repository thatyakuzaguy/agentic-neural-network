"""Executable skill runtime primitives for ANN skills."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.skills.audit import SkillAuditLogger
from agentic_network.skills.models import SkillPermission
from agentic_network.skills.permission_store import SkillPermissionStore
from agentic_network.skills.registry import SkillRegistry
from agentic_network.skills.sandbox import (
    SandboxResult,
    SandboxStatus,
    create_skill_workspace,
    evaluate_skill_sandbox,
)
from agentic_network.skills_builtin.documentation.runtime import documentation_lookup
from agentic_network.skills_builtin.github.runtime import github_extract_patterns, github_lookup_file, github_lookup_repo


EXECUTABLE_ACTIONS = {"permission_test"}
DOCUMENTATION_ACTIONS = {"lookup"}
GITHUB_ACTIONS = {"extract_patterns", "lookup_file", "lookup_repo"}
REQUIRED_PERMISSION_BY_SKILL = {
    "github": SkillPermission.GIT_READ.value,
    "internet_search": SkillPermission.NETWORK.value,
    "documentation": SkillPermission.NETWORK.value,
    "package_registry": SkillPermission.NETWORK.value,
}


@dataclass(frozen=True)
class SkillExecutionResult:
    """Result returned by a sandboxed skill execution."""

    status: str
    skill: str
    action: str
    duration: float
    permission_used: list[str]
    audit_path: str
    output: dict[str, Any]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillExecutor:
    """Execute sandboxed skill actions."""

    def __init__(
        self,
        *,
        registry: SkillRegistry | None = None,
        store: SkillPermissionStore | None = None,
        audit_logger: SkillAuditLogger | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.store = store or SkillPermissionStore()
        self.audit_logger = audit_logger or SkillAuditLogger()

    def execute_skill(
        self,
        skill_name: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> SkillExecutionResult:
        """Run one allowed skill action without terminal or package installs."""

        started = time.perf_counter()
        payload = payload or {}
        requested = [_required_permission(skill_name)]
        workspace = create_skill_workspace(skill_name, outputs_root=self.audit_logger.audit_root)
        if skill_name == "github" and action in GITHUB_ACTIONS:
            return self._execute_github_lookup_repo(action, payload, started, workspace)
        if skill_name == "documentation" and action in DOCUMENTATION_ACTIONS:
            return self._execute_documentation_lookup(action, payload, started, workspace)
        if action not in EXECUTABLE_ACTIONS:
            sandbox = evaluate_skill_sandbox(
                skill_name,
                requested,
                registry=self.registry,
                store=self.store,
                outputs_root=self.audit_logger.audit_root,
            )
            result = _result(
                "BLOCKED",
                skill_name,
                action,
                started,
                sandbox,
                str(workspace),
                {"message": "Unsupported skill action.", "payload_keys": sorted(payload)},
                ["unsupported_action"],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result

        sandbox = evaluate_skill_sandbox(
            skill_name,
            requested,
            registry=self.registry,
            store=self.store,
            outputs_root=self.audit_logger.audit_root,
        )
        if sandbox.status != SandboxStatus.ALLOWED:
            result = _result(
                "BLOCKED" if sandbox.status == SandboxStatus.BLOCKED else "FAILED",
                skill_name,
                action,
                started,
                sandbox,
                str(workspace),
                {"message": "permission denied", "timestamp": _now(), "payload_keys": sorted(payload)},
                [sandbox.reason],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result

        output = {
            "message": "permission granted",
            "timestamp": _now(),
            "workspace": str(workspace),
            "internet_used": False,
            "terminal_used": False,
            "dependency_install_used": False,
            "payload_keys": sorted(payload),
        }
        result = _result("SUCCESS", skill_name, action, started, sandbox, str(workspace), output, [])
        self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
        return result

    def _execute_github_lookup_repo(
        self,
        action: str,
        payload: dict[str, Any],
        started: float,
        workspace: Path,
    ) -> SkillExecutionResult:
        sandbox = evaluate_skill_sandbox(
            "github",
            [SkillPermission.NETWORK.value, SkillPermission.GIT_READ.value],
            registry=self.registry,
            store=self.store,
            outputs_root=self.audit_logger.audit_root,
        )
        if sandbox.status != SandboxStatus.ALLOWED:
            result = _result(
                "BLOCKED",
                "github",
                action,
                started,
                sandbox,
                str(workspace),
                {
                    "message": "github lookup blocked",
                    "repo": str(payload.get("repo", "")),
                    "summary": "",
                    "files_sample": [],
                    "timestamp": _now(),
                    "internet_used": False,
                    "terminal_used": False,
                    "dependency_install_used": False,
                },
                [sandbox.reason],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result
        try:
            if action == "lookup_repo":
                lookup = github_lookup_repo(payload, workspace, workspace.parent)
            elif action == "lookup_file":
                lookup = github_lookup_file(payload, workspace, workspace.parent)
            elif action == "extract_patterns":
                lookup = github_extract_patterns(payload, workspace, workspace.parent)
            else:
                raise ValueError(f"Unsupported GitHub action: {action}")
        except (OSError, ValueError) as exc:
            result = _result(
                "FAILED",
                "github",
                action,
                started,
                sandbox,
                str(workspace),
                {
                    "message": "github lookup failed",
                    "repo": str(payload.get("repo", "")),
                    "path": str(payload.get("path", "")),
                    "paths": payload.get("paths", []),
                    "summary": "",
                    "files_sample": [],
                    "patterns": [],
                    "timestamp": _now(),
                    "internet_used": False,
                    "terminal_used": False,
                    "dependency_install_used": False,
                },
                [str(exc)],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result
        output = lookup.to_dict()
        output.update(
            {
                "message": f"github {action} completed",
                "workspace": str(workspace),
                "audit_path": str(workspace.parent),
                "internet_used": True,
                "terminal_used": False,
                "dependency_install_used": False,
                "timestamp": _now(),
            }
        )
        result = _result(
            _github_execution_status(str(lookup.status)),
            "github",
            action,
            started,
            sandbox,
            str(workspace),
            output,
            lookup.errors,
        )
        self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
        return result

    def _execute_documentation_lookup(
        self,
        action: str,
        payload: dict[str, Any],
        started: float,
        workspace: Path,
    ) -> SkillExecutionResult:
        sandbox = evaluate_skill_sandbox(
            "documentation",
            [SkillPermission.NETWORK.value],
            registry=self.registry,
            store=self.store,
            outputs_root=self.audit_logger.audit_root,
        )
        if sandbox.status != SandboxStatus.ALLOWED:
            result = _result(
                "BLOCKED" if sandbox.status == SandboxStatus.BLOCKED else "FAILED",
                "documentation",
                action,
                started,
                sandbox,
                str(workspace),
                {
                    "message": "documentation lookup blocked",
                    "query": str(payload.get("query", "")),
                    "sources": [],
                    "summary": "",
                    "citations": [],
                    "timestamp": _now(),
                    "internet_used": False,
                    "terminal_used": False,
                    "dependency_install_used": False,
                },
                [sandbox.reason],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result
        try:
            lookup = documentation_lookup(payload, workspace, workspace.parent)
        except (OSError, ValueError) as exc:
            result = _result(
                "FAILED",
                "documentation",
                action,
                started,
                sandbox,
                str(workspace),
                {
                    "message": "documentation lookup failed",
                    "query": str(payload.get("query", "")),
                    "sources": [],
                    "summary": "",
                    "citations": [],
                    "timestamp": _now(),
                    "internet_used": False,
                    "terminal_used": False,
                    "dependency_install_used": False,
                },
                [str(exc)],
            )
            self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
            return result
        output = lookup.to_dict()
        output.update(
            {
                "message": "documentation lookup completed",
                "workspace": str(workspace),
                "internet_used": True,
                "terminal_used": False,
                "dependency_install_used": False,
                "timestamp": _now(),
            }
        )
        result = _result(
            "SUCCESS" if lookup.status == "SUCCESS" else "FAILED",
            "documentation",
            action,
            started,
            sandbox,
            str(workspace),
            output,
            lookup.errors,
        )
        self.audit_logger.log_skill_execution(result.to_dict(), sandbox.to_dict())
        return result


def _required_permission(skill_name: str) -> str:
    return REQUIRED_PERMISSION_BY_SKILL.get(skill_name, SkillPermission.FILESYSTEM_READ.value)


def _result(
    status: str,
    skill_name: str,
    action: str,
    started: float,
    sandbox: SandboxResult,
    workspace: str,
    output: dict[str, Any],
    errors: list[str],
) -> SkillExecutionResult:
    audit_path = str(Path(workspace).parent)
    output = dict(output)
    output.setdefault("workspace", workspace)
    output["sandbox_status"] = sandbox.status.value
    output["sandbox_reason"] = sandbox.reason
    return SkillExecutionResult(
        status=status,
        skill=skill_name,
        action=action,
        duration=round(time.perf_counter() - started, 6),
        permission_used=sandbox.granted_permissions,
        audit_path=audit_path,
        output=output,
        errors=errors,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _github_execution_status(status: str) -> str:
    if status == "SUCCESS":
        return "SUCCESS"
    if status == "BLOCKED":
        return "BLOCKED"
    return "FAILED"
