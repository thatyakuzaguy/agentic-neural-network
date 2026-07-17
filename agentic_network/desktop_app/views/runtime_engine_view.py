"""Read-only Runtime Engine view for ANN Desktop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.executor import DEFAULT_OUTPUT_ROOT
from agentic_network.runtime_engine.loader import DEFAULT_CONFIG_PATH, get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.model_policy import load_model_policy

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


RUNTIME_ENGINE_MESSAGE = (
    "Runtime Engine is read-only in this view. It does not download models, "
    "modify adapters or datasets, execute terminal commands, use internet, or run training."
)


def runtime_engine_snapshot(
    config_path: str | Path | None = None,
    runtime_root: str | Path | None = None,
) -> str:
    """Render runtime config, active models, metrics, and latest artifacts."""

    config = _read_json(Path(config_path or DEFAULT_CONFIG_PATH))
    policy = load_model_policy()
    metrics = get_runtime_metrics()
    root = Path(runtime_root or DEFAULT_OUTPUT_ROOT).resolve()
    lines = [
        "Runtime Engine",
        "",
        RUNTIME_ENGINE_MESSAGE,
        "",
        f"Execution Mode: {config.get('default_mode', 'FAST')}",
        f"VRAM Policy: {config.get('vram_policy', 'SEQUENTIAL')}",
        f"Max Loaded Models: {config.get('max_loaded_models', 1)}",
        f"Backend: {config.get('backend', 'mock')}",
        f"Real Model Load Allowed: {_real_model_load_allowed(config)}",
        "Policy Decision Source: config/ann_model_policy.json",
        f"Policy Allowed Backends: {policy.allowed_backends}",
        f"Policy Downloads Allowed: {policy.allow_model_download}",
        f"Policy Training Allowed: {policy.allow_training}",
        f"Loaded Models: {get_loaded_models()}",
        f"Active Models: {metrics.get('active_models', 0)}",
        f"Parallel Loads: {metrics.get('parallel_llm_loads', 0)}",
        f"Peak VRAM: {metrics.get('peak_vram_mb', 0)} MB",
        f"Backend Status: {metrics.get('backend_status', 'UNKNOWN')}",
        f"Load Status: {metrics.get('last_load_status', 'UNKNOWN')}",
        f"Generate Status: {metrics.get('last_generate_status', 'UNKNOWN')}",
        f"Unload Status: {metrics.get('last_unload_status', 'UNKNOWN')}",
        "",
    ]
    bundles = sorted(root.glob("*/74_runtime_execution.json")) if root.is_dir() else []
    if bundles:
        lines.append("Latest executions:")
    for bundle_path in bundles[-5:]:
        payload = _read_json(bundle_path)
        policy_payload = _read_json(bundle_path.parent / "79_model_policy_decision.json")
        lines.extend(
            [
                str(bundle_path.parent),
                f"- Status: {payload.get('status', 'UNKNOWN')}",
                f"- Backend: {payload.get('backend_name', '')}",
                f"- Backend Status: {payload.get('backend_status', '')}",
                f"- Current Agent: {payload.get('agent_name', '')}",
                f"- Current Model: {payload.get('selected_model', '')}",
                f"- Load Status: {payload.get('load_status', '')}",
                f"- Generate Status: {payload.get('generate_status', '')}",
                f"- Unload Status: {payload.get('unload_status', '')}",
                f"- Active Models: {payload.get('active_models', 0)}",
                f"- Parallel Loads: {payload.get('parallel_llm_loads', 0)}",
                f"- Policy Decision: {policy_payload.get('reason', 'UNKNOWN')}",
                f"- Load Allowed: {policy_payload.get('allowed', 'UNKNOWN')}",
            ]
        )
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class RuntimeEngineView(QWidget):  # type: ignore[misc]
        """Read-only Runtime Engine view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Runtime Engine")
            title.setAccessibleName("Runtime Engine view title")
            self.body = QPlainTextEdit(runtime_engine_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Runtime Engine read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(runtime_engine_snapshot())

else:

    class RuntimeEngineView:  # type: ignore[no-redef]
        pass


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _real_model_load_allowed(config: dict[str, object]) -> bool:
    policy = config.get("backend_policy")
    if not isinstance(policy, dict):
        return False
    return bool(policy.get("allow_real_model_load", False))
