"""Parallel Review view for ANN Desktop."""

from __future__ import annotations

import json
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


if PYSIDE6_AVAILABLE:

    class ParallelReviewView(QWidget):  # type: ignore[misc]
        """Read-only Parallel Review artifact view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Parallel Review")
            title.setAccessibleName("Parallel Review view title")
            self.body = QPlainTextEdit()
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Parallel Review read only artifact")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, bundle: Any, _snapshot: dict[str, Any]) -> None:
            payload = bundle.parallel_review if bundle else {}
            self.body.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False) if payload else "No parallel review artifact.")

else:

    class ParallelReviewView:  # type: ignore[no-redef]
        pass
