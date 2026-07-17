"""Typed models for the ANN Sequential Runtime Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeExecutionResult:
    """Result of one sequential agent runtime execution."""

    status: str
    agent_name: str
    selected_model: str
    execution_mode: str
    backend_name: str
    backend_status: str
    load_status: str
    generate_status: str
    unload_status: str
    load_time_ms: int
    execution_time_ms: int
    unload_time_ms: int
    peak_vram_mb: int
    active_models: int
    parallel_llm_loads: int
    artifact_paths: list[str]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimePipelineResult:
    """Result of running multiple stages through the sequential runtime."""

    status: str
    execution_mode: str
    stages: list[str]
    results: list[dict[str, Any]]
    active_models: int
    parallel_llm_loads: int
    artifact_paths: list[str]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
