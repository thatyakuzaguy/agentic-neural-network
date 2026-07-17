"""Read-only Project Brain for ANN Desktop.

This module reuses existing run artifacts, workspace registry, and memory-style
outputs. It does not create a new memory system.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.conversation_store import ConversationStore
from agentic_network.desktop_app.workspace_store import ProjectRecord, WorkspaceStore


def get_project_history(
    project_id: str,
    *,
    workspace_store: WorkspaceStore | None = None,
    conversation_store: ConversationStore | None = None,
) -> dict[str, Any]:
    """Return a compact project history snapshot."""

    project = _resolve_project(project_id, workspace_store)
    if project is None:
        return {"project_id": project_id, "status": "MISSING", "runs": [], "conversations": []}
    return {
        "project_id": project.project_id,
        "name": project.name,
        "root_path": project.root_path,
        "runs_path": project.runs_path,
        "runs": get_recent_runs(project_id, workspace_store=workspace_store),
        "conversations": get_recent_conversations(project_id, store=conversation_store),
        "patches": get_recent_patches(project_id, workspace_store=workspace_store),
        "failures": get_recent_failures(project_id, workspace_store=workspace_store),
        "approvals": get_recent_approvals(project_id, workspace_store=workspace_store),
        "retries": get_recent_retries(project_id, workspace_store=workspace_store),
    }


def get_recent_runs(project_id: str, *, workspace_store: WorkspaceStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent run summaries for a registered project."""

    project = _resolve_project(project_id, workspace_store)
    if project is None:
        return []
    runs_root = Path(project.runs_path)
    if not runs_root.is_dir():
        return []
    runs = []
    for run_dir in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        summary = _read_json(run_dir / "summary.json")
        runs.append(
            {
                "run_id": run_dir.name,
                "path": str(run_dir.resolve()),
                "status": summary.get("status") or summary.get("autonomous_loop_status") or summary.get("chat_status") or "UNKNOWN",
                "task": summary.get("task") or summary.get("prompt") or "",
                "artifact_count": _artifact_count(run_dir),
            }
        )
        if len(runs) >= limit:
            break
    return runs


def get_recent_conversations(project_id: str, *, store: ConversationStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent conversations for a project."""

    conversation_store = store or ConversationStore()
    records = [
        record.to_dict()
        for record in conversation_store.list_conversations()
        if record.project_id == project_id
    ]
    return records[:limit]


def get_recent_patches(project_id: str, *, workspace_store: WorkspaceStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent patch artifacts for a project."""

    project = _resolve_project(project_id, workspace_store)
    if project is None:
        return []
    runs_root = Path(project.runs_path)
    patches: list[dict[str, Any]] = []
    if runs_root.is_dir():
        for run_dir in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
            for patch in sorted(run_dir.rglob("*.diff")):
                patches.append({"run_id": run_dir.name, "path": str(patch.resolve()), "size": patch.stat().st_size})
                if len(patches) >= limit:
                    return patches
    return patches


def get_recent_failures(project_id: str, *, workspace_store: WorkspaceStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent failed or blocked run summaries."""

    failures = []
    for run in get_recent_runs(project_id, workspace_store=workspace_store, limit=100):
        status = str(run.get("status", "")).upper()
        if any(marker in status for marker in ("FAILED", "BLOCKED", "TIMEOUT", "ERROR")):
            failures.append(run)
            if len(failures) >= limit:
                break
    return failures


def get_recent_approvals(project_id: str, *, workspace_store: WorkspaceStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent approval-related artifacts for a project."""

    return _recent_artifacts(
        project_id,
        workspace_store=workspace_store,
        limit=limit,
        markers=("approval", "human_approval", "85_confirmation_trace"),
        extensions=(".json", ".md"),
    )


def get_recent_retries(project_id: str, *, workspace_store: WorkspaceStore | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent retry/self-healing artifacts for a project."""

    return _recent_artifacts(
        project_id,
        workspace_store=workspace_store,
        limit=limit,
        markers=("retry", "self_healing", "failure_loop"),
        extensions=(".json", ".md", ".diff"),
    )


def _resolve_project(project_id: str, workspace_store: WorkspaceStore | None) -> ProjectRecord | None:
    store = workspace_store or WorkspaceStore()
    for project in store.load_projects():
        if project.project_id == project_id:
            return project
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_count(run_dir: Path) -> int:
    return sum(1 for path in run_dir.rglob("*") if path.is_file())


def _recent_artifacts(
    project_id: str,
    *,
    workspace_store: WorkspaceStore | None,
    limit: int,
    markers: tuple[str, ...],
    extensions: tuple[str, ...],
) -> list[dict[str, Any]]:
    project = _resolve_project(project_id, workspace_store)
    if project is None:
        return []
    runs_root = Path(project.runs_path)
    if not runs_root.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    lowered_markers = tuple(marker.lower() for marker in markers)
    lowered_extensions = tuple(extension.lower() for extension in extensions)
    for run_dir in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        for path in sorted((item for item in run_dir.rglob("*") if item.is_file()), key=lambda item: item.name):
            lowered = path.name.lower()
            if not lowered.endswith(lowered_extensions):
                continue
            if not any(marker in lowered for marker in lowered_markers):
                continue
            artifacts.append(
                {
                    "run_id": run_dir.name,
                    "name": path.name,
                    "path": str(path.resolve()),
                    "size": path.stat().st_size,
                }
            )
            if len(artifacts) >= limit:
                return artifacts
    return artifacts
