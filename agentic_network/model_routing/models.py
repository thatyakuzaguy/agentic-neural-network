"""Typed models for ANN model routing decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_MODES = {"FAST", "POWERFUL"}
VALID_STATUSES = {"VALID", "FALLBACK", "INVALID", "BLOCKED"}
DEFAULT_VRAM_POLICY = "SEQUENTIAL"


@dataclass(frozen=True)
class ModelRouteDecision:
    """Read-only decision for one agent/stage model route."""

    status: str
    agent_name: str
    mode: str
    selected_model: str
    fallback_model: str
    vram_policy: str
    sequential_required: bool
    reason: str
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PipelineRoutingPlan:
    """Sequential routing plan for a pipeline run."""

    status: str
    mode: str
    vram_policy: str
    stages: list[str]
    decisions: list[dict[str, Any]]
    estimated_profile: dict[str, Any]
    artifacts: list[str]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
