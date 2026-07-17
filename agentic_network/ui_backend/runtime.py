"""Read-only local dashboard backend for ANN runs.

The v5.0 UI intentionally exposes only run metadata and text artifacts. It does
not apply patches, execute commands, approve changes, or write repository files.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
DEFAULT_STATIC_ROOT = REPO_ROOT / "agentic_network" / "ui_static"

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_RELATIVE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-/]+$")
ARTIFACT_EXTENSIONS = {".json", ".log", ".md", ".txt"}
PATCH_EXTENSIONS = {".diff", ".patch"}
BLOCKED_PARTS = {".git", "knowledge", "memory", "models", "training", "unsloth_compiled_cache"}
PATCHES_DIR = "patches"

STATUS_FIELDS = (
    "autonomous_loop_status",
    "patch_quality_decision",
    "patch_apply_status",
    "test_runner_status",
    "patch_approval_decision",
    "patch_approval_status",
    "self_healing_status",
    "merge_readiness_status",
    "parallel_review_status",
    "parallel_review_decision",
    "parallel_review_confidence",
    "consensus_status",
    "consensus_decision",
    "consensus_confidence",
    "action_plan_status",
    "action_plan_next_action",
    "action_plan_executable",
    "action_plan_blocked",
)


def create_app(
    *,
    runs_root: Path | None = None,
    static_root: Path | None = None,
) -> FastAPI:
    """Create the local read-only FastAPI app."""

    resolved_runs_root = _resolve_root(runs_root or DEFAULT_RUNS_ROOT)
    resolved_static_root = _resolve_root(static_root or DEFAULT_STATIC_ROOT)
    from agentic_network.ui_backend.approval_runtime import (
        approve_patch,
        get_patch_metadata,
        list_approvals,
    )
    from agentic_network.terminal_agent.runtime import run_terminal_command

    app = FastAPI(
        title="Agentic Engineering Network UI",
        version="5.0.0",
        description="Local read-only dashboard for ANN runs.",
    )

    @app.get("/api/runs")
    def api_list_runs() -> dict[str, Any]:
        return {"runs": list_runs(resolved_runs_root)}

    @app.get("/api/runs/{run_id}")
    def api_get_run(run_id: str) -> dict[str, Any]:
        return get_run_detail(run_id, resolved_runs_root)

    @app.get("/api/runs/{run_id}/action-plan")
    def api_get_action_plan(run_id: str) -> dict[str, Any]:
        return get_action_plan_detail(run_id, resolved_runs_root)

    @app.get("/api/runs/{run_id}/artifact/{artifact_name:path}", response_class=PlainTextResponse)
    def api_get_artifact(run_id: str, artifact_name: str) -> str:
        return read_artifact(run_id, artifact_name, resolved_runs_root)

    @app.get("/api/runs/{run_id}/patch/{patch_name:path}/metadata")
    def api_get_patch_metadata(run_id: str, patch_name: str) -> dict[str, Any]:
        return get_patch_metadata(run_id, patch_name, resolved_runs_root)

    @app.get("/api/runs/{run_id}/patch/{patch_name:path}", response_class=PlainTextResponse)
    def api_get_patch(run_id: str, patch_name: str) -> str:
        return read_patch(run_id, patch_name, resolved_runs_root)

    @app.post("/api/runs/{run_id}/approve")
    def api_approve_patch(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return approve_patch(run_id, payload, resolved_runs_root)

    @app.get("/api/runs/{run_id}/approvals")
    def api_list_approvals(run_id: str) -> dict[str, Any]:
        return list_approvals(run_id, resolved_runs_root)

    @app.post("/api/terminal/run")
    def api_run_terminal(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirm_execute") is not True:
            raise HTTPException(status_code=400, detail="confirm_execute must be true.")
        command = payload.get("command")
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise HTTPException(status_code=400, detail="command must be a list of strings.")
        result = run_terminal_command(
            command=command,
            cwd=str(payload.get("cwd") or "."),
            timeout_seconds=int(payload.get("timeout_seconds") or 120),
            allow_write=payload.get("allow_write") is True,
            run_id=payload.get("run_id") if isinstance(payload.get("run_id"), str) else None,
        )
        return result.to_dict()

    if resolved_static_root.exists():
        app.mount("/static", StaticFiles(directory=resolved_static_root), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = _safe_static_path(resolved_static_root, "index.html")
        return FileResponse(index_path)

    return app


def list_runs(runs_root: Path | None = None) -> list[dict[str, Any]]:
    """List valid ANN run directories newest first."""

    root = _resolve_runs_root(runs_root)
    if not root.exists():
        return []
    runs = [_run_summary(path, root) for path in root.iterdir() if _is_run_dir(path)]
    return sorted(runs, key=lambda item: str(item.get("timestamp") or item["run_id"]), reverse=True)


def get_run_detail(run_id: str, runs_root: Path | None = None) -> dict[str, Any]:
    """Return parsed summary, artifacts, patches, and key statuses for one run."""

    root = _resolve_runs_root(runs_root)
    run_dir = _resolve_run_dir(root, run_id)
    summary = _read_summary(run_dir)
    parallel_review = _read_parallel_review(run_dir)
    consensus = _read_consensus(run_dir)
    action_plan = _read_action_plan(run_dir)
    action_plan_view = _action_plan_payload(action_plan)
    return {
        **_run_summary(run_dir, root, summary=summary),
        "summary": summary,
        "artifacts": _available_artifacts(run_dir),
        "patches": _available_patches(run_dir),
        "statuses": _key_statuses(
            summary,
            parallel_review=parallel_review,
            consensus=consensus,
            action_plan=action_plan,
        ),
        "warnings": _warnings_from_summary(summary),
        "errors": _errors_from_summary(summary),
        "parallel_review": parallel_review,
        "consensus": consensus,
        "action_plan": action_plan,
        "action_plan_view": action_plan_view,
    }


def get_action_plan_detail(run_id: str, runs_root: Path | None = None) -> dict[str, Any]:
    """Return UI-friendly Action Plan data for one run."""

    root = _resolve_runs_root(runs_root)
    run_dir = _resolve_run_dir(root, run_id)
    return _action_plan_payload(_read_action_plan(run_dir))


def read_artifact(run_id: str, artifact_name: str, runs_root: Path | None = None) -> str:
    """Read a safe text artifact from a run."""

    root = _resolve_runs_root(runs_root)
    run_dir = _resolve_run_dir(root, run_id)
    path = _safe_child_path(run_dir, artifact_name, allowed_extensions=ARTIFACT_EXTENSIONS)
    if _is_patch_path(run_dir, path):
        raise HTTPException(status_code=404, detail="Use the patch endpoint for patch files.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return path.read_text(encoding="utf-8", errors="replace")


def read_patch(run_id: str, patch_name: str, runs_root: Path | None = None) -> str:
    """Read a safe patch diff from a run's patches directory."""

    root = _resolve_runs_root(runs_root)
    run_dir = _resolve_run_dir(root, run_id)
    patches_root = (run_dir / PATCHES_DIR).resolve()
    path = _safe_child_path(patches_root, patch_name, allowed_extensions=PATCH_EXTENSIONS)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Patch not found.")
    return path.read_text(encoding="utf-8", errors="replace")


