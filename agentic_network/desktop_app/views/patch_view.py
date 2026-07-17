"""Patch diff viewer for ANN Desktop."""

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

    class PatchView(QWidget):  # type: ignore[misc]
        """Read-only patch diff viewer."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Patches")
            title.setAccessibleName("Patch viewer title")
            self.body = QPlainTextEdit()
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Patch diff read only viewer")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, bundle: Any, _snapshot: dict[str, Any]) -> None:
            if not bundle or not bundle.patches:
                self.body.setPlainText("No patch diffs found.")
                return
            patch = bundle.patches[0]
            self.body.setPlainText(f"# {patch.name}\n\n{patch.content}")

else:

    class PatchView:  # type: ignore[no-redef]
        pass
