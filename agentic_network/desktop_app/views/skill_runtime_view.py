"""Skill Runtime status view for ANN Desktop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_network.skills.audit import DEFAULT_AUDIT_ROOT

try:  # pragma: no cover - covered by manual desktop smoke.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


SKILL_RUNTIME_MESSAGE = (
    "Skill Runtime shows sandbox state and skill execution artifacts only. "
    "It does not execute automatically, terminal commands, git operations, or dependency installation."
)


def runtime_snapshot(audit_root: str | Path | None = None) -> str:
    """Render the latest local skill runtime artifacts."""

    root = Path(audit_root or DEFAULT_AUDIT_ROOT).resolve()
    lines = ["Skill Runtime", "", SKILL_RUNTIME_MESSAGE, ""]
    if not root.is_dir():
        lines.append("No skill runtime artifacts found.")
        return "\n".join(lines)
    runtime_files = sorted(root.glob("*/runtime.json"))
    if not runtime_files:
        lines.append("No skill runtime artifacts found.")
        return "\n".join(lines)
    for runtime_path in runtime_files:
        payload = _read_json(runtime_path)
        execution = payload.get("execution", {})
        sandbox = payload.get("sandbox", {})
        if not isinstance(execution, dict) or not isinstance(sandbox, dict):
            continue
        output = execution.get("output", {})
        output_payload = output if isinstance(output, dict) else {}
        sources = output_payload.get("sources", [])
        source_text = _sources_text(sources)
        files_sample = output_payload.get("files_sample", [])
        repo = output_payload.get("repo", "")
        patterns = output_payload.get("patterns", [])
        lines.extend(
            [
                runtime_path.parent.name,
                f"- Skill: {execution.get('skill', runtime_path.parent.name)}",
                f"- Action: {execution.get('action', 'unknown')}",
                f"- Permission: {execution.get('permission_used', [])}",
                f"- Query: {output_payload.get('query', '')}",
                f"- Repo: {repo}",
                f"- Path: {output_payload.get('path', '')}",
                f"- Paths: {output_payload.get('files_analyzed', output_payload.get('paths', []))}",
                f"- Runtime status: {execution.get('status', 'unknown')}",
                f"- Sandbox status: {sandbox.get('status', 'unknown')}",
                f"- Allowed permissions: {sandbox.get('granted_permissions', [])}",
                f"- Sources: {source_text}",
                f"- Files sample: {_files_text(files_sample)}",
                f"- Patterns found: {_patterns_text(patterns)}",
                f"- Summary: {output_payload.get('summary', '')}",
                f"- Workspace: {execution.get('output', {}).get('workspace', '')}",
                f"- Audit path: {execution.get('audit_path', str(runtime_path.parent))}",
                f"- Errors: {execution.get('errors', [])}",
                "",
            ]
        )
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class SkillRuntimeView(QWidget):  # type: ignore[misc]
        """Read-only Skill Runtime view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Skill Runtime")
            title.setAccessibleName("Skill Runtime view title")
            self.body = QPlainTextEdit(runtime_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Skill Runtime read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(runtime_snapshot())

else:

    class SkillRuntimeView:  # type: ignore[no-redef]
        pass


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sources_text(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    urls = []
    for item in value:
        if isinstance(item, dict):
            urls.append(str(item.get("url", "")))
    return ", ".join(url for url in urls if url) or "[]"


def _files_text(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    paths = []
    for item in value:
        if isinstance(item, dict):
            paths.append(str(item.get("path", "")))
    return ", ".join(path for path in paths if path) or "[]"


def _patterns_text(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    names = []
    for item in value:
        if isinstance(item, dict):
            names.append(f"{item.get('pattern_type', 'unknown')}:{item.get('name', 'unknown')}")
    return ", ".join(names) or "[]"
