"""Runtime artifact generation for ANN model routing plans."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.model_routing.models import DEFAULT_VRAM_POLICY, PipelineRoutingPlan
from agentic_network.model_routing.router import resolve_model_route


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "model_routing"
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


def build_pipeline_routing_plan(
    stages: list[str],
    mode: str = "FAST",
    *,
    run_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> PipelineRoutingPlan:
    """Build a sequential routing plan and write 72/73 artifacts."""

    normalized_mode = mode.strip().upper()
    errors: list[str] = []
    warnings: list[str] = []
    output_dir = _resolve_output_dir(run_dir, errors)
    clean_stages = [stage.strip().lower() for stage in stages if stage.strip()]
    decisions = [
        resolve_model_route(stage, normalized_mode, config_path=config_path)
        for stage in clean_stages
    ]
    for decision in decisions:
        warnings.extend(decision.warnings)
        errors.extend(decision.errors)
    if not clean_stages:
        errors.append("stages_required")
    status = _status_for(decisions, errors)
    vram_policy = decisions[0].vram_policy if decisions else DEFAULT_VRAM_POLICY
    plan_without_artifacts = PipelineRoutingPlan(
        status=status,
        mode=normalized_mode,
        vram_policy=vram_policy,
        stages=clean_stages,
        decisions=[decision.to_dict() for decision in decisions],
        estimated_profile={
            "execution": "sequential",
            "stage_count": len(clean_stages),
            "parallel_llm_loads": 0,
            "vram_policy": vram_policy,
            "runtime_engine": "sequential",
            "max_loaded_models": 1,
        },
        artifacts=[],
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )
    artifacts = [] if errors and output_dir is None else _write_artifacts(output_dir or _standalone_output_dir(), plan_without_artifacts)
    return PipelineRoutingPlan(**{**plan_without_artifacts.to_dict(), "artifacts": artifacts})


def _resolve_output_dir(run_dir: str | Path | None, errors: list[str]) -> Path | None:
    if run_dir is None:
        return _standalone_output_dir()
    raw = str(run_dir)
    if _has_traversal(raw):
        errors.append("run_dir_path_traversal_blocked")
        return None
    resolved = Path(run_dir).resolve()
    if _has_protected_part(resolved):
        errors.append(f"run_dir_protected_path_blocked:{resolved}")
        return None
    return resolved


def _standalone_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return DEFAULT_OUTPUT_ROOT / timestamp


def _status_for(decisions: list[Any], errors: list[str]) -> str:
    if errors:
        return "INVALID"
    if any(decision.status == "BLOCKED" for decision in decisions):
        return "BLOCKED"
    if any(decision.status == "INVALID" for decision in decisions):
        return "INVALID"
    if any(decision.status == "FALLBACK" for decision in decisions):
        return "FALLBACK"
    return "VALID"


def _write_artifacts(output_dir: Path, plan: PipelineRoutingPlan) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_md = output_dir / "72_model_routing_plan.md"
    plan_json = output_dir / "72_model_routing_plan.json"
    trace_md = output_dir / "73_model_routing_trace.md"
    plan_json.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    plan_md.write_text(_plan_markdown(plan), encoding="utf-8")
    trace_md.write_text(_trace_markdown(plan), encoding="utf-8")
    return [str(plan_md), str(plan_json), str(trace_md)]


def _plan_markdown(plan: PipelineRoutingPlan) -> str:
    lines = [
        "# ANN Model Routing Plan",
        "",
        f"Status: {plan.status}",
        f"Mode: {plan.mode}",
        f"VRAM policy: {plan.vram_policy}",
        "Sequential required: True",
        "",
        "## Stages",
    ]
    for decision in plan.decisions:
        lines.append(
            f"- {decision['agent_name']}: {decision['selected_model']} "
            f"(status={decision['status']}, fallback={decision['fallback_model']})"
        )
    return "\n".join(lines).rstrip() + "\n"


def _trace_markdown(plan: PipelineRoutingPlan) -> str:
    lines = [
        "# ANN Model Routing Trace",
        "",
        "ANN loads one routed stage at a time. Heavy LLM parallelism is not implied by this plan.",
        "",
    ]
    for index, decision in enumerate(plan.decisions, start=1):
        lines.extend(
            [
                f"## {index}. {decision['agent_name']}",
                f"- Mode: {decision['mode']}",
                f"- Selected model: {decision['selected_model']}",
                f"- Fallback model: {decision['fallback_model']}",
                f"- Sequential required: {decision['sequential_required']}",
                f"- Reason: {decision['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _has_traversal(raw: str) -> bool:
    return any(part == ".." for part in raw.replace("\\", "/").split("/"))


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


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
