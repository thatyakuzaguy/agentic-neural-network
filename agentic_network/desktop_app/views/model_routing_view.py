"""Read-only Model Routing view for ANN Desktop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_network.model_routing.router import DEFAULT_CONFIG_PATH, load_routing_config
from agentic_network.model_routing.runtime import DEFAULT_OUTPUT_ROOT

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


MODEL_ROUTING_MESSAGE = (
    "Model Routing is read-only. This view does not download models, load models, "
    "touch adapters or datasets, execute terminal commands, or run training."
)


def model_routing_snapshot(
    config_path: str | Path | None = None,
    routing_root: str | Path | None = None,
) -> str:
    """Render routing configuration and latest routing artifacts."""

    config = load_routing_config(config_path or DEFAULT_CONFIG_PATH)
    root = Path(routing_root or DEFAULT_OUTPUT_ROOT).resolve()
    lines = ["Model Routing", "", MODEL_ROUTING_MESSAGE, ""]
    lines.extend(
        [
            f"Default mode: {config.get('default_mode', 'UNKNOWN')}",
            f"VRAM policy: {config.get('vram_policy', 'UNKNOWN')}",
            "",
            "Configured routes:",
        ]
    )
    routes = config.get("agent_routes") if isinstance(config.get("agent_routes"), dict) else {}
    for agent, route in sorted(routes.items()):
        lines.append(f"- {agent}: {route}")
    bundles = sorted(root.glob("*/72_model_routing_plan.json")) if root.is_dir() else []
    if bundles:
        lines.extend(["", "Latest routing plans:"])
    for bundle_path in bundles[-5:]:
        payload = _read_json(bundle_path)
        lines.extend(
            [
                str(bundle_path.parent),
                f"- Status: {payload.get('status', 'UNKNOWN')}",
                f"- Mode: {payload.get('mode', 'UNKNOWN')}",
                f"- VRAM policy: {payload.get('vram_policy', 'UNKNOWN')}",
                "- Decisions:",
            ]
        )
        decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
        for decision in decisions:
            if isinstance(decision, dict):
                lines.append(
                    f"  - {decision.get('agent_name')}: {decision.get('selected_model')} "
                    f"sequential={decision.get('sequential_required')}"
                )
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class ModelRoutingView(QWidget):  # type: ignore[misc]
        """Read-only Model Routing view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Model Routing")
            title.setAccessibleName("Model Routing view title")
            self.body = QPlainTextEdit(model_routing_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Model Routing read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(model_routing_snapshot())

else:

    class ModelRoutingView:  # type: ignore[no-redef]
        pass


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
