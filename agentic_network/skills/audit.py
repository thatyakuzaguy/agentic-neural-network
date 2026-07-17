"""Local audit logging for ANN skill permission events."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agentic_network.skills.models import PermissionRequestResult, SkillAuditRecord


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_ROOT = REPO_ROOT / "outputs" / "skills"
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


class SkillAuditLogger:
    """Write local skill audit artifacts."""

    def __init__(self, audit_root: str | Path | None = None) -> None:
        self.audit_root = Path(audit_root or DEFAULT_AUDIT_ROOT).resolve()
        if _has_protected_part(self.audit_root):
            raise ValueError("Skill audit root cannot be inside a protected path.")

    def log_permission_request(
        self,
        result: PermissionRequestResult,
        *,
        started_at: float | None = None,
        success: bool | None = None,
        user_action: str = "",
    ) -> list[str]:
        """Create request/result/audit artifacts for one permission request."""

        duration = round(time.perf_counter() - started_at, 6) if started_at is not None else 0.0
        record = SkillAuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            skill=result.skill_name,
            requested_permission=result.permission,
            decision=result.decision.value,
            duration=duration,
            success=_decision_allows(result.decision.value) if success is None else success,
            errors=result.errors,
            reason=result.reason,
            user_action=user_action or result.decision.value,
        )
        skill_dir = self.audit_root / _safe_segment(result.skill_name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        request_json = skill_dir / "request.json"
        execution_json = skill_dir / "execution.json"
        result_summary = skill_dir / "result_summary.md"
        audit_log = skill_dir / "audit.log"
        history_json = skill_dir / "permission_history.json"
        request_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        execution_json.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
        result_summary.write_text(_summary_markdown(record), encoding="utf-8")
        history = _load_history(history_json)
        history.append(record.to_dict())
        history_json.write_text(json.dumps(history, indent=2), encoding="utf-8")
        with audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return [str(execution_json), str(request_json), str(result_summary), str(audit_log), str(history_json)]

    def log_skill_execution(
        self,
        execution: dict[str, object],
        sandbox: dict[str, object],
    ) -> list[str]:
        """Create runtime audit artifacts for one sandboxed skill execution."""

        skill_name = _safe_segment(str(execution.get("skill", "unknown_skill")))
        skill_dir = self.audit_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        runtime_json = skill_dir / "runtime.json"
        execution_json = skill_dir / "execution.json"
        permission_used_json = skill_dir / "permission_used.json"
        request_json = skill_dir / "request.json"
        result_summary = skill_dir / "result_summary.md"
        audit_log = skill_dir / "audit.log"
        output = execution.get("output", {})
        output_payload = output if isinstance(output, dict) else {}
        runtime_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution": execution,
            "sandbox": sandbox,
            "network_used": bool(output_payload.get("internet_used", False)),
            "terminal_used": bool(output_payload.get("terminal_used", False)),
            "dependency_install_used": bool(output_payload.get("dependency_install_used", False)),
        }
        request_payload = {
            "skill": execution.get("skill"),
            "action": execution.get("action"),
            "requested_permissions": sandbox.get("requested_permissions", []),
        }
        permission_payload = {
            "permission_used": execution.get("permission_used", []),
            "requested_permissions": sandbox.get("requested_permissions", []),
            "granted_permissions": sandbox.get("granted_permissions", []),
            "sandbox_status": sandbox.get("status"),
        }
        runtime_json.write_text(json.dumps(runtime_payload, indent=2), encoding="utf-8")
        execution_json.write_text(json.dumps(execution, indent=2), encoding="utf-8")
        permission_used_json.write_text(json.dumps(permission_payload, indent=2), encoding="utf-8")
        request_json.write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
        result_summary.write_text(_runtime_summary_markdown(execution, sandbox), encoding="utf-8")
        with audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(runtime_payload, sort_keys=True) + "\n")
        return [
            str(runtime_json),
            str(execution_json),
            str(permission_used_json),
            str(request_json),
            str(result_summary),
            str(audit_log),
        ]


def _summary_markdown(record: SkillAuditRecord) -> str:
    return "\n".join(
        [
            "# Skill Permission Audit",
            "",
            f"Timestamp: {record.timestamp}",
            f"Skill: {record.skill}",
            f"Requested permission: {record.requested_permission}",
            f"Decision: {record.decision}",
            f"Duration: {record.duration}s",
            f"Success: {record.success}",
            f"User action: {record.user_action}",
            "",
            "## Reason",
            record.reason,
            "",
            "## Errors",
            *[f"- {error}" for error in record.errors],
            "",
        ]
    )


def _runtime_summary_markdown(execution: dict[str, object], sandbox: dict[str, object]) -> str:
    output = execution.get("output", {})
    output_payload = output if isinstance(output, dict) else {}
    sources = output_payload.get("sources", [])
    source_lines = []
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict):
                source_lines.append(f"- [{item.get('title', item.get('url', 'source'))}]({item.get('url', '')})")
    return "\n".join(
        [
            "# Skill Runtime Audit",
            "",
            f"Skill: {execution.get('skill', 'unknown')}",
            f"Action: {execution.get('action', 'unknown')}",
            f"Status: {execution.get('status', 'unknown')}",
            f"Duration: {execution.get('duration', 0)}s",
            f"Sandbox status: {sandbox.get('status', 'unknown')}",
            f"Reason: {sandbox.get('reason', '')}",
            f"Query: {output_payload.get('query', '')}",
            "",
            "## Summary",
            str(output_payload.get("summary", "")),
            "",
            "## Sources",
            *(source_lines or ["- None"]),
            "",
            "## Safety",
            f"- Internet used: {str(bool(output_payload.get('internet_used', False))).lower()}",
            f"- Terminal used: {str(bool(output_payload.get('terminal_used', False))).lower()}",
            f"- Dependency install used: {str(bool(output_payload.get('dependency_install_used', False))).lower()}",
            "",
            "## Errors",
            *[f"- {error}" for error in execution.get("errors", []) if isinstance(error, str)],
            "",
        ]
    )


def _safe_segment(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char in {"_", "-"})
    return cleaned or "unknown_skill"


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _decision_allows(decision: str) -> bool:
    return decision in {"ALLOW", "ALLOW_ONCE", "ALLOW_ALWAYS"}


def _load_history(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []
