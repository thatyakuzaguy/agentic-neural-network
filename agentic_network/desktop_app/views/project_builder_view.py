"""Read-only Project Builder view for ANN Desktop."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - covered by manual desktop smoke.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


PROJECT_BUILDER_MESSAGE = (
    "Project Builder v8.4 starts implementation runs from a scaffolded project.\n"
    "Flow: Idea -> Plan -> Scaffold -> Implementation -> Consensus -> Next Step.\n"
    "It generates backlog, artifacts, and patch proposals only.\n"
    "It does not execute terminal commands, install packages, use network, or apply patches."
)


if PYSIDE6_AVAILABLE:

    class ProjectBuilderView(QWidget):  # type: ignore[misc]
        """Read-only status view for project implementation kickoff."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Builder")
            title.setAccessibleName("Project Builder view title")
            self.body = QPlainTextEdit(PROJECT_BUILDER_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Builder read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_BUILDER_MESSAGE)

else:

    class ProjectBuilderView:  # type: ignore[no-redef]
        pass
