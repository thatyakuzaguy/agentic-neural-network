"""Backend adapter contract for ANN runtime model execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendLoadResult:
    """Result of a backend model load request."""

    status: str
    model_name: str
    backend: str
    loaded: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendGenerateResult:
    """Result of a backend generation request."""

    status: str
    model_name: str
    backend: str
    text: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendUnloadResult:
    """Result of a backend unload request."""

    status: str
    model_name: str
    backend: str
    unloaded: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendHealthResult:
    """Result of checking backend health/configuration."""

    status: str
    backend: str
    available: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelBackend(Protocol):
    """Common adapter interface used by the runtime engine."""

    name: str

    def load_model(self, model_name: str) -> BackendLoadResult:
        """Load a model or return a safe blocked result."""

    def generate(
        self,
        model_name: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> BackendGenerateResult:
        """Generate text or return a safe blocked result."""

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        """Unload model resources if any were loaded."""

    def health_check(self) -> BackendHealthResult:
        """Report adapter health without side effects."""
