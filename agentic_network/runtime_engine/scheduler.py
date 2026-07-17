"""Sequential scheduler for ANN runtime engine."""

from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine.executor import execute_agent_runtime
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.models import RuntimePipelineResult


def run_pipeline_sequential(
    stages: list[str],
    execution_mode: str = "FAST",
    *,
    task: str = "",
    run_dir: str | Path | None = None,
    backend_name: str | None = None,
) -> RuntimePipelineResult:
    """Run stages one after another, never allowing concurrent LLM loads."""

    results = []
    warnings: list[str] = []
    errors: list[str] = []
    for stage in stages:
        result = execute_agent_runtime(
            stage,
            task or f"Run {stage}",
            execution_mode=execution_mode,
            run_dir=run_dir,
            backend_name=backend_name,
        )
        results.append(result.to_dict())
        warnings.extend(result.warnings)
        errors.extend(result.errors)
        if len(get_loaded_models()) > 1:
            errors.append("active_models_exceeded_policy")
            break
    metrics = get_runtime_metrics()
    artifact_paths = []
    for result in results:
        artifact_paths.extend(str(path) for path in result.get("artifact_paths", []))
    return RuntimePipelineResult(
        status="SUCCESS" if not errors else "FAILED",
        execution_mode=execution_mode.strip().upper(),
        stages=[stage.strip().lower() for stage in stages],
        results=results,
        active_models=len(get_loaded_models()),
        parallel_llm_loads=int(metrics.get("parallel_llm_loads", 0)),
        artifact_paths=artifact_paths,
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
