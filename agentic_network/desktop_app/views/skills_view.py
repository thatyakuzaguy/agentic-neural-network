"""Read-only Skills view for ANN Desktop."""

from __future__ import annotations

from typing import Any

from agentic_network.skills import SkillsManager

try:  # pragma: no cover - covered by manual desktop smoke.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


SKILLS_VIEW_MESSAGE = (
    "Skills v10.1 is a local permission foundation. Installed skills are manifests only. "
    "This view does not execute skills, terminal commands, internet requests, git commands, "
    "or package installation."
)


def skills_snapshot(manager: SkillsManager | None = None) -> str:
    """Render installed skills as plain text for desktop and tests."""

    resolved = manager or SkillsManager()
    lines = [
        "Skills",
        "",
        SKILLS_VIEW_MESSAGE,
        "",
        "Installed skills",
    ]
    for skill in resolved.list_skills():
        lines.extend(
            [
                "",
                f"- {skill.name} v{skill.version}",
                f"  Enabled: {skill.enabled}",
                f"  Requires approval: {skill.requires_user_approval}",
                f"  Audit enabled: {skill.audit_enabled}",
                f"  Description: {skill.description}",
                "  Permissions:",
                *[f"    {key}: {value.value}" for key, value in sorted(skill.permissions.items())],
            ]
        )
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class SkillsView(QWidget):  # type: ignore[misc]
        """Read-only skills management foundation view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Skills")
            title.setAccessibleName("Skills view title")
            self.body = QPlainTextEdit(skills_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Skills read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(skills_snapshot())

else:

    class SkillsView:  # type: ignore[no-redef]
        pass
