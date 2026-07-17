"""Base embedded local backend foundation for ANN."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)


class EmbeddedBackend:
    """Safe local backend wrapper that never loads real weights by default."""

    name = "embedded"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}
        self.loaded: set[str] = set()

    def load_model(self, model_name: str) -> BackendLoadResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendLoadResult(
                status="BLOCKED",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=["embedded_real_model_load_blocked_by_policy"],
                warnings=["No embedded model weights were opened."],
            )
        return BackendLoadResult(
            status="UNAVAILABLE",
            model_name=model_name,
            backend=self.name,
            loaded=False,
            errors=["embedded_backend_has_no_concrete_loader"],
            warnings=["Use llama_cpp or qwen_local for concrete local backends."],
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
            errors=["embedded_generate_requires_loaded_model"],
            warnings=["No terminal, internet, download, or training was used."],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        self.loaded.discard(model_name)
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=["No real embedded model was loaded."],
        )

    def health_check(self) -> BackendHealthResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendHealthResult(
                status="BLOCKED_BY_POLICY",
                backend=self.name,
                available=False,
                errors=["real_model_load_blocked_by_policy"],
                warnings=["Embedded backend is present but real load is disabled."],
            )
        return BackendHealthResult(
            status="AVAILABLE",
            backend=self.name,
            available=True,
            errors=[],
            warnings=["Embedded backend foundation is available; concrete loader required."],
        )

