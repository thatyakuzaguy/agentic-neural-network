from __future__ import annotations

import json
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from agentic_network.conversation_orchestrator.runtime import (
    CONVERSATION_ORCHESTRATOR_MODEL_ID,
    build_context_bundle,
    build_intent_contract,
    compile_agent_prompts,
    detect_conflicts,
    inspect_conversation_orchestrator_model,
    repair_contract_json,
    run_conversation_orchestrator,
    select_pipeline_route,
    validate_intent_contract,
)
from agentic_network.desktop_app.chat_runtime import create_conversation, submit_chat_task
from agentic_network.desktop_app.conversation_store import ConversationStore
from agentic_network.desktop_app.project_manager import ProjectManager
from agentic_network.desktop_app.workspace_store import WorkspaceStore
from agentic_network.model_routing.router import resolve_model_route
from agentic_network.runtime_engine.loader import get_runtime_metrics, reset_runtime_state
from agentic_network.runtime_engine.model_inventory import resolve_model_record
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request


@pytest.fixture()
def stores(tmp_path: Path) -> tuple[ConversationStore, WorkspaceStore]:
    return (
        ConversationStore(tmp_path / "outputs" / "conversations"),
        WorkspaceStore(tmp_path / "config" / "ann_workspace.json", project_manager=ProjectManager(allow_temp_paths=True)),
    )


def _active_project(tmp_path: Path, workspace: WorkspaceStore):
    root = tmp_path / "projects" / "ann-target"
    root.mkdir(parents=True)
    project = workspace.add_project("ANN Target", root)
    return workspace.set_active_project(project.project_id)


