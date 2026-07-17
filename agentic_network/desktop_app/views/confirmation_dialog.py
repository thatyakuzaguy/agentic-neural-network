"""Native confirmation UX for approval-gated ANN actions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised by manual desktop smoke.
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QVBoxLayout,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QCheckBox = None
    QDialog = object
    QDialogButtonBox = None
    QLabel = None
    QLineEdit = None
    QPlainTextEdit = None
    QVBoxLayout = None
    PYSIDE6_AVAILABLE = False


@dataclass(frozen=True)
class ConfirmationRequest:
    """Confirmation metadata for an approval-gated desktop action."""

    action: str
    project: str
    patch: str | None
    risk: str
    files: int
    requires_token: bool
    requires_understanding: bool
    offers_backup: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmationDecision:
    """User confirmation result captured by the desktop UI."""

    action: str
    confirmed: bool
    token_provided: bool
    understands_risk: bool
    create_backup: bool
    cancelled: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_confirmation_request(
    *,
    action: str,
    project: str = "unknown",
    patch: str | None = None,
    risk: str = "MEDIUM",
    files: int = 0,
) -> ConfirmationRequest:
    """Build a confirmation request without approving or applying anything."""

    return ConfirmationRequest(
        action=action.strip() or "unknown",
        project=project.strip() or "unknown",
        patch=patch.strip() if isinstance(patch, str) and patch.strip() else None,
        risk=risk.strip().upper() or "MEDIUM",
        files=max(0, int(files)),
        requires_token=True,
        requires_understanding=True,
        offers_backup=True,
    )


def build_cancelled_decision(action: str) -> ConfirmationDecision:
    """Return a deterministic cancelled decision."""

    return ConfirmationDecision(
        action=action,
        confirmed=False,
        token_provided=False,
        understands_risk=False,
        create_backup=False,
        cancelled=True,
    )


def record_confirmation_trace(
    run_dir: str | Path,
    request: ConfirmationRequest,
    decision: ConfirmationDecision | None = None,
) -> str:
    """Persist artifact 85 without mutating approval gates."""

    target = Path(run_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "85_confirmation_trace.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": request.to_dict(),
        "decision": decision.to_dict() if decision else None,
        "gate_reuse": [
            "human_approval_agent",
            "project_patch_apply_agent",
            "project_self_healing_agent",
        ],
        "safety": {
            "auto_approval": False,
            "patch_auto_apply": False,
            "terminal_auto_execute": False,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


if PYSIDE6_AVAILABLE:

    class ConfirmationDialog(QDialog):  # type: ignore[misc]
        """Confirmation dialog that collects token and risk acknowledgement."""

        def __init__(self, request: ConfirmationRequest, parent: Any = None) -> None:
            super().__init__(parent)
            self.request = request
            self.setWindowTitle(request.action)
            self.setAccessibleName("ANN confirmation dialog")
            self.token_input = QLineEdit()
            self.token_input.setAccessibleName("Approval token input")
            self.token_input.setEchoMode(QLineEdit.Password)
            self.understand = QCheckBox("I understand the risk")
            self.understand.setAccessibleName("Understand risk checkbox")
            self.backup = QCheckBox("Create backup")
            self.backup.setAccessibleName("Create backup checkbox")
            self.backup.setChecked(True)
            details = QPlainTextEdit(_request_text(request))
            details.setReadOnly(True)
            details.setAccessibleName("Confirmation risk details")
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel(request.action))
            layout.addWidget(details)
            layout.addWidget(QLabel("Token"))
            layout.addWidget(self.token_input)
            layout.addWidget(self.understand)
            layout.addWidget(self.backup)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def decision(self) -> ConfirmationDecision:
            """Return the current dialog decision."""

            token = self.token_input.text().strip()
            understands = self.understand.isChecked()
            return ConfirmationDecision(
                action=self.request.action,
                confirmed=bool(token and understands),
                token_provided=bool(token),
                understands_risk=understands,
                create_backup=self.backup.isChecked(),
                cancelled=False,
            )

        def token(self) -> str:
            """Return the entered token."""

            return self.token_input.text().strip()

else:

    class ConfirmationDialog:  # type: ignore[no-redef]
        pass


def _request_text(request: ConfirmationRequest) -> str:
    return "\n".join(
        [
            f"Patch: {request.patch or 'n/a'}",
            f"Project: {request.project}",
            f"Risk: {request.risk}",
            f"Files: {request.files}",
            "",
            "This dialog only collects confirmation. Existing ANN gates still decide whether the action is allowed.",
        ]
    )
