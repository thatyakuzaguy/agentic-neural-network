"""Runs list view for ANN Desktop."""

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


if PYSIDE6_AVAILABLE:

    class RunsView(QWidget):  # type: ignore[misc]
        """Read-only list of runs."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Runs")
            title.setAccessibleName("Runs view title")
            self.body = QPlainTextEdit()
            self.body.setReadOnly(True)
            self.body.setAccessibleName("ANN runs read only list")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, snapshot: dict[str, Any]) -> None:
            active = snapshot.get("active_project")
            header = []
            if active:
                header.append(f"Active project: {active.get('name')}")
                header.append(f"Runs path: {active.get('runs_path')}")
            else:
                header.append("Active project: none registered; using default repository runs.")
            lines = [
                f"{run['run_id']} | {run.get('status', 'UNKNOWN')} | {run.get('task', 'Unknown task')}"
                for run in snapshot.get("runs", [])
            ]
            if not lines:
                lines = ["No ANN runs found."]
            self.body.setPlainText("\n".join([*header, "", *lines]))

else:

    class RunsView:  # type: ignore[no-redef]
        pass
