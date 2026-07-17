"""Action Plan / Next Step view for ANN Desktop."""

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

    class ActionPlanView(QWidget):  # type: ignore[misc]
        """Read-only Next Step controller view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Next Step")
            title.setAccessibleName("Next Step view title")
            self.body = QPlainTextEdit()
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Action Plan read only artifact")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, bundle: Any, _snapshot: dict[str, Any]) -> None:
            payload = bundle.action_plan if bundle else {}
            if not payload:
                self.body.setPlainText("No 39_action_plan.json artifact. No action can be executed.")
                return
            self.body.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

else:

    class ActionPlanView:  # type: ignore[no-redef]
        pass
