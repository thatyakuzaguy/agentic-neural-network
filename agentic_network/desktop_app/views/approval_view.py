"""Approval view for ANN Desktop."""

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


APPROVAL_MESSAGE = (
    "Approvals are visible here in v8.0, but this foundation does not auto-approve, "
    "mint tokens, apply patches, or mutate approval artifacts."
)


if PYSIDE6_AVAILABLE:

    class ApprovalView(QWidget):  # type: ignore[misc]
        """Read-only approval center placeholder."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Approvals")
            title.setAccessibleName("Approvals view title")
            self.body = QPlainTextEdit(APPROVAL_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Approvals read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(APPROVAL_MESSAGE)

else:

    class ApprovalView:  # type: ignore[no-redef]
        auto_approves = False
