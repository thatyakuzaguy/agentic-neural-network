"""llama.cpp / GGUF local backend foundation for ANN."""

from __future__ import annotations

import importlib.util
from time import perf_counter
from typing import Any

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)


class LlamaCppBackend:
    """Safe llama.cpp backend foundation.

    This adapter does not install, compile, download, shell out, or open GGUF
    weights. It only reports whether the optional Python binding is importable
    and whether policy allows real model loading.
    """

    name = "llama_cpp"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}
        self.binding_available = importlib.util.find_spec("llama_cpp") is not None

    def load_model(self, model_name: str) -> BackendLoadResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendLoadResult(
                status="BLOCKED",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=["llama_cpp_real_model_load_blocked_by_policy"],
                warnings=["No GGUF file was opened."],
            )
        if not self.binding_available:
            return BackendLoadResult(
                status="UNAVAILABLE",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=["llama_cpp_binding_unavailable"],
                warnings=["Install/configure llama_cpp outside ANN runtime if policy permits."],
            )
        return BackendLoadResult(
            status="UNAVAILABLE",
            model_name=model_name,
            backend=self.name,
            loaded=False,
            errors=["llama_cpp_real_loader_not_enabled"],
            warnings=["Foundation only; no real GGUF load is attempted in v11.0-v11.2."],
        )

    def generate(
        self,
        model_name: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> BackendGenerateResult:
        started = perf_counter()
        return BackendGenerateResult(
            status="BLOCKED",
            model_name=model_name,
            backend=self.name,
            text="",
            tokens_in=len(prompt.split()),
            tokens_out=0,
            duration_ms=max(0, int((perf_counter() - started) * 1000)),
            errors=["llama_cpp_generate_requires_loaded_model"],
            warnings=["No terminal, internet, download, compile, or GGUF write was used."],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=["No real llama.cpp model was loaded."],
        )

    def health_check(self) -> BackendHealthResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendHealthResult(
                status="BLOCKED_BY_POLICY",
                backend=self.name,
                available=False,
                errors=["real_model_load_blocked_by_policy"],
                warnings=["llama.cpp backend is present but real load is disabled."],
            )
        if not self.binding_available:
            return BackendHealthResult(
                status="UNAVAILABLE",
                backend=self.name,
                available=False,
                errors=["llama_cpp_binding_unavailable"],
                warnings=[],
            )
        return BackendHealthResult(status="AVAILABLE", backend=self.name, available=True, errors=[], warnings=[])

