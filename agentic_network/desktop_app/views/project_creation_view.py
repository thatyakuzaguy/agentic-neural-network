"""Read-only Project Creation view for ANN Desktop."""

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


PROJECT_CREATION_MESSAGE = (
    "Project Creation Engine v8.2 is plan-only.\n"
    "It generates artifacts 40/41 through the Python API or CLI.\n"
    "It does not scaffold target project files, execute terminal commands, apply patches, or approve anything."
)


if PYSIDE6_AVAILABLE:

    class ProjectCreationView(QWidget):  # type: ignore[misc]
        """Read-only status view for project creation planning."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Creation")
            title.setAccessibleName("Project Creation view title")
            self.body = QPlainTextEdit(PROJECT_CREATION_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Creation read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_CREATION_MESSAGE)

else:

    class ProjectCreationView:  # type: ignore[no-redef]
        pass
