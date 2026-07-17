"""Deterministic mock backend for safe runtime tests and default local execution."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)


class MockBackend:
    """Safe backend that performs deterministic in-process generation."""

    name = "mock"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}
        self.loaded: set[str] = set()

    def load_model(self, model_name: str) -> BackendLoadResult:
        self.loaded.add(model_name)
        return BackendLoadResult(
            status="LOADED",
            model_name=model_name,
            backend=self.name,
            loaded=True,
            errors=[],
            warnings=[],
        )

    def generate(
        self,
        model_name: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> BackendGenerateResult:
        started = perf_counter()
        text = (
            f"[mock:{model_name}] Sequential backend generation completed. "
            f"Prompt preview: {prompt.strip()[:160]}"
        )
        return BackendGenerateResult(
            status="SUCCESS",
            model_name=model_name,
            backend=self.name,
            text=text,
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            duration_ms=max(0, int((perf_counter() - started) * 1000)),
            errors=[],
            warnings=[],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        self.loaded.discard(model_name)
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=[],
        )

    def health_check(self) -> BackendHealthResult:
        return BackendHealthResult(
            status="HEALTHY",
            backend=self.name,
            available=True,
            errors=[],
            warnings=[],
        )
