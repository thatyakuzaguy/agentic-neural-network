"""Read-only Project Self Healing view for ANN Desktop."""

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


PROJECT_SELF_HEALING_MESSAGE = (
    "Project Self Healing v8.7 analyzes failed verification output, generates retry patches, "
    "applies them with explicit approval, reruns safe verification, and stops at max attempts. "
    "It never uses internet, installs dependencies, executes arbitrary shell commands, or modifies ANN core."
)


if PYSIDE6_AVAILABLE:

    class ProjectSelfHealingView(QWidget):  # type: ignore[misc]
        """Read-only status view for project self-healing."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Project Self Healing")
            title.setAccessibleName("Project Self Healing view title")
            self.body = QPlainTextEdit(PROJECT_SELF_HEALING_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Project Self Healing read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_SELF_HEALING_MESSAGE)

else:

    class ProjectSelfHealingView:  # type: ignore[no-redef]
        pass
