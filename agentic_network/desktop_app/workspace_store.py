"""Persistent local workspace registry for ANN Desktop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import (
    ProjectManager,
    normalize_workspace_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE_CONFIG = REPO_ROOT / "config" / "ann_workspace.json"
CONFIG_VERSION = 1


@dataclass(frozen=True)
class ProjectRecord:
    """Registered local ANN project."""

    project_id: str
    name: str
    root_path: str
    runs_path: str
    created_at: str
    last_opened_at: str | None
    is_active: bool


class WorkspaceStore:
    """Safe JSON store for authorized local ANN projects."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        project_manager: ProjectManager | None = None,
    ) -> None:
        self.config_path = Path(config_path or DEFAULT_WORKSPACE_CONFIG).resolve()
        self.project_manager = project_manager or ProjectManager()
        self._ensure_config()

    def load_projects(self) -> list[ProjectRecord]:
        payload = self._read_payload()
        projects = payload.get("projects", [])
        if not isinstance(projects, list):
            return []
        records: list[ProjectRecord] = []
        for item in projects:
            if isinstance(item, dict):
                record = _project_from_dict(item)
                if record is not None:
                    records.append(record)
        return records

    def save_projects(self, projects: list[ProjectRecord]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CONFIG_VERSION,
            "projects": [asdict(project) for project in projects],
        }
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_project(self, name: str, root_path: str | Path) -> ProjectRecord:
        validation = self.project_manager.validate_project_root(root_path)
        if not validation.valid or validation.runs_path is None:
            raise ValueError("; ".join(validation.errors) or "Invalid project path.")
        normalized_root = normalize_workspace_path(root_path)
        now = _now()
        project_id = _project_id(normalized_root)
        new_project = ProjectRecord(
            project_id=project_id,
            name=name.strip() or normalized_root.name or "ANN Project",
            root_path=str(normalized_root),
            runs_path=validation.runs_path,
            created_at=now,
            last_opened_at=None,
            is_active=False,
        )
        projects = [project for project in self.load_projects() if project.project_id != project_id]
        projects.append(new_project)
        self.save_projects(projects)
        return new_project

    def remove_project(self, project_id: str) -> None:
        projects = [project for project in self.load_projects() if project.project_id != project_id]
        self.save_projects(projects)

    def set_active_project(self, project_id: str) -> ProjectRecord:
        now = _now()
        projects = self.load_projects()
        active: ProjectRecord | None = None
        updated: list[ProjectRecord] = []
        for project in projects:
            is_active = project.project_id == project_id
            record = ProjectRecord(
                project_id=project.project_id,
                name=project.name,
                root_path=project.root_path,
                runs_path=project.runs_path,
                created_at=project.created_at,
                last_opened_at=now if is_active else project.last_opened_at,
                is_active=is_active,
            )
            if is_active:
                active = record
            updated.append(record)
        if active is None:
            raise KeyError(f"Unknown project id: {project_id}")
        self.save_projects(updated)
        return active

    def get_active_project(self) -> ProjectRecord | None:
        for project in self.load_projects():
            if project.is_active:
                return project
        return None

    def _ensure_config(self) -> None:
        if self.config_path.exists():
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps({"version": CONFIG_VERSION, "projects": []}, indent=2),
            encoding="utf-8",
        )

    def _read_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": CONFIG_VERSION, "projects": []}
        return payload if isinstance(payload, dict) else {"version": CONFIG_VERSION, "projects": []}


def _project_from_dict(payload: dict[str, Any]) -> ProjectRecord | None:
    required = ("project_id", "name", "root_path", "runs_path", "created_at")
    if not all(isinstance(payload.get(key), str) and payload.get(key) for key in required):
        return None
    last_opened = payload.get("last_opened_at")
    return ProjectRecord(
        project_id=str(payload["project_id"]),
        name=str(payload["name"]),
        root_path=str(payload["root_path"]),
        runs_path=str(payload["runs_path"]),
        created_at=str(payload["created_at"]),
        last_opened_at=str(last_opened) if isinstance(last_opened, str) and last_opened else None,
        is_active=payload.get("is_active") is True,
    )


def _project_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).lower().encode("utf-8")).hexdigest()[:12]
    return f"project_{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
