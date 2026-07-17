"""Skill permission administration view."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_network.skills import SkillPermissionStore, SkillsManager
from agentic_network.skills.models import PermissionDecision

try:  # pragma: no cover - covered by manual desktop smoke.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QPushButton = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


SKILL_PERMISSION_MESSAGE = (
    "Skill Permissions are persistent local decisions. This view does not execute "
    "skills, internet, git, terminal commands, or package installation."
)
ACTION_DECISIONS = {
    "Allow Once": PermissionDecision.ALLOW_ONCE,
    "Allow Always": PermissionDecision.ALLOW_ALWAYS,
    "Deny Once": PermissionDecision.DENY_ONCE,
    "Deny Always": PermissionDecision.DENY_ALWAYS,
}


def permission_snapshot(
    manager: SkillsManager | None = None,
    store: SkillPermissionStore | None = None,
) -> str:
    """Render skill permission state."""

    resolved_manager = manager or SkillsManager()
    resolved_store = store or resolved_manager.permission_store
    lines = ["Skill Permissions", "", SKILL_PERMISSION_MESSAGE, ""]
    for skill in resolved_manager.list_skills():
        lines.append(f"{skill.name}")
        for permission, manifest_decision in sorted(skill.permissions.items()):
            current = resolved_store.get_permission(skill.name, permission)
            persistent = current in {PermissionDecision.ALLOW_ALWAYS, PermissionDecision.DENY_ALWAYS}
            lines.append(
                f"- {permission}: current={current.value}; manifest={manifest_decision.value}; "
                f"persistent={persistent}; description={skill.description}"
            )
        lines.append("")
    return "\n".join(lines)


def update_skill_permission(
    skill_name: str,
    permission: str,
    action: str,
    *,
    store_path: str | Path | None = None,
) -> PermissionDecision:
    """Apply a Desktop permission action to the persistent store."""

    store = SkillPermissionStore(store_path)
    if action == "Reset":
        store.remove_permission(skill_name, permission)
        return PermissionDecision.ASK_ALWAYS
    decision = ACTION_DECISIONS.get(action)
    if decision is None:
        raise ValueError(f"Unknown permission action: {action}")
    store.set_permission(skill_name, permission, decision)
    return decision


if PYSIDE6_AVAILABLE:

    class SkillPermissionView(QWidget):  # type: ignore[misc]
        """Read/write local permission settings view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Skill Permissions")
            title.setAccessibleName("Skill Permissions view title")
            self.body = QPlainTextEdit(permission_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Skill Permissions read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)
            for label in ["Allow Once", "Allow Always", "Deny Once", "Deny Always", "Reset"]:
                button = QPushButton(label)
                button.setAccessibleName(f"Skill permission {label}")
                layout.addWidget(button)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(permission_snapshot())

else:

    class SkillPermissionView:  # type: ignore[no-redef]
        pass
