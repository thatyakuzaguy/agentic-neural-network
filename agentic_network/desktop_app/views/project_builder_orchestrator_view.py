"""Read-only End-to-End Project Builder Orchestrator view."""

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


PROJECT_BUILDER_ORCHESTRATOR_MESSAGE = (
    "End-to-End Builder v8.9 orchestrates Project Creation, Scaffold, Implementation, "
    "Patch Apply, Verification, Self-Healing, Consensus, and Action Plan.\n\n"
    "Completion quality: VERIFIED, UNVERIFIED, or REVIEW_REQUIRED.\n"
    "Verification evidence: tests detected, commands executed, stdout/stderr artifacts, "
    "verification status, and evidence level NONE/WEAK/MEDIUM/STRONG.\n"
    "Recommended next action: add_project_tests, run_project_verification, "
    "review_generated_project, resolve_failures, or completed_verified.\n\n"
    "Unverified warning: generated projects without executed passing tests are not shown as "
    "COMPLETED_VERIFIED. Dangerous phases still require explicit confirmations and local "
    "approval tokens."
)


if PYSIDE6_AVAILABLE:

    class ProjectBuilderOrchestratorView(QWidget):  # type: ignore[misc]
        """Read-only status view for the end-to-end builder."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("End-to-End Builder")
            title.setAccessibleName("End-to-End Builder view title")
            self.body = QPlainTextEdit(PROJECT_BUILDER_ORCHESTRATOR_MESSAGE)
            self.body.setReadOnly(True)
            self.body.setAccessibleName("End-to-End Builder read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(PROJECT_BUILDER_ORCHESTRATOR_MESSAGE)

else:

    class ProjectBuilderOrchestratorView:  # type: ignore[no-redef]
        pass
