"""Backend registry for ANN Sequential Runtime Engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.backends.embedded_backend import EmbeddedBackend
from agentic_network.runtime_engine.backends.base import ModelBackend
from agentic_network.runtime_engine.backends.gguf_backend import GGUFBackend
from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend
from agentic_network.runtime_engine.backends.mock_backend import MockBackend
from agentic_network.runtime_engine.backends.ollama_backend import OllamaBackend
from agentic_network.runtime_engine.backends.qwen_local_backend import QwenLocalBackend
from agentic_network.runtime_engine.backends.unsloth_qwen_backend import UnslothQwenBackend


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ann_runtime_engine.json"
AVAILABLE_BACKENDS = ("mock", "embedded", "llama_cpp", "qwen_local", "ollama", "gguf", "unsloth_qwen")


def list_available_backends() -> list[str]:
    """Return backend names supported by the registry."""

    return list(AVAILABLE_BACKENDS)


def get_backend(
    backend_name: str | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> ModelBackend:
    """Resolve a backend adapter by name or runtime config."""

    runtime_config = config or load_runtime_config()
    selected = (backend_name or os.environ.get("ANN_RUNTIME_BACKEND") or runtime_config.get("backend") or "mock")
    name = str(selected).strip().lower()
    policy = runtime_config.get("backend_policy") if isinstance(runtime_config.get("backend_policy"), dict) else {}
    if name == "mock":
        return MockBackend(policy)
    if name == "embedded":
        return EmbeddedBackend(policy)
    if name == "llama_cpp":
        return LlamaCppBackend(policy)
    if name == "qwen_local":
        return QwenLocalBackend(policy)
    if name == "ollama":
        return OllamaBackend(policy)
    if name == "gguf":
        return GGUFBackend(policy)
    if name == "unsloth_qwen":
        return UnslothQwenBackend(policy)
    raise ValueError(f"invalid_runtime_backend:{name}")


def load_runtime_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load runtime engine config without touching model directories."""

    path = Path(config_path or DEFAULT_CONFIG_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "backend": "mock",
            "available_backends": list_available_backends(),
            "backend_policy": {
                "allow_real_model_load": False,
                "allow_network": False,
                "allow_model_download": False,
                "allow_training": False,
                "allow_adapter_write": False,
                "allow_dataset_write": False,
            },
        }
    return payload if isinstance(payload, dict) else {"backend": "mock"}
