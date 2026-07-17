"""Sequential agent executor for ANN runtime engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from agentic_network.model_routing.router import resolve_model_route
from agentic_network.runtime_engine.backend_registry import get_backend
from agentic_network.runtime_engine.loader import (
    get_loaded_models,
    get_runtime_metrics,
    load_model,
    record_generate_status,
    unload_model,
)
from agentic_network.runtime_engine.model_inventory import load_model_inventory, resolve_model_record
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request
from agentic_network.runtime_engine.models import RuntimeExecutionResult


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "runtime_engine"
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


def execute_agent_runtime(
    agent_name: str,
    task: str,
    execution_mode: str = "FAST",
    run_dir: str | Path | None = None,
    backend_name: str | None = None,
) -> RuntimeExecutionResult:
    """Execute one logical agent through load -> run -> unload."""

    warnings: list[str] = []
    errors: list[str] = []
    output_dir = _resolve_output_dir(run_dir, errors)
    route = resolve_model_route(agent_name, execution_mode)
    warnings.extend(route.warnings)
    errors.extend(route.errors)
    if route.status in {"INVALID", "BLOCKED"}:
        result = RuntimeExecutionResult(
            status="BLOCKED",
            agent_name=route.agent_name,
            selected_model=route.selected_model,
            execution_mode=route.mode,
            backend_name=backend_name or "mock",
            backend_status="BLOCKED",
            load_status="SKIPPED",
            generate_status="SKIPPED",
            unload_status="SKIPPED",
            load_time_ms=0,
            execution_time_ms=0,
            unload_time_ms=0,
            peak_vram_mb=0,
            active_models=len(get_loaded_models()),
            parallel_llm_loads=max(0, len(get_loaded_models()) - 1),
            artifact_paths=[],
            warnings=_dedupe(warnings),
            errors=_dedupe(errors or ["model_route_blocked"]),
        )
        return result
    inventory = load_model_inventory()
    model_record = resolve_model_record(route.selected_model)
    policy = load_model_policy()
    requested_backend = backend_name or policy.default_backend or "mock"
    if backend_name is None and requested_backend != "mock" and model_record is not None and model_record.enabled:
        requested_backend = model_record.backend
    policy_decision = validate_model_load_request(
        route.selected_model,
        requested_backend,
        route.mode,
        policy=policy,
    )
    try:
        backend = get_backend(requested_backend)
    except ValueError as exc:
        return RuntimeExecutionResult(
            status="BLOCKED",
            agent_name=route.agent_name,
            selected_model=route.selected_model,
            execution_mode=route.mode,
            backend_name=str(requested_backend or ""),
            backend_status="INVALID",
            load_status="SKIPPED",
            generate_status="SKIPPED",
            unload_status="SKIPPED",
            load_time_ms=0,
            execution_time_ms=0,
            unload_time_ms=0,
            peak_vram_mb=0,
            active_models=len(get_loaded_models()),
            parallel_llm_loads=max(0, len(get_loaded_models()) - 1),
            artifact_paths=[],
            warnings=[],
            errors=[str(exc)],
        )
    load = load_model(route.selected_model, backend_name=backend.name)
    warnings.extend(load.get("warnings", []))
    errors.extend(load.get("errors", []))
    if load.get("status") == "BLOCKED":
        metrics = get_runtime_metrics()
        result = RuntimeExecutionResult(
            status="BLOCKED",
            agent_name=route.agent_name,
            selected_model=route.selected_model,
            execution_mode=route.mode,
            backend_name=backend.name,
            backend_status=str(load.get("backend_status", "BLOCKED")),
            load_status=str(load.get("status", "BLOCKED")),
            generate_status="SKIPPED",
            unload_status="SKIPPED",
            load_time_ms=int(load.get("load_time_ms", 0)),
            execution_time_ms=0,
            unload_time_ms=0,
            peak_vram_mb=int(metrics.get("peak_vram_mb", 0)),
            active_models=len(get_loaded_models()),
            parallel_llm_loads=int(metrics.get("parallel_llm_loads", 0)),
            artifact_paths=[],
            warnings=_dedupe(warnings),
            errors=_dedupe(errors),
        )
        artifacts = _write_artifacts(
            output_dir,
            result,
            metrics,
            {"result": "Backend load blocked."},
            {
                "load": load,
                "model_record": model_record.to_dict() if model_record else None,
                "inventory_status": "FOUND" if model_record else "MISSING",
                "backend_policy_decision": policy_decision.to_dict(),
                "load_allowed": policy_decision.allowed,
                "real_model_load_attempted": False,
            },
            inventory.to_dict(),
            policy_decision.to_dict(),
        )
        return RuntimeExecutionResult(**{**result.to_dict(), "artifact_paths": artifacts})
    started = perf_counter()
    generation = backend.generate(route.selected_model, _agent_prompt(route.agent_name, task), options=None)
    record_generate_status(backend.name, generation.status)
    warnings.extend(generation.warnings)
    errors.extend(generation.errors)
    execution_summary = _execute_agent_stub(route.agent_name, task, route.selected_model, generation.text)
    execution_time_ms = max(0, int((perf_counter() - started) * 1000))
    unload = unload_model(route.selected_model, backend_name=backend.name)
    warnings.extend(unload.get("warnings", []))
    errors.extend(unload.get("errors", []))
    metrics = get_runtime_metrics()
    result = RuntimeExecutionResult(
        status="SUCCESS" if not errors else "FAILED",
        agent_name=route.agent_name,
        selected_model=route.selected_model,
        execution_mode=route.mode,
        backend_name=backend.name,
        backend_status=str(metrics.get("backend_status", "UNKNOWN")),
        load_status=str(load.get("status", "UNKNOWN")),
        generate_status=generation.status,
        unload_status=str(unload.get("status", "UNKNOWN")),
        load_time_ms=int(load.get("load_time_ms", 0)),
        execution_time_ms=execution_time_ms,
        unload_time_ms=int(unload.get("unload_time_ms", 0)),
        peak_vram_mb=int(metrics.get("peak_vram_mb", 0)),
        active_models=len(get_loaded_models()),
        parallel_llm_loads=int(metrics.get("parallel_llm_loads", 0)),
        artifact_paths=[],
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )
    backend_payload = {
        "load": load,
        "generate": generation.to_dict(),
        "unload": unload,
    }
    backend_payload.update(
        {
            "model_record": model_record.to_dict() if model_record else None,
            "inventory_status": "FOUND" if model_record else "MISSING",
            "backend_policy_decision": policy_decision.to_dict(),
            "load_allowed": policy_decision.allowed,
            "real_model_load_attempted": False,
        }
    )
    artifacts = _write_artifacts(
        output_dir,
        result,
        metrics,
        execution_summary,
        backend_payload,
        inventory.to_dict(),
        policy_decision.to_dict(),
    )
    return RuntimeExecutionResult(**{**result.to_dict(), "artifact_paths": artifacts})


def _agent_prompt(agent_name: str, task: str) -> str:
    return f"Agent: {agent_name}\nTask: {task.strip()}"


def _execute_agent_stub(agent_name: str, task: str, selected_model: str, generated_text: str) -> dict[str, str]:
    return {
        "agent_name": agent_name,
        "selected_model": selected_model,
        "task_preview": task.strip()[:500],
        "result": generated_text,
    }


def _write_artifacts(
    output_dir: Path,
    result: RuntimeExecutionResult,
    metrics: dict[str, Any],
    execution_summary: dict[str, str],
    backend_payload: dict[str, Any],
    inventory_snapshot: dict[str, Any],
    policy_decision: dict[str, Any],
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_md = output_dir / "74_runtime_execution.md"
    execution_json = output_dir / "74_runtime_execution.json"
    metrics_json = output_dir / "75_runtime_metrics.json"
    trace_md = output_dir / "76_runtime_trace.md"
    backend_md = output_dir / "77_backend_execution.md"
    backend_json = output_dir / "77_backend_execution.json"
    inventory_json = output_dir / "78_model_inventory_snapshot.json"
    policy_json = output_dir / "79_model_policy_decision.json"
    execution_payload = {**result.to_dict(), "execution_summary": execution_summary}
    execution_json.write_text(json.dumps(execution_payload, indent=2), encoding="utf-8")
    metrics_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    execution_md.write_text(_execution_markdown(result, execution_summary), encoding="utf-8")
    trace_md.write_text(_trace_markdown(result), encoding="utf-8")
    backend_json.write_text(json.dumps({"result": result.to_dict(), **backend_payload}, indent=2), encoding="utf-8")
    backend_md.write_text(_backend_markdown(result, backend_payload), encoding="utf-8")
    inventory_json.write_text(json.dumps(inventory_snapshot, indent=2), encoding="utf-8")
    policy_json.write_text(json.dumps(policy_decision, indent=2), encoding="utf-8")
    return [
        str(execution_md),
        str(execution_json),
        str(metrics_json),
        str(trace_md),
        str(backend_md),
        str(backend_json),
        str(inventory_json),
        str(policy_json),
    ]


def _execution_markdown(result: RuntimeExecutionResult, execution_summary: dict[str, str]) -> str:
    return "\n".join(
        [
            "# ANN Runtime Execution",
            "",
            f"Status: {result.status}",
            f"Agent: {result.agent_name}",
            f"Execution mode: {result.execution_mode}",
            f"Backend: {result.backend_name}",
            f"Backend status: {result.backend_status}",
            f"Selected model: {result.selected_model}",
            f"Load status: {result.load_status}",
            f"Generate status: {result.generate_status}",
            f"Unload status: {result.unload_status}",
            f"Active models after unload: {result.active_models}",
            f"Parallel LLM loads: {result.parallel_llm_loads}",
            f"Generated at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            "",
            "## Execution Summary",
            execution_summary["result"],
            "",
        ]
    )


def _trace_markdown(result: RuntimeExecutionResult) -> str:
    return "\n".join(
        [
            "# ANN Runtime Trace",
            "",
            f"1. Load model: {result.selected_model}",
            f"2. Generate with backend: {result.backend_name}",
            f"3. Execute agent: {result.agent_name}",
            f"4. Unload model: {result.selected_model}",
            "5. Continue with next agent only after unload completes.",
            "",
            "Policy: active_models <= 1 and parallel_llm_loads = 0.",
            "",
        ]
    )


def _backend_markdown(result: RuntimeExecutionResult, backend_payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ANN Backend Execution",
            "",
            f"Backend: {result.backend_name}",
            f"Backend status: {result.backend_status}",
            f"Load status: {result.load_status}",
            f"Generate status: {result.generate_status}",
            f"Unload status: {result.unload_status}",
            "",
            "## Safety",
            "- No model download is performed.",
            "- No training is performed.",
            "- No adapters or datasets are modified.",
            "",
            "## Backend Payload Keys",
            *[f"- {key}" for key in sorted(backend_payload)],
            "",
        ]
    )


def _resolve_output_dir(run_dir: str | Path | None, errors: list[str]) -> Path:
    if run_dir is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return DEFAULT_OUTPUT_ROOT / timestamp
    raw = str(run_dir)
    if any(part == ".." for part in raw.replace("\\", "/").split("/")):
        errors.append("run_dir_path_traversal_blocked")
        return DEFAULT_OUTPUT_ROOT / "blocked"
    resolved = Path(run_dir).resolve()
    if any(part.lower() in PROTECTED_PARTS for part in resolved.parts):
        errors.append(f"run_dir_protected_path_blocked:{resolved}")
        return DEFAULT_OUTPUT_ROOT / "blocked"
    return resolved


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
