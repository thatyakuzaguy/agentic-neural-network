"""Safe Terminal view for ANN Desktop."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


SAFE_TERMINAL_MESSAGE = (
    "Safe Terminal is read-only in ANN v8.0.\n"
    "No command is executed from the desktop foundation.\n"
    "Future phases may add explicit approval-gated execution."
)


if PYSIDE6_AVAILABLE:

    class TerminalView(QWidget):  # type: ignore[misc]
        """Read-only terminal status view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Safe Terminal")
            title.setAccessibleName("Safe Terminal view title")
            self.body = QPlainTextEdit(SAFE_TERMINAL_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Safe Terminal read only output")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(SAFE_TERMINAL_MESSAGE)

else:

    class TerminalView:  # type: ignore[no-redef]
        """Non-Qt terminal view placeholder."""

        can_execute = False
