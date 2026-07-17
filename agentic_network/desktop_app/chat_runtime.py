"""Native Chat-to-Run runtime for ANN Desktop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.action_planner_agent.runtime import run_action_plan
from agentic_network.consensus_agent.runtime import run_consensus_decision
from agentic_network.conversation_orchestrator.runtime import (
    CONVERSATION_ORCHESTRATOR_MODEL_ID,
    render_pipeline_input,
    render_user_response,
    run_conversation_orchestrator,
)
from agentic_network.desktop_app.conversation_store import ConversationStore
from agentic_network.desktop_app.project_brain import get_project_history
from agentic_network.desktop_app.workspace_store import ProjectRecord, WorkspaceStore
from agentic_network.human_approval_agent.runtime import APPROVAL_TOKEN, authorize_apply
from agentic_network.model_routing.runtime import build_pipeline_routing_plan
from agentic_network.project_patch_apply_agent.runtime import apply_project_patch
from agentic_network.project_self_healing_agent.runtime import run_project_self_healing
from agentic_network.project_test_runner_agent.runtime import run_project_verification
from agentic_network.runtime_bundle.runtime import build_runtime_manifest, write_runtime_bundle_artifacts
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics, reset_runtime_state
from agentic_network.runtime_engine.model_policy import load_model_policy
from agentic_network.runtime_engine.scheduler import run_pipeline_sequential
from agentic_network.desktop_app.views.confirmation_dialog import (
    ConfirmationDecision,
    build_confirmation_request,
    record_confirmation_trace,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
DEFAULT_CHAT_STAGES = ["product", "architect", "code", "test", "security", "reviewer"]


@dataclass(frozen=True)
class ChatTaskResult:
    """Result of submitting one chat task to ANN runtime."""

    status: str
    conversation_id: str
    run_id: str
    run_dir: str
    execution_mode: str
    current_agent: str
    current_model: str
    stage: str
    runtime_status: str
    backend: str
    routing_mode: str
    model_policy: str
    max_loaded_models: int
    vram_policy: str
    peak_vram_mb: int
    loaded_models: list[str]
    parallel_loads: int
    recent_artifact: str | None
    artifacts: list[str]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatActionResult:
    """Result of one desktop chat action button."""

    action: str
    status: str
    conversation_id: str
    run_id: str | None
    message: str
    artifacts: list[str]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_conversation(
    *,
    title: str = "ANN Conversation",
    execution_mode: str = "FAST",
    project_id: str | None = None,
    store: ConversationStore | None = None,
) -> Any:
    """Create a persisted chat conversation."""

    return (store or ConversationStore()).create_conversation(
        title=title,
        execution_mode=execution_mode,
        project_id=project_id,
    )


def submit_chat_task(
    conversation_id: str,
    prompt: str,
    execution_mode: str,
    project_id: str | None,
    *,
    store: ConversationStore | None = None,
    workspace_store: WorkspaceStore | None = None,
    stages: list[str] | None = None,
) -> ChatTaskResult:
    """Submit a chat prompt to the existing model routing and sequential runtime."""

    conversation_store = store or ConversationStore()
    workspace = workspace_store or WorkspaceStore()
    bundle = conversation_store.load_conversation(conversation_id)
    mode = _normalize_mode(execution_mode or bundle.conversation.execution_mode)
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("prompt is required.")
    project = _resolve_project(project_id, workspace)
    run_root = Path(project.runs_path).resolve() if project else DEFAULT_RUNS_ROOT
    run_root.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id("chat")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    conversation_store.append_message(conversation_id, "user", clean_prompt)
    bundle_after_user_message = conversation_store.load_conversation(conversation_id)
    orchestrator = run_conversation_orchestrator(
        message=clean_prompt,
        conversation_id=conversation_id,
        conversation_bundle=bundle_after_user_message,
        project_context=_project_context(project),
        run_dir=run_dir,
    )
    if orchestrator.status in {"BLOCKED", "NEEDS_CLARIFICATION"} or (
        orchestrator.contract.requires_human_approval
        and orchestrator.contract.primary_intent == "patch_application"
    ):
        status = "WAITING_APPROVAL" if orchestrator.contract.requires_human_approval else orchestrator.status
        summary = {
            "task": clean_prompt,
            "prompt": clean_prompt,
            "timestamp": _now(),
            "chat_status": status,
            "status": status,
            "conversation_id": conversation_id,
            "project_id": project_id,
            "execution_mode": mode,
            "current_agent": "conversation_orchestrator",
            "current_model": CONVERSATION_ORCHESTRATOR_MODEL_ID,
            "stage": "0/0",
            "runtime_status": orchestrator.status,
            "backend": orchestrator.backend_status,
            "routing_mode": mode,
            "recommended_pipeline": orchestrator.contract.recommended_pipeline,
            "recommended_agents": orchestrator.contract.recommended_agents,
            "intent_contract": orchestrator.contract.to_dict(),
            "pipeline_route": orchestrator.route.to_dict(),
            "model_lifecycle": orchestrator.lifecycle,
            "model_policy": "REAL MODEL LOAD BLOCKED BY POLICY"
            if not load_model_policy().allow_real_model_load
            else "REAL MODEL LOAD ENABLED",
            "max_loaded_models": load_model_policy().max_loaded_models,
            "vram_policy": "SEQUENTIAL",
            "peak_vram_mb": get_runtime_metrics().get("peak_vram_mb", 0),
            "loaded_models": get_loaded_models(),
            "parallel_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
            "artifacts": orchestrator.artifacts,
            "model_routing_decisions": [],
            "runtime_results": [],
            "warnings": orchestrator.warnings,
            "errors": orchestrator.errors,
        }
        _write_json(run_dir / "summary.json", summary)
        assistant_message = render_user_response(summary)
        conversation_store.append_message(
            conversation_id,
            "assistant",
            assistant_message,
            agent="conversation_orchestrator",
            model=CONVERSATION_ORCHESTRATOR_MODEL_ID,
        )
        all_artifacts = _dedupe([*orchestrator.artifacts, str(run_dir / "summary.json")])
        conversation_store.attach_run(conversation_id, run_id, status, all_artifacts)
        conversation_store.update_conversation_status(conversation_id, status)
        return ChatTaskResult(
            status=status,
            conversation_id=conversation_id,
            run_id=run_id,
            run_dir=str(run_dir),
            execution_mode=mode,
            current_agent="conversation_orchestrator",
            current_model=CONVERSATION_ORCHESTRATOR_MODEL_ID,
            stage="0/0",
            runtime_status=orchestrator.status,
            backend=orchestrator.backend_status,
            routing_mode=mode,
            model_policy=summary["model_policy"],
            max_loaded_models=int(summary["max_loaded_models"]),
            vram_policy="SEQUENTIAL",
            peak_vram_mb=int(summary["peak_vram_mb"]),
            loaded_models=get_loaded_models(),
            parallel_loads=int(summary["parallel_loads"]),
            recent_artifact=all_artifacts[-1] if all_artifacts else None,
            artifacts=all_artifacts,
            errors=orchestrator.errors,
            warnings=orchestrator.warnings,
        )
    reset_runtime_state()
    selected_stages = stages or orchestrator.route.stages or DEFAULT_CHAT_STAGES
    pipeline_task = render_pipeline_input(orchestrator.contract, orchestrator.prompt_compilation)
    routing = build_pipeline_routing_plan(selected_stages, mode=mode, run_dir=run_dir)
    pipeline = run_pipeline_sequential(selected_stages, execution_mode=mode, task=pipeline_task, run_dir=run_dir)
    metrics = get_runtime_metrics()
    policy = load_model_policy()
    last_result = pipeline.results[-1] if pipeline.results else {}
    current_agent = str(last_result.get("agent_name") or selected_stages[-1])
    current_model = str(last_result.get("selected_model") or "")
    artifacts = _dedupe([*routing.artifacts, *pipeline.artifact_paths])
    summary = {
        "task": clean_prompt,
        "prompt": clean_prompt,
        "timestamp": _now(),
        "chat_status": pipeline.status,
        "status": pipeline.status,
        "conversation_id": conversation_id,
        "project_id": project_id,
        "execution_mode": mode,
        "current_agent": current_agent,
        "current_model": current_model,
        "stage": f"{len(pipeline.results)}/{len(selected_stages)}",
        "runtime_status": pipeline.status,
        "backend": str(last_result.get("backend_name") or "mock"),
        "routing_mode": mode,
        "model_policy": "REAL MODEL LOAD BLOCKED BY POLICY"
        if not policy.allow_real_model_load
        else "REAL MODEL LOAD ENABLED",
        "max_loaded_models": policy.max_loaded_models,
        "vram_policy": "SEQUENTIAL",
        "peak_vram_mb": metrics.get("peak_vram_mb", 0),
        "loaded_models": get_loaded_models(),
        "parallel_loads": pipeline.parallel_llm_loads,
        "artifacts": artifacts,
        "model_routing_decisions": routing.decisions,
        "runtime_results": pipeline.results,
        "intent_contract": orchestrator.contract.to_dict(),
        "conversation_orchestrator": orchestrator.to_dict(),
        "recommended_pipeline": orchestrator.contract.recommended_pipeline,
        "recommended_agents": orchestrator.contract.recommended_agents,
    }
    _write_json(run_dir / "summary.json", summary)
    status = pipeline.status
    assistant_message = render_user_response(summary)
    conversation_store.append_message(
        conversation_id,
        "assistant",
        assistant_message,
        agent=current_agent,
        model=current_model,
    )
    brain_snapshot = (
        get_project_history(project_id, workspace_store=workspace, conversation_store=conversation_store)
        if project_id
        else {"project_id": None, "status": "NO_PROJECT"}
    )
    runtime_bundle_artifacts = write_runtime_bundle_artifacts(run_dir, build_runtime_manifest())
    confirmation_trace = record_confirmation_trace(
        run_dir,
        build_confirmation_request(
            action="Pending Desktop Confirmation",
            project=project.name if project else "no-project",
            risk="LOW",
        ),
    )
    chat_artifacts = _write_chat_artifacts(
        conversation_store,
        conversation_id,
        summary,
        brain_snapshot,
        run_dir,
    )
    all_artifacts = _dedupe(
        [
            *orchestrator.artifacts,
            *artifacts,
            *runtime_bundle_artifacts,
            confirmation_trace,
            *chat_artifacts,
            str(run_dir / "summary.json"),
        ]
    )
    conversation_store.attach_run(conversation_id, run_id, status, all_artifacts)
    conversation_store.update_conversation_status(conversation_id, status)
    return ChatTaskResult(
        status=status,
        conversation_id=conversation_id,
        run_id=run_id,
        run_dir=str(run_dir),
        execution_mode=mode,
        current_agent=current_agent,
        current_model=current_model,
        stage=f"{len(pipeline.results)}/{len(selected_stages)}",
        runtime_status=pipeline.status,
        backend=str(last_result.get("backend_name") or "mock"),
        routing_mode=mode,
        model_policy="REAL MODEL LOAD BLOCKED BY POLICY"
        if not policy.allow_real_model_load
        else "REAL MODEL LOAD ENABLED",
        max_loaded_models=policy.max_loaded_models,
        vram_policy="SEQUENTIAL",
        peak_vram_mb=int(metrics.get("peak_vram_mb", 0)),
        loaded_models=get_loaded_models(),
        parallel_loads=pipeline.parallel_llm_loads,
        recent_artifact=all_artifacts[-1] if all_artifacts else None,
        artifacts=all_artifacts,
        errors=pipeline.errors,
        warnings=pipeline.warnings,
    )


def approve_action(
    conversation_id: str,
    *,
    approval_token: str | None = None,
    approve_apply: bool = False,
    store: ConversationStore | None = None,
) -> ChatActionResult:
    """Run existing Human Approval gate for the latest attached run."""

    conversation_store = store or ConversationStore()
    bundle = conversation_store.load_conversation(conversation_id)
    run_dir = _latest_run_dir(bundle)
    if run_dir is None:
        return _action_result("approve", "BLOCKED", conversation_id, None, "No run is attached.", [], ["missing_run"], [])
    result = authorize_apply(
        run_dir,
        approval_token=approval_token,
        approve_apply=approve_apply,
        required_artifacts=(),
        require_merge_readiness=False,
    )
    record_confirmation_trace(
        run_dir,
        build_confirmation_request(action="Approve", project="latest-run", risk="MEDIUM"),
        ConfirmationDecision(
            action="Approve",
            confirmed=approve_apply,
            token_provided=bool((approval_token or "").strip()),
            understands_risk=approve_apply,
            create_backup=False,
            cancelled=False,
        ),
    )
    status = "APPROVED" if result.decision == "Approved" and result.validation_passed else "DENIED"
    conversation_store.append_message(conversation_id, "assistant", f"Approval result: {status}")
    return _action_result("approve", status, conversation_id, run_dir.name, result.decision, [result.artifact_path], result.validation_errors, result.warnings)


def reject_action(
    conversation_id: str,
    *,
    store: ConversationStore | None = None,
) -> ChatActionResult:
    """Reject by rerunning existing Consensus and Action Planner for the latest run."""

    conversation_store = store or ConversationStore()
    bundle = conversation_store.load_conversation(conversation_id)
    run_dir = _latest_run_dir(bundle)
    if run_dir is None:
        return _action_result("reject", "BLOCKED", conversation_id, None, "No run is attached.", [], ["missing_run"], [])
    consensus = run_consensus_decision(run_dir, runs_root=run_dir.parent)
    action = run_action_plan(run_dir, runs_root=run_dir.parent)
    artifacts = [*consensus.artifacts, *action.artifacts]
    message = f"Rejected for review. Next action: {action.recommended_next_action}"
    conversation_store.append_message(conversation_id, "assistant", message)
    return _action_result("reject", action.status, conversation_id, run_dir.name, message, artifacts, action.validation_errors, action.validation_warnings)


def run_tests_action(
    conversation_id: str,
    *,
    confirm_run: bool = False,
    store: ConversationStore | None = None,
    workspace_store: WorkspaceStore | None = None,
) -> ChatActionResult:
    """Run existing Project Verification for the conversation project."""

    conversation_store = store or ConversationStore()
    workspace = workspace_store or WorkspaceStore()
    bundle = conversation_store.load_conversation(conversation_id)
    project = _resolve_project(bundle.conversation.project_id, workspace)
    run_dir = _latest_run_dir(bundle)
    if project is None or run_dir is None:
        return _action_result("run_tests", "BLOCKED", conversation_id, run_dir.name if run_dir else None, "Project or run missing.", [], ["missing_project_or_run"], [])
    result = run_project_verification(project.root_path, run_dir=run_dir, confirm_run=confirm_run)
    conversation_store.append_message(conversation_id, "assistant", f"Project verification: {result.status}")
    return _action_result("run_tests", result.status, conversation_id, run_dir.name, result.test_summary, result.artifacts, result.validation_errors, result.validation_warnings)


def apply_patch_action(
    conversation_id: str,
    *,
    patch_file: str | Path | None = None,
    approval_token: str | None = None,
    confirm_apply: bool = False,
    store: ConversationStore | None = None,
    workspace_store: WorkspaceStore | None = None,
) -> ChatActionResult:
    """Run existing Project Patch Apply gate for a project patch."""

    conversation_store = store or ConversationStore()
    workspace = workspace_store or WorkspaceStore()
    bundle = conversation_store.load_conversation(conversation_id)
    project = _resolve_project(bundle.conversation.project_id, workspace)
    run_dir = _latest_run_dir(bundle)
    selected_patch = Path(patch_file) if patch_file else _latest_patch(run_dir)
    if project is None or selected_patch is None:
        return _action_result("apply_patch", "BLOCKED", conversation_id, run_dir.name if run_dir else None, "Project or patch missing.", [], ["missing_project_or_patch"], [])
    result = apply_project_patch(
        project.root_path,
        selected_patch,
        approval_token=approval_token,
        confirm_apply=confirm_apply,
        dry_run=not confirm_apply,
    )
    record_confirmation_trace(
        run_dir or Path(project.runs_path),
        build_confirmation_request(
            action="Apply Patch",
            project=project.name,
            patch=selected_patch.name,
            risk="MEDIUM",
            files=1,
        ),
        ConfirmationDecision(
            action="Apply Patch",
            confirmed=confirm_apply,
            token_provided=bool((approval_token or "").strip()),
            understands_risk=confirm_apply,
            create_backup=confirm_apply,
            cancelled=False,
        ),
    )
    artifacts = [*result.backups_created]
    if result.retry_patch_generated:
        artifacts.append(result.retry_patch_generated)
    conversation_store.append_message(conversation_id, "assistant", f"Project patch apply: {result.status}")
    return _action_result("apply_patch", result.status, conversation_id, run_dir.name if run_dir else None, result.next_action, artifacts, result.validation_errors, result.validation_warnings)


def retry_action(
    conversation_id: str,
    *,
    approval_token: str | None = None,
    confirm_retry: bool = False,
    max_attempts: int = 3,
    store: ConversationStore | None = None,
    workspace_store: WorkspaceStore | None = None,
) -> ChatActionResult:
    """Run existing Project Self Healing retry loop."""

    conversation_store = store or ConversationStore()
    workspace = workspace_store or WorkspaceStore()
    bundle = conversation_store.load_conversation(conversation_id)
    project = _resolve_project(bundle.conversation.project_id, workspace)
    run_dir = _latest_run_dir(bundle)
    if project is None or run_dir is None:
        return _action_result("retry", "BLOCKED", conversation_id, run_dir.name if run_dir else None, "Project or run missing.", [], ["missing_project_or_run"], [])
    result = run_project_self_healing(
        project.root_path,
        run_dir=run_dir,
        max_attempts=max_attempts,
        approval_token=approval_token,
        confirm_retry=confirm_retry,
    )
    record_confirmation_trace(
        run_dir,
        build_confirmation_request(action="Retry", project=project.name, risk="MEDIUM"),
        ConfirmationDecision(
            action="Retry",
            confirmed=confirm_retry,
            token_provided=bool((approval_token or "").strip()),
            understands_risk=confirm_retry,
            create_backup=True,
            cancelled=False,
        ),
    )
    conversation_store.append_message(conversation_id, "assistant", f"Project self healing: {result.status}")
    return _action_result("retry", result.status, conversation_id, run_dir.name, result.next_action, result.artifacts, result.validation_errors, result.validation_warnings)


def _write_chat_artifacts(
    store: ConversationStore,
    conversation_id: str,
    summary: dict[str, Any],
    brain_snapshot: dict[str, Any],
    run_dir: Path,
) -> list[str]:
    conversation_dir = store.conversation_dir(conversation_id)
    session = conversation_dir / "80_chat_session.json"
    history = conversation_dir / "81_chat_history.md"
    trace = conversation_dir / "82_chat_runtime_trace.md"
    brain = conversation_dir / "83_project_brain_snapshot.json"
    project_history = run_dir / "86_project_history_snapshot.json"
    bundle = store.load_conversation(conversation_id)
    _write_json(session, {"summary": summary, "run_dir": str(run_dir)})
    history.write_text(_history_markdown(bundle.messages, summary), encoding="utf-8")
    trace.write_text(_trace_markdown(summary), encoding="utf-8")
    _write_json(brain, brain_snapshot)
    _write_json(project_history, brain_snapshot)
    return [str(session), str(history), str(trace), str(brain), str(project_history)]


def _history_markdown(messages: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = ["# ANN Chat History", "", f"Conversation: {summary.get('conversation_id')}", f"Run: {summary.get('status')}", ""]
    for message in messages:
        lines.extend([f"## {str(message.get('role', '')).title()}", str(message.get("content", "")), ""])
    return "\n".join(lines)


def _trace_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ANN Chat Runtime Trace",
            "",
            "Chat -> Model Routing -> Sequential Runtime -> Agents -> Artifacts -> Conversation Store",
            "",
            f"Execution mode: {summary.get('execution_mode')}",
            f"Current agent: {summary.get('current_agent')}",
            f"Current model: {summary.get('current_model')}",
            f"Stage: {summary.get('stage')}",
            f"Backend: {summary.get('backend')}",
            f"VRAM policy: {summary.get('vram_policy')}",
            f"Peak VRAM: {summary.get('peak_vram_mb')}",
            f"Loaded models: {summary.get('loaded_models')}",
            f"Parallel loads: {summary.get('parallel_loads')}",
            "",
            "Safety: no internet, no downloads, no training, no direct terminal execution.",
            "",
        ]
    )


def _assistant_summary(prompt: str, summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Processed request: {prompt[:160]}",
            f"Status: {summary.get('status')}",
            f"Agent: {summary.get('current_agent')}",
            f"Model: {summary.get('current_model')}",
            f"Stage: {summary.get('stage')}",
            f"Backend: {summary.get('backend')}",
        ]
    )


def _resolve_project(project_id: str | None, workspace_store: WorkspaceStore) -> ProjectRecord | None:
    if not project_id:
        return workspace_store.get_active_project()
    for project in workspace_store.load_projects():
        if project.project_id == project_id:
            return project
    return None


def _project_context(project: ProjectRecord | None) -> dict[str, Any]:
    if project is None:
        return {
            "project_path": None,
            "project_name": None,
            "environment": "local-desktop",
            "repository_state": "no-active-project",
        }
    return {
        "project_path": project.root_path,
        "project_name": project.name,
        "environment": "local-desktop",
        "repository_state": "active-project",
    }


def _latest_run_dir(bundle: Any) -> Path | None:
    if not bundle.runs:
        return None
    artifacts = bundle.runs[-1].get("artifacts", [])
    for artifact in artifacts:
        path = Path(str(artifact))
        if path.name == "summary.json":
            return path.parent.resolve()
    first = Path(str(artifacts[0])).resolve() if artifacts else None
    return first.parent if first else None


def _latest_patch(run_dir: Path | None) -> Path | None:
    if run_dir is None or not run_dir.is_dir():
        return None
    patches = sorted(run_dir.rglob("*.diff"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return patches[0] if patches else None


def _new_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_mode(value: str) -> str:
    mode = value.strip().upper()
    return mode if mode in {"FAST", "POWERFUL"} else "FAST"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _action_result(
    action: str,
    status: str,
    conversation_id: str,
    run_id: str | None,
    message: str,
    artifacts: list[str],
    errors: list[str],
    warnings: list[str],
) -> ChatActionResult:
    return ChatActionResult(
        action=action,
        status=status,
        conversation_id=conversation_id,
        run_id=run_id,
        message=message,
        artifacts=artifacts,
        errors=errors,
        warnings=warnings,
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


__all__ = [
    "APPROVAL_TOKEN",
    "ChatActionResult",
    "ChatTaskResult",
    "apply_patch_action",
    "approve_action",
    "create_conversation",
    "reject_action",
    "retry_action",
    "run_tests_action",
    "submit_chat_task",
]
