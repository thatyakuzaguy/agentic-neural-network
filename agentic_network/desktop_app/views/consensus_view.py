"""Consensus decision view for ANN Desktop."""

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

    class ConsensusView(QWidget):  # type: ignore[misc]
        """Read-only consensus artifact view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Consensus")
            title.setAccessibleName("Consensus view title")
            self.body = QPlainTextEdit()
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Consensus read only artifact")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, bundle: Any, _snapshot: dict[str, Any]) -> None:
            payload = bundle.consensus if bundle else {}
            self.body.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False) if payload else "No consensus artifact.")

else:

    class ConsensusView:  # type: ignore[no-redef]
        pass
