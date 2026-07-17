"""Pipeline orchestration for the local multi-agent network."""

from __future__ import annotations

from typing import Any

__all__ = ["PipelineResult", "PipelineRunner"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from agentic_network.pipeline.runner import PipelineResult, PipelineRunner

        return {"PipelineResult": PipelineResult, "PipelineRunner": PipelineRunner}[name]
    raise AttributeError(name)
