"""Qwen/Unsloth local backend foundation for ANN."""

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


class QwenLocalBackend:
    """Safe local Qwen backend foundation.

    The adapter performs optional dependency detection only. It does not train,
    load weights by default, write adapters/datasets, or create repo caches.
    """

    name = "qwen_local"

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {}
        self.torch_available = importlib.util.find_spec("torch") is not None
        self.transformers_available = importlib.util.find_spec("transformers") is not None
        self.unsloth_available = importlib.util.find_spec("unsloth") is not None

    def load_model(self, model_name: str) -> BackendLoadResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendLoadResult(
                status="BLOCKED",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=["qwen_local_real_model_load_blocked_by_policy"],
                warnings=["No Qwen weights, adapters, datasets, or training caches were touched."],
            )
        missing = self._missing_dependencies()
        if missing:
            return BackendLoadResult(
                status="UNAVAILABLE",
                model_name=model_name,
                backend=self.name,
                loaded=False,
                errors=[f"dependency_unavailable:{item}" for item in missing],
                warnings=["No model load was attempted."],
            )
        return BackendLoadResult(
            status="UNAVAILABLE",
            model_name=model_name,
            backend=self.name,
            loaded=False,
            errors=["qwen_local_real_loader_not_enabled"],
            warnings=["Foundation only; no real Qwen load is attempted in v11.0-v11.2."],
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
            errors=["qwen_local_generate_requires_loaded_model"],
            warnings=["No training, terminal execution, internet, or dependency install was used."],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        return BackendUnloadResult(
            status="UNLOADED",
            model_name=model_name,
            backend=self.name,
            unloaded=True,
            errors=[],
            warnings=["No real Qwen model was loaded."],
        )

    def health_check(self) -> BackendHealthResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendHealthResult(
                status="BLOCKED_BY_POLICY",
                backend=self.name,
                available=False,
                errors=["real_model_load_blocked_by_policy"],
                warnings=["Qwen local backend is present but real load is disabled."],
            )
        missing = self._missing_dependencies()
        if missing:
            return BackendHealthResult(
                status="UNAVAILABLE",
                backend=self.name,
                available=False,
                errors=[f"dependency_unavailable:{item}" for item in missing],
                warnings=[],
            )
        return BackendHealthResult(status="AVAILABLE", backend=self.name, available=True, errors=[], warnings=[])

    def _missing_dependencies(self) -> list[str]:
        missing = []
        if not self.torch_available:
            missing.append("torch")
        if not self.transformers_available:
            missing.append("transformers")
        return missing

