"""Project Manager view for ANN Desktop."""

from __future__ import annotations

from typing import Any, Callable

from agentic_network.runtime_engine.local_model_activation import ann_v1_1_desktop_status_lines

try:  # pragma: no cover - covered by smoke when Qt is available.
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QPushButton,
        QPlainTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QListWidget = None
    QPushButton = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


if PYSIDE6_AVAILABLE:

    class ProjectManagerView(QWidget):  # type: ignore[misc]
        """Local project registry and active workspace selector."""

        def __init__(
            self,
            *,
            add_project: Callable[[str, str], str],
            activate_project: Callable[[str], str],
            remove_project: Callable[[str], str],
        ) -> None:
            super().__init__()
            self._add_project = add_project
            self._activate_project = activate_project
            self._remove_project = remove_project
            self._project_ids: list[str] = []

            layout = QVBoxLayout(self)
            title = QLabel("Projects")
            title.setAccessibleName("Projects view title")

            self.project_list = QListWidget()
            self.project_list.setAccessibleName("Registered ANN projects")
            self.project_list.currentRowChanged.connect(self._show_selected_summary)

            form = QWidget()
            form_layout = QHBoxLayout(form)
            self.name_input = QLineEdit()
            self.name_input.setAccessibleName("Project name")
            self.name_input.setPlaceholderText("Project name")
            self.path_input = QLineEdit()
            self.path_input.setAccessibleName("Project root path")
            self.path_input.setPlaceholderText("D:\\AgenticEngineeringNetwork")
            add_button = QPushButton("Register")
            add_button.setAccessibleName("Register local project")
            add_button.clicked.connect(self._register_clicked)
            activate_button = QPushButton("Set Active")
            activate_button.setAccessibleName("Set selected project active")
            activate_button.clicked.connect(self._activate_clicked)
            remove_button = QPushButton("Remove")
            remove_button.setAccessibleName("Remove selected project registration")
            remove_button.clicked.connect(self._remove_clicked)
            for widget in (self.name_input, self.path_input, add_button, activate_button, remove_button):
                form_layout.addWidget(widget)

            self.summary = QPlainTextEdit()
            self.summary.setReadOnly(True)
            self.summary.setAccessibleName("Project summary")
            self.ux_status = QPlainTextEdit("\n".join(ann_v1_1_desktop_status_lines()))
            self.ux_status.setReadOnly(True)
            self.ux_status.setAccessibleName("ANN v1.1 Projects user status")

            layout.addWidget(title)
            layout.addWidget(self.ux_status)
            layout.addWidget(form)
            layout.addWidget(self.project_list, 1)
            layout.addWidget(self.summary, 1)

        def set_bundle(self, _bundle: Any, snapshot: dict[str, Any]) -> None:
            self._snapshot = snapshot
            self.ux_status.setPlainText("\n".join(ann_v1_1_desktop_status_lines()))
            self._project_ids = []
            self.project_list.blockSignals(True)
            self.project_list.clear()
            for project in snapshot.get("projects", []):
                marker = "*" if project.get("is_active") else " "
                self.project_list.addItem(f"{marker} {project.get('name')} | {project.get('root_path')}")
                self._project_ids.append(str(project.get("project_id")))
            self.project_list.blockSignals(False)
            if self.project_list.count() and self.project_list.currentRow() < 0:
                self.project_list.setCurrentRow(0)
            self._show_selected_summary(self.project_list.currentRow())

        def _register_clicked(self) -> None:
            self.summary.setPlainText(self._add_project(self.name_input.text(), self.path_input.text()))

        def _activate_clicked(self) -> None:
            project_id = self._selected_project_id()
            if project_id is not None:
                self.summary.setPlainText(self._activate_project(project_id))

        def _remove_clicked(self) -> None:
            project_id = self._selected_project_id()
            if project_id is not None:
                self.summary.setPlainText(self._remove_project(project_id))

        def _selected_project_id(self) -> str | None:
            row = self.project_list.currentRow()
            if 0 <= row < len(self._project_ids):
                return self._project_ids[row]
            return None

        def _show_selected_summary(self, row: int) -> None:
            projects = getattr(self, "_snapshot", {}).get("project_summaries", [])
            if 0 <= row < len(projects):
                project = projects[row]
                lines = [
                    f"Name: {project.get('name')}",
                    f"Root: {project.get('root_path')}",
                    f"Runs: {project.get('run_count')}",
                    f"Latest run: {project.get('latest_run_id') or 'None'}",
                    f"Valid: {project.get('valid')}",
                ]
                warnings = project.get("warnings") or []
                errors = project.get("errors") or []
                if warnings:
                    lines.append("Warnings: " + "; ".join(str(item) for item in warnings))
                if errors:
                    lines.append("Errors: " + "; ".join(str(item) for item in errors))
                self.summary.setPlainText("\n".join(lines))
            else:
                self.summary.setPlainText("No registered projects yet.")

else:

    class ProjectManagerView:  # type: ignore[no-redef]
        pass
