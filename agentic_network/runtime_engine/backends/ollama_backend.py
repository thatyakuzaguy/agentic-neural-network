"""Safe Ollama backend adapter stub for future real model integration."""

from __future__ import annotations

from typing import Any

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)


class OllamaBackend:
    """Ollama adapter that blocks real loading unless future policy permits it."""

    name = "ollama"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}

    def load_model(self, model_name: str) -> BackendLoadResult:
        if not bool(self.policy.get("allow_real_model_load", False)):
            return BackendLoadResult(
                status="BLOCKED",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=["ollama_real_model_load_blocked_by_policy"],
                warnings=["Ollama adapter is a safe stub in v10.9."],
            )
        return BackendLoadResult(
            status="BLOCKED",
            model_name=model_name,
            backend=self.name,
            loaded=False,
            errors=["ollama_real_model_load_not_implemented"],
            warnings=[],
        )

    def generate(
        self,
        model_name: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> BackendGenerateResult:
        return BackendGenerateResult(
            status="BLOCKED",
            model_name=model_name,
            backend=self.name,
            text="",
            tokens_in=len(prompt.split()),
            tokens_out=0,
            duration_ms=0,
            errors=["ollama_generate_blocked_in_v10_9"],
            warnings=["No network or Ollama API call is made."],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=["No real Ollama model was loaded."],
        )

    def health_check(self) -> BackendHealthResult:
        return BackendHealthResult(
            status="STUB",
            backend=self.name,
            available=False,
            errors=[],
            warnings=["Ollama backend is present but real load is disabled by default."],
        )
