"""Runtime backend adapters for ANN Sequential Runtime Engine."""

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
    ModelBackend,
)
from agentic_network.runtime_engine.backends.embedded_backend import EmbeddedBackend
from agentic_network.runtime_engine.backends.gguf_backend import GGUFBackend
from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend
from agentic_network.runtime_engine.backends.mock_backend import MockBackend
from agentic_network.runtime_engine.backends.ollama_backend import OllamaBackend
from agentic_network.runtime_engine.backends.qwen_local_backend import QwenLocalBackend
from agentic_network.runtime_engine.backends.unsloth_qwen_backend import UnslothQwenBackend

__all__ = [
    "BackendGenerateResult",
    "BackendHealthResult",
    "BackendLoadResult",
    "BackendUnloadResult",
    "EmbeddedBackend",
    "GGUFBackend",
    "LlamaCppBackend",
    "MockBackend",
    "ModelBackend",
    "OllamaBackend",
    "QwenLocalBackend",
    "UnslothQwenBackend",
]
