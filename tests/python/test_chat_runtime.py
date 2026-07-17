from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.desktop_app.chat_runtime import (
    apply_patch_action,
    approve_action,
    create_conversation,
    reject_action,
    retry_action,
    run_tests_action,
    submit_chat_task,
)
from agentic_network.desktop_app.conversation_store import ConversationStore
from agentic_network.desktop_app.project_brain import (
    get_project_history,
    get_recent_approvals,
    get_recent_conversations,
    get_recent_failures,
    get_recent_patches,
    get_recent_retries,
    get_recent_runs,
)
from agentic_network.desktop_app.project_manager import ProjectManager
from agentic_network.desktop_app.views.chat_view import CHAT_VIEW_MESSAGE, chat_runtime_snapshot
from agentic_network.desktop_app.workspace_store import WorkspaceStore


@pytest.fixture()
def stores(tmp_path: Path) -> tuple[ConversationStore, WorkspaceStore]:
    conversation_store = ConversationStore(tmp_path / "outputs" / "conversations")
    workspace_store = WorkspaceStore(
        tmp_path / "config" / "ann_workspace.json",
        project_manager=ProjectManager(allow_temp_paths=True),
    )
    return conversation_store, workspace_store


def _project(tmp_path: Path, workspace_store: WorkspaceStore):
    root = tmp_path / "projects" / "crm"
    root.mkdir(parents=True)
    project = workspace_store.add_project("CRM", root)
    return workspace_store.set_active_project(project.project_id)