def test_valid_intent_contract_preserves_traceability() -> None:
    context = build_context_bundle("Implementa login sin tocar la base de datos.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    contract = build_intent_contract(
        "Implementa login sin tocar la base de datos.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )

    validation = validate_intent_contract(contract, context)

    assert validation["status"] == "VALID"
    assert contract.contract_version == "ann_intent_contract_v1"
    assert contract.primary_intent == "implement_feature"
    assert contract.deliverables
    assert contract.explicit_constraints or contract.forbidden_actions
    assert all(item.source_message_id for item in contract.deliverables + contract.forbidden_actions)


def test_invalid_json_repair_extracts_object() -> None:
    payload = repair_contract_json("noise before {\"contract_version\":\"ann_intent_contract_v1\"} noise after")

    assert payload["contract_version"] == "ann_intent_contract_v1"


def test_invalid_json_without_object_raises() -> None:
    with pytest.raises(ValueError):
        repair_contract_json("not json")


def test_restriction_omission_is_detected() -> None:
    context = build_context_bundle("Implementa login pero no toques la base de datos.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    contract = build_intent_contract(
        "Implementa login pero no toques la base de datos.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )
    broken = replace(contract, explicit_constraints=[], forbidden_actions=[])

    validation = validate_intent_contract(broken, context)

    assert "restriction_marker_not_represented:no" in validation["errors"]


def test_blocking_ambiguity_for_fix_without_project() -> None:
    context = build_context_bundle("Arregla el login.")
    contract = build_intent_contract(
        "Arregla el login.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )

    assert contract.status == "needs_clarification"
    assert any(item.classification == "blocking" for item in contract.ambiguities)


def test_non_blocking_ambiguity_does_not_block_analysis() -> None:
    context = build_context_bundle("Revisa el proyecto y comenta preferencias de color.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    contract = build_intent_contract(
        "Revisa el proyecto y comenta preferencias de color.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )

    assert contract.primary_intent == "repository_analysis"
    assert contract.status == "draft"


def test_conflict_between_messages_is_reported() -> None:
    context = build_context_bundle("Toca el módulo de UI.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    from agentic_network.conversation_orchestrator.runtime import DecisionLedgerEntry

    context = replace(
        context,
        decision_ledger=[
            DecisionLedgerEntry(
                id="decision_001",
                timestamp="now",
                source="message_1",
                status="active",
                scope="ui",
                reason="no toques la UI",
                confidence=0.9,
                previous_decision_id=None,
            )
        ],
    )

    conflicts = detect_conflicts("Toca el módulo de UI.", context)

    assert conflicts


def test_pipeline_router_maps_core_intents() -> None:
    context = build_context_bundle("Haz una revisión de seguridad.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    contract = build_intent_contract(
        "Haz una revisión de seguridad.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )
    route = select_pipeline_route(contract)

    assert route.status == "READY"
    assert route.pipeline_id == "security_review"
    assert route.stages == ["security", "reviewer", "final"]


def test_prompt_compiler_keeps_global_constraints_for_all_agents() -> None:
    context = build_context_bundle("Implementa login, pero no toques la base de datos.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    contract = build_intent_contract(
        "Implementa login, pero no toques la base de datos.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )
    route = select_pipeline_route(contract)
    prompts = compile_agent_prompts(contract, context, route)

    assert prompts.prompts
    assert all("GLOBAL CONSTRAINTS" in prompt for prompt in prompts.prompts.values())
    assert all("base de datos" in prompt.lower() for prompt in prompts.prompts.values())
    assert all("UNTRUSTED CONTENT" in prompt for prompt in prompts.prompts.values())


def test_orchestrator_permissions_are_non_privileged(tmp_path: Path) -> None:
    result = run_conversation_orchestrator(
        message="Implementa login sin ejecutar comandos.",
        conversation_id="conversation_001",
        project_context={"project_path": str(tmp_path)},
        run_dir=tmp_path / "outputs" / "run",
    )

    permissions = result.context.permissions
    assert permissions["filesystem_write"] is False
    assert permissions["shell_execution"] is False
    assert permissions["dependency_installation"] is False
    assert permissions["network_access"] is False
    assert permissions["patch_application"] is False


def test_c_drive_blocked_and_d_drive_allowed() -> None:
    c_context = build_context_bundle("Revisa esto.", project_context={"project_path": "C:/Users/ihala/project"})
    c_contract = build_intent_contract("Revisa esto.", conversation_id="conversation_001", request_id="request_test", context=c_context)
    d_context = build_context_bundle("Revisa esto.", project_context={"project_path": "D:/AgenticEngineeringNetwork"})
    d_contract = build_intent_contract("Revisa esto.", conversation_id="conversation_001", request_id="request_test", context=d_context)
    mnt_context = build_context_bundle("Revisa esto.", project_context={"project_path": "/mnt/d/AgenticEngineeringNetwork"})
    mnt_contract = build_intent_contract("Revisa esto.", conversation_id="conversation_001", request_id="request_test", context=mnt_context)

    assert "project_path_c_drive_blocked" in validate_intent_contract(c_contract, c_context)["errors"]
    assert validate_intent_contract(d_contract, d_context)["status"] == "VALID"
    assert validate_intent_contract(mnt_contract, mnt_context)["status"] == "VALID"


def test_context_builder_respects_token_budget() -> None:
    messages = [{"role": "user", "timestamp": f"m{i}", "content": "x " * 200} for i in range(20)]
    bundle = type("Bundle", (), {"messages": messages, "runs": []})()
    context = build_context_bundle("current", conversation_bundle=bundle, token_budget=300)

    assert context.estimated_tokens <= 300
    assert context.excluded_messages > 0


def test_qwen3_4b_registered_only_for_conversation_orchestrator() -> None:
    record = resolve_model_record(CONVERSATION_ORCHESTRATOR_MODEL_ID)
    route = resolve_model_route("conversation_orchestrator", "FAST")
    product_route = resolve_model_route("product", "FAST")

    assert record is not None
    assert route.selected_model == CONVERSATION_ORCHESTRATOR_MODEL_ID
    assert product_route.selected_model != CONVERSATION_ORCHESTRATOR_MODEL_ID


def test_existing_models_remain_policy_blocked() -> None:
    policy = load_model_policy()
    assert validate_model_load_request("qwen3_8b_product_v9_repaired_v2_bullets", "qwen_local", "FAST", policy=policy).allowed is False
    assert validate_model_load_request("deepseek_r1_distill_qwen_14b", "deepseek_unsloth", "POWERFUL", policy=policy).allowed is False


def test_model_missing_is_reported_not_faked_ready() -> None:
    state = inspect_conversation_orchestrator_model()

    assert state["model_id"] == CONVERSATION_ORCHESTRATOR_MODEL_ID
    assert state["status"] in {"MODEL_NOT_FOUND", "BLOCKED_BY_POLICY", "MODEL_READY"}
    if not state["exists"]:
        assert state["status"] == "MODEL_NOT_FOUND"


def test_no_terminal_or_network_for_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("orchestrator must not use network")

    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("orchestrator must not execute terminal")

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(subprocess, "run", fail_run)

    result = run_conversation_orchestrator(
        message="Revisa el proyecto.",
        conversation_id="conversation_001",
        project_context={"project_path": str(tmp_path)},
        run_dir=tmp_path / "outputs" / "run",
    )

    assert result.status == "READY_FOR_EXECUTION"


def test_orchestrator_artifacts_are_written(tmp_path: Path) -> None:
    result = run_conversation_orchestrator(
        message="Haz una revisión de seguridad.",
        conversation_id="conversation_001",
        project_context={"project_path": "D:/AgenticEngineeringNetwork"},
        run_dir=tmp_path / "outputs" / "run",
    )

    assert any(path.endswith("88_intent_contract.json") for path in result.artifacts)
    contract_path = Path(next(path for path in result.artifacts if path.endswith("88_intent_contract.json")))
    assert json.loads(contract_path.read_text(encoding="utf-8"))["primary_intent"] == "security_review"


def test_desktop_chat_uses_intent_contract(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _active_project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    result = submit_chat_task(
        conversation.conversation_id,
        "Implementa login sin tocar la base de datos.",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    assert result.status == "SUCCESS"
    assert any(path.endswith("88_intent_contract.json") for path in result.artifacts)
    summary = json.loads(Path(result.run_dir, "summary.json").read_text(encoding="utf-8"))
    assert summary["intent_contract"]["primary_intent"] == "implement_feature"
    assert "base de datos" in json.dumps(summary["intent_contract"], ensure_ascii=False).lower()


def test_patch_request_waits_for_approval(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _active_project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    result = submit_chat_task(
        conversation.conversation_id,
        "Aplica el patch_001.diff al proyecto.",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
    )

    assert result.status == "WAITING_APPROVAL"
    assert result.current_agent == "conversation_orchestrator"


def test_negated_patch_request_does_not_select_patch_application() -> None:
    context = build_context_bundle(
        "Revisa el proyecto y dime qué falta, sin aplicar parches.",
        project_context={"project_path": "D:/AgenticEngineeringNetwork"},
    )
    contract = build_intent_contract(
        "Revisa el proyecto y dime qué falta, sin aplicar parches.",
        conversation_id="conversation_001",
        request_id="request_test",
        context=context,
    )

    assert contract.primary_intent == "repository_analysis"
    assert any("aplicar" in item.text.lower() for item in contract.forbidden_actions)


def test_runtime_counters_remain_sequential(tmp_path: Path) -> None:
    reset_runtime_state()
    result = run_conversation_orchestrator(
        message="Revisa el proyecto.",
        conversation_id="conversation_001",
        project_context={"project_path": "D:/AgenticEngineeringNetwork"},
        run_dir=tmp_path / "outputs" / "run",
    )
    metrics = get_runtime_metrics()

    assert result.lifecycle["active_models_after"] == 0
    assert metrics["active_models"] <= 1
    assert metrics["parallel_llm_loads"] == 0
