"""Token dialog for ANN Desktop confirmation flows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

try:  # pragma: no cover - exercised by manual desktop smoke.
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QVBoxLayout, QLabel

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QDialog = object
    QDialogButtonBox = None
    QLineEdit = None
    QVBoxLayout = None
    QLabel = None
    PYSIDE6_AVAILABLE = False


@dataclass(frozen=True)
class TokenRequest:
    """Read-only token prompt metadata."""

    action: str
    requires_token: bool
    risk: str
    token_provided: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_token_request(action: str, *, risk: str = "MEDIUM", token: str | None = None) -> TokenRequest:
    """Build token request metadata without validating or minting approvals."""

    return TokenRequest(
        action=action.strip() or "unknown",
        requires_token=True,
        risk=risk.strip().upper() or "MEDIUM",
        token_provided=bool((token or "").strip()),
    )


if PYSIDE6_AVAILABLE:

    class TokenDialog(QDialog):  # type: ignore[misc]
        """Small native dialog that collects an existing approval token."""

        def __init__(self, *, action: str, risk: str = "MEDIUM", parent: Any = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Approval Token")
            self.setAccessibleName("ANN approval token dialog")
            self.token_input = QLineEdit()
            self.token_input.setAccessibleName("Approval token input")
            self.token_input.setEchoMode(QLineEdit.Password)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel(f"Action: {action}"))
            layout.addWidget(QLabel(f"Risk: {risk}"))
            layout.addWidget(QLabel("Token"))
            layout.addWidget(self.token_input)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def token(self) -> str:
            """Return the entered token."""

            return self.token_input.text().strip()

else:

    class TokenDialog:  # type: ignore[no-redef]
        pass