def test_chat_creation(stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, _workspace = stores
    conversation = create_conversation(title="CRM", execution_mode="POWERFUL", project_id="project_1", store=store)

    assert conversation.conversation_id == "conversation_001"
    assert conversation.execution_mode == "POWERFUL"
    assert (store.conversation_dir(conversation.conversation_id) / "conversation.json").is_file()


def test_conversation_persistence(stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, _workspace = stores
    conversation = create_conversation(title="CRM", store=store)

    reloaded = ConversationStore(store.root).load_conversation(conversation.conversation_id)

    assert reloaded.conversation.title == "CRM"
    assert reloaded.messages == []


def test_message_append(stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, _workspace = stores
    conversation = create_conversation(store=store)

    store.append_message(conversation.conversation_id, "user", "Create a CRM")
    bundle = store.load_conversation(conversation.conversation_id)

    assert bundle.messages[0]["content"] == "Create a CRM"


def test_attach_run(stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, _workspace = stores
    conversation = create_conversation(store=store)

    store.attach_run(conversation.conversation_id, "chat_001", "SUCCESS", ["artifact.md"])
    bundle = store.load_conversation(conversation.conversation_id)

    assert bundle.runs[0]["run_id"] == "chat_001"
    assert bundle.artifacts == ["artifact.md"]


def test_submit_chat_task(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(title="CRM", project_id=project.project_id, store=store)

    result = submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product", "architect"],
    )

    assert result.status == "SUCCESS"
    assert result.execution_mode == "FAST"
    assert result.current_agent == "architect"
    assert result.current_model == "qwen3_architect_finetuned"
    assert Path(result.run_dir, "summary.json").is_file()


def test_submit_chat_task_powerful(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(title="CRM", project_id=project.project_id, store=store)

    result = submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "POWERFUL",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    assert result.execution_mode == "POWERFUL"
    assert result.current_model == "deepseek_r1_distill_qwen_14b"
    assert result.model_policy == "REAL MODEL LOAD BLOCKED BY POLICY"


def test_load_conversation_after_submit(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )
    bundle = store.load_conversation(conversation.conversation_id)

    assert len(bundle.messages) == 2
    assert bundle.runs[0]["status"] == "SUCCESS"


def test_project_brain(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)
    result = submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    history = get_project_history(project.project_id, workspace_store=workspace, conversation_store=store)

    assert history["project_id"] == project.project_id
    assert get_recent_runs(project.project_id, workspace_store=workspace)
    assert get_recent_conversations(project.project_id, store=store)
    assert get_recent_patches(project.project_id, workspace_store=workspace) == []
    assert get_recent_failures(project.project_id, workspace_store=workspace) == []
    assert get_recent_approvals(project.project_id, workspace_store=workspace)
    assert get_recent_retries(project.project_id, workspace_store=workspace) == []
    assert "approvals" in history
    assert "retries" in history
    assert Path(result.run_dir).is_dir()


def test_buttons_integration(
    tmp_path: Path,
    stores: tuple[ConversationStore, WorkspaceStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_TEST_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_SELF_HEALING_TARGETS", "1")
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)
    submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    approval = approve_action(conversation.conversation_id, store=store)
    reject = reject_action(conversation.conversation_id, store=store)
    tests = run_tests_action(conversation.conversation_id, store=store, workspace_store=workspace)
    patch = apply_patch_action(conversation.conversation_id, store=store, workspace_store=workspace)
    retry = retry_action(conversation.conversation_id, store=store, workspace_store=workspace)

    assert approval.status in {"DENIED", "APPROVED"}
    assert reject.action == "reject"
    assert tests.status == "SKIPPED"
    assert patch.status == "BLOCKED"
    assert retry.status == "BLOCKED"


def test_desktop_chat_loads(stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, _workspace = stores
    create_conversation(title="CRM", store=store)

    snapshot = chat_runtime_snapshot(store)

    assert "ANN Chat" in snapshot
    assert "Conversations: 1" in snapshot
    assert "native PySide6" in CHAT_VIEW_MESSAGE


def test_persistent_state(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, execution_mode="POWERFUL", store=store)

    submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "POWERFUL",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )
    reloaded = ConversationStore(store.root).list_conversations()[0]

    assert reloaded.conversation_id == conversation.conversation_id
    assert reloaded.execution_mode == "POWERFUL"
    assert reloaded.status == "SUCCESS"


def test_artifacts_generation(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    result = submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    assert any(path.endswith("80_chat_session.json") for path in result.artifacts)
    assert any(path.endswith("81_chat_history.md") for path in result.artifacts)
    assert any(path.endswith("82_chat_runtime_trace.md") for path in result.artifacts)
    assert any(path.endswith("83_project_brain_snapshot.json") for path in result.artifacts)
    assert any(path.endswith("84_runtime_bundle_manifest.json") for path in result.artifacts)
    assert any(path.endswith("85_confirmation_trace.json") for path in result.artifacts)
    assert any(path.endswith("86_project_history_snapshot.json") for path in result.artifacts)
    assert any(path.endswith("87_runtime_validation.md") for path in result.artifacts)
    history_path = Path(next(path for path in result.artifacts if path.endswith("81_chat_history.md")))
    assert "Assistant" in history_path.read_text(encoding="utf-8")


def test_no_internet(
    tmp_path: Path,
    stores: tuple[ConversationStore, WorkspaceStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Chat runtime must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    assert submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    ).status == "SUCCESS"


def test_no_terminal_arbitrary(
    tmp_path: Path,
    stores: tuple[ConversationStore, WorkspaceStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Chat submit must not execute arbitrary terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    assert submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    ).status == "SUCCESS"


def test_no_model_adapter_dataset_modification(
    tmp_path: Path,
    stores: tuple[ConversationStore, WorkspaceStore],
) -> None:
    watched = [
        Path("D:/AgenticEngineeringNetwork/models"),
        Path("D:/AgenticEngineeringNetwork/training/adapters"),
        Path("D:/AgenticEngineeringNetwork/training/datasets"),
    ]
    before = [_directory_metadata(path) for path in watched]
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)

    submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    assert [_directory_metadata(path) for path in watched] == before


def test_artifacts_are_valid_json(tmp_path: Path, stores: tuple[ConversationStore, WorkspaceStore]) -> None:
    store, workspace = stores
    project = _project(tmp_path, workspace)
    conversation = create_conversation(project_id=project.project_id, store=store)
    result = submit_chat_task(
        conversation.conversation_id,
        "Create a CRM",
        "FAST",
        project.project_id,
        store=store,
        workspace_store=workspace,
        stages=["product"],
    )

    for suffix in ("80_chat_session.json", "83_project_brain_snapshot.json"):
        path = Path(next(item for item in result.artifacts if item.endswith(suffix)))
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def _directory_metadata(path: Path) -> tuple[bool, int, tuple[str, ...]]:
    if not path.exists():
        return (False, 0, ())
    return (True, path.stat().st_mtime_ns, tuple(sorted(item.name for item in path.iterdir())))
