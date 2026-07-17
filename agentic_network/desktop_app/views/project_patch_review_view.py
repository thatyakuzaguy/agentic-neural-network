"""Read-only Project Patch Review view for ANN Desktop."""

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


PROJECT_PATCH_REVIEW_MESSAGE = (
    "Project Patch Review v8.5 is approval-gated.\n"
    "Flow: Generated Patch -> Parallel Review -> Consensus -> Human Approval -> Apply -> Backup/Rollback.\n"
    "No terminal commands, package installs, network access, or ANN core patch apply happen here."
)


if PYSIDE6_AVAILABLE:

    class ProjectPatchReviewView(QWidget):  # type: ignore[misc]
        """Read-only status view for project patch review and apply flow."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Patch Review")
            title.setAccessibleName("Project Patch Review view title")
            self.body = QPlainTextEdit(PROJECT_PATCH_REVIEW_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Patch Review read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_PATCH_REVIEW_MESSAGE)

else:

    class ProjectPatchReviewView:  # type: ignore[no-redef]
        pass
