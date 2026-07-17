"""Read-only Project Test Generation view."""

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


PROJECT_TEST_GENERATION_MESSAGE = (
    "Project Test Generation v9.0 proposes non-trivial test patches for generated "
    "projects that ended in NEEDS_TESTS.\n\n"
    "Status: shown from generated artifacts when available.\n"
    "Project root: read-only.\n"
    "Tests planned: README/package/API/schema contract tests.\n"
    "Generated test patches: patches/test_patch_001.diff and later.\n"
    "Next action: review and apply generated test patches with approval, then run "
    "Project Verification.\n\n"
    "Safety: this view does not execute terminal commands, install dependencies, "
    "apply patches, or grant approvals."
)


if PYSIDE6_AVAILABLE:

    class ProjectTestGenerationView(QWidget):  # type: ignore[misc]
        """Read-only status view for project test generation."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Test Generation")
            title.setAccessibleName("Project Test Generation view title")
            self.body = QPlainTextEdit(PROJECT_TEST_GENERATION_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Test Generation read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_TEST_GENERATION_MESSAGE)

else:

    class ProjectTestGenerationView:  # type: ignore[no-redef]
        pass