def _run_summary(run_dir: Path, runs_root: Path, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _read_summary(run_dir) if summary is None else summary
    return {
        "run_id": run_dir.name,
        "path": _display_path(run_dir, runs_root),
        "timestamp": _timestamp_for_run(run_dir, payload),
        "task": _task_for_run(payload),
        "autonomous_loop_status": _status_value(payload, "autonomous_loop_status"),
        "patch_quality_decision": _status_value(payload, "patch_quality_decision"),
        "patch_apply_status": _status_value(payload, "patch_apply_status"),
        "test_runner_status": _status_value(payload, "test_runner_status"),
    }


def _is_run_dir(path: Path) -> bool:
    if not path.is_dir() or not _valid_run_id(path.name):
        return False
    if (path / "summary.json").is_file():
        return True
    if _available_artifacts(path) or _available_patches(path):
        return True
    return False


def _read_summary(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "summary.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"summary_error": "invalid_summary_json"}
    return payload if isinstance(payload, dict) else {"summary_error": "summary_not_object"}


def _available_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or _is_patch_path(run_dir, path):
            continue
        try:
            relative = path.relative_to(run_dir)
        except ValueError:
            continue
        if not _safe_relative_parts(relative) or path.suffix.lower() not in ARTIFACT_EXTENSIONS:
            continue
        artifacts.append(_file_entry(path, relative))
    return artifacts


def _available_patches(run_dir: Path) -> list[dict[str, Any]]:
    patches_root = run_dir / PATCHES_DIR
    if not patches_root.is_dir():
        return []
    patches: list[dict[str, Any]] = []
    for path in sorted(patches_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in PATCH_EXTENSIONS:
            continue
        try:
            relative = path.relative_to(patches_root)
        except ValueError:
            continue
        if _safe_relative_parts(relative):
            patches.append(_file_entry(path, relative))
    return patches


def _file_entry(path: Path, relative: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": relative.as_posix(),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _resolve_runs_root(runs_root: Path | None) -> Path:
    root = _resolve_root(runs_root or DEFAULT_RUNS_ROOT)
    if _has_blocked_part(root):
        raise HTTPException(status_code=403, detail="Runs root is blocked.")
    return root


def _resolve_root(root: Path) -> Path:
    return Path(root).resolve()


def _resolve_run_dir(runs_root: Path, run_id: str) -> Path:
    if not _valid_run_id(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    run_dir = (runs_root / run_id).resolve()
    if not _is_relative_to(run_dir, runs_root) or not _is_run_dir(run_dir):
        raise HTTPException(status_code=404, detail="Run not found.")
    return run_dir


def _safe_child_path(parent: Path, relative_name: str, *, allowed_extensions: set[str]) -> Path:
    if not _valid_relative_name(relative_name):
        raise HTTPException(status_code=400, detail="Invalid file name.")
    candidate = (parent / relative_name).resolve()
    if not _is_relative_to(candidate, parent):
        raise HTTPException(status_code=403, detail="Path traversal blocked.")
    try:
        relative = candidate.relative_to(parent)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path traversal blocked.") from exc
    if not _safe_relative_parts(relative) or candidate.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=403, detail="File is not allowed.")
    return candidate


def _safe_static_path(static_root: Path, filename: str) -> Path:
    path = _safe_child_path(static_root, filename, allowed_extensions={".html"})
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Static UI not found.")
    return path


def _valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id)) and run_id not in {".", ".."}


def _valid_relative_name(name: str) -> bool:
    if not name or "\\" in name:
        return False
    if name.startswith("/") or ":" in name:
        return False
    return bool(SAFE_RELATIVE_NAME_PATTERN.fullmatch(name))


def _safe_relative_parts(path: Path) -> bool:
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return not any(part.lower() in BLOCKED_PARTS for part in parts)


def _has_blocked_part(path: Path) -> bool:
    return any(part.lower() in BLOCKED_PARTS for part in path.parts)


def _is_patch_path(run_dir: Path, path: Path) -> bool:
    try:
        path.relative_to(run_dir / PATCHES_DIR)
        return True
    except ValueError:
        return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _display_path(path: Path, runs_root: Path) -> str:
    try:
        return path.relative_to(runs_root.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _timestamp_for_run(run_dir: Path, summary: dict[str, Any]) -> str:
    for key in ("timestamp", "created_at", "started_at"):
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return run_dir.name


def _task_for_run(summary: dict[str, Any]) -> str:
    for key in ("task", "idea", "prompt", "user_request", "original_prompt"):
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unknown task"


def _key_statuses(
    summary: dict[str, Any],
    *,
    parallel_review: dict[str, Any] | None = None,
    consensus: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    statuses = {field: _status_value(summary, field) for field in STATUS_FIELDS}
    if parallel_review:
        statuses["parallel_review_status"] = _status_value(parallel_review, "status")
        statuses["parallel_review_decision"] = _status_value(parallel_review, "decision")
        statuses["parallel_review_confidence"] = _status_value(parallel_review, "confidence")
    if consensus:
        statuses["consensus_status"] = _status_value(consensus, "status")
        statuses["consensus_decision"] = _status_value(consensus, "consensus_decision")
        statuses["consensus_confidence"] = _status_value(consensus, "confidence")
    if action_plan:
        statuses["action_plan_status"] = _status_value(action_plan, "status")
        statuses["action_plan_next_action"] = _status_value(action_plan, "recommended_next_action")
        statuses["action_plan_executable"] = _status_value(action_plan, "executable")
        statuses["action_plan_blocked"] = _status_value(action_plan, "blocked")
    return statuses


def _status_value(summary: dict[str, Any], field: str) -> str:
    value = summary.get(field)
    if isinstance(value, bool):
        return str(value)
    return value.strip() if isinstance(value, str) and value.strip() else "UNKNOWN"


def _read_parallel_review(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "37_parallel_review.json"
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "INVALID", "decision": "BLOCKED", "confidence": "Low"}
    return payload if isinstance(payload, dict) else {}


def _read_consensus(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "38_consensus_decision.json"
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "INVALID", "consensus_decision": "BLOCKED", "confidence": "Low"}
    return payload if isinstance(payload, dict) else {}


def _read_action_plan(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "39_action_plan.json"
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "INVALID",
            "recommended_next_action": "manual_review",
            "executable": False,
            "blocked": True,
        }
    return payload if isinstance(payload, dict) else {}


def _action_plan_payload(action_plan: dict[str, Any]) -> dict[str, Any]:
    if not action_plan:
        return {
            "status": "MISSING",
            "next_action": "missing_action_plan",
            "user_message": "No action plan is available for this run yet.",
            "blocked": True,
            "executable": False,
            "requires": {
                "human": False,
                "terminal": False,
                "approval": False,
                "apply": False,
            },
            "blocking_reasons": ["39_action_plan.json is missing."],
            "planned_steps": [],
            "allowed_actions": ["inspect_artifacts"],
            "blocked_actions": ["execute_terminal", "apply_patch", "approve_patch"],
            "prerequisites": ["run_action_planner"],
            "risks": ["The UI cannot recommend a next step without 39_action_plan.json."],
            "expected_artifacts": ["39_action_plan.md", "39_action_plan.json"],
            "responsible_subsystems": ["Action Planner"],
        }
    blocked = _bool_field(action_plan, "blocked")
    executable = _bool_field(action_plan, "executable") and not blocked
    return {
        "status": _string_field(action_plan, "status", default="UNKNOWN"),
        "next_action": _string_field(action_plan, "recommended_next_action", default="manual_review"),
        "user_message": _string_field(action_plan, "user_message", default="Review the action plan artifact."),
        "blocked": blocked,
        "executable": executable,
        "requires": {
            "human": _bool_field(action_plan, "requires_human"),
            "terminal": _bool_field(action_plan, "requires_terminal"),
            "approval": _bool_field(action_plan, "requires_approval"),
            "apply": _bool_field(action_plan, "requires_apply"),
        },
        "blocking_reasons": _list_field(action_plan, "blocking_reasons"),
        "planned_steps": _steps_field(action_plan.get("planned_steps")),
        "allowed_actions": _list_field(action_plan, "allowed_actions"),
        "blocked_actions": _list_field(action_plan, "blocked_actions"),
        "prerequisites": _list_field(action_plan, "prerequisites"),
        "risks": _list_field(action_plan, "risks"),
        "expected_artifacts": _list_field(action_plan, "expected_artifacts"),
        "responsible_subsystems": _list_field(action_plan, "responsible_subsystems"),
    }


def _string_field(payload: dict[str, Any], key: str, *, default: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _bool_field(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _list_field(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _steps_field(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            steps.append(
                {
                    "order": item.get("order") if isinstance(item.get("order"), int) else index,
                    "description": str(item.get("description") or "").strip(),
                    "subsystem": str(item.get("subsystem") or "").strip(),
                    "action_type": str(item.get("action_type") or "").strip(),
                }
            )
        elif str(item).strip():
            steps.append(
                {
                    "order": index,
                    "description": str(item).strip(),
                    "subsystem": "",
                    "action_type": "",
                }
            )
    return steps


def _warnings_from_summary(summary: dict[str, Any]) -> list[str]:
    return _flatten_status_items(summary, suffixes=("_warnings", "_warning"))


def _errors_from_summary(summary: dict[str, Any]) -> list[str]:
    return _flatten_status_items(summary, suffixes=("_errors", "_validation_errors", "_error"))


def _flatten_status_items(summary: dict[str, Any], *, suffixes: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for key, value in summary.items():
        if not any(key.endswith(suffix) for suffix in suffixes):
            continue
        if isinstance(value, list):
            items.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            items.append(value.strip())
    return _dedupe(items)[:20]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result
