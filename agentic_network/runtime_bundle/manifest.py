"""Typed manifest objects for the ANN Runtime Bundle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PythonRuntime:
    """Detected Python runtime candidate."""

    kind: str
    executable: str
    version: str
    priority: int
    active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeManifest:
    """Read-only manifest of locally available ANN runtime dependencies."""

    python_version: str
    python_executable: str
    python_runtime: PythonRuntime
    python_candidates: list[PythonRuntime]
    torch_version: str | None
    transformers_version: str | None
    pyside_version: str | None
    runtime_engine_version: str
    installed_models: list[dict[str, Any]]
    available_backends: list[str]
    runtime_dependencies: list[dict[str, Any]]
    estimated_size_mb: float
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["python_runtime"] = self.python_runtime.to_dict()
        payload["python_candidates"] = [candidate.to_dict() for candidate in self.python_candidates]
        return payload
