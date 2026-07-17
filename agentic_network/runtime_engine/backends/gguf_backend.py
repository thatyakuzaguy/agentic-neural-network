"""Safe GGUF backend adapter stub for future local model integration."""

from __future__ import annotations

from typing import Any

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)


class GGUFBackend:
    """GGUF adapter that avoids scanning or loading model files in v10.9."""

    name = "gguf"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}

    def load_model(self, model_name: str) -> BackendLoadResult:
        return BackendLoadResult(
            status="BLOCKED",
            model_name=model_name,
            backend=self.name,
            loaded=False,
            errors=["gguf_real_model_load_blocked_by_policy"],
            warnings=["GGUF adapter does not scan /models or load files in v10.9."],
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
            errors=["gguf_generate_blocked_in_v10_9"],
            warnings=["No GGUF file is opened."],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=["No real GGUF model was loaded."],
        )

    def health_check(self) -> BackendHealthResult:
        return BackendHealthResult(
            status="STUB",
            backend=self.name,
            available=False,
            errors=[],
            warnings=["GGUF backend is present but real load is disabled by default."],
        )
