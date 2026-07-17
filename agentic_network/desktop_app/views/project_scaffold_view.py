"""Read-only Project Scaffold view for ANN Desktop."""

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


PROJECT_SCAFFOLD_MESSAGE = (
    "Project Scaffolding v8.3 is approval-gated.\n"
    "Preview and dry-run are safe read/write artifact operations.\n"
    "Real scaffold apply requires ANN_PROJECT_SCAFFOLD_TOKEN, --approval-token, and --confirm-create.\n"
    "No terminal commands, dependency installs, patch apply, or approval token mutation happen here."
)


if PYSIDE6_AVAILABLE:

    class ProjectScaffoldView(QWidget):  # type: ignore[misc]
        """Read-only status view for project scaffold flow."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Scaffold")
            title.setAccessibleName("Project Scaffold view title")
            self.body = QPlainTextEdit(PROJECT_SCAFFOLD_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Scaffold read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_SCAFFOLD_MESSAGE)

else:

    class ProjectScaffoldView:  # type: ignore[no-redef]
        pass
