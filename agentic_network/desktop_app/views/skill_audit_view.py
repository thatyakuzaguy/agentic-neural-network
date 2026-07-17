"""Skill audit history view."""

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


SKILL_AUDIT_MESSAGE = "Skill Audit shows local permission history only. It does not execute skills."


def audit_snapshot(audit_root: str | Path | None = None) -> str:
    """Render skill permission history."""

    root = Path(audit_root or DEFAULT_AUDIT_ROOT).resolve()
    lines = ["Skill Audit", "", SKILL_AUDIT_MESSAGE, ""]
    if not root.is_dir():
        lines.append("No skill audit history found.")
        return "\n".join(lines)
    for history_path in sorted(root.glob("*/permission_history.json")):
        skill_name = history_path.parent.name
        lines.append(f"{skill_name}")
        for item in _read_history(history_path):
            lines.append(
                "- "
                f"{item.get('timestamp', 'unknown')} "
                f"permission={item.get('requested_permission', 'unknown')} "
                f"decision={item.get('decision', 'unknown')} "
                f"success={item.get('success', False)} "
                f"reason={item.get('reason', '')}"
            )
        lines.append("")
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class SkillAuditView(QWidget):  # type: ignore[misc]
        """Read-only skill audit history."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Skill Audit")
            title.setAccessibleName("Skill Audit view title")
            self.body = QPlainTextEdit(audit_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Skill Audit read only history")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(audit_snapshot())

else:

    class SkillAuditView:  # type: ignore[no-redef]
        pass


def _read_history(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []
