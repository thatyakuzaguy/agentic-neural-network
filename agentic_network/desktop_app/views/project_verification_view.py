"""Read-only Project Verification view for ANN Desktop."""

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


PROJECT_VERIFICATION_MESSAGE = (
    "Project Verification v8.6 runs only allowlisted local test commands after explicit confirmation.\n"
    "It captures stdout/stderr artifacts, updates consensus/action plan, and prepares retry context.\n"
    "It never installs dependencies, uses internet, or executes arbitrary shell commands."
)


if PYSIDE6_AVAILABLE:

    class ProjectVerificationView(QWidget):  # type: ignore[misc]
        """Read-only status view for project verification."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Verification")
            title.setAccessibleName("Project Verification view title")
            self.body = QPlainTextEdit(PROJECT_VERIFICATION_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Verification read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_VERIFICATION_MESSAGE)

else:

    class ProjectVerificationView:  # type: ignore[no-redef]
        pass
