from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.desktop_app.main_window import DesktopDataStore
from agentic_network.desktop_app.project_manager import ProjectManager
from agentic_network.desktop_app.workspace_store import WorkspaceStore


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_project_root(tmp_path: Path, name: str = "project") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


def _create_run(project_root: Path, run_id: str = "20260621_091500") -> Path:
    run_dir = project_root / "outputs" / "runs" / run_id
    (run_dir / "patches").mkdir(parents=True)
    _write_json(
        run_dir / "summary.json",
        {"task": "Workspace selector run", "autonomous_loop_status": "PASSED"},
    )
    _write_json(run_dir / "39_action_plan.json", {"recommended_next_action": "inspect_workspace"})
    (run_dir / "patches" / "retry_patch_001.diff").write_text(
        "diff --git a/app.py b/app.py\n+print('workspace')\n",
        encoding="utf-8",
    )
    return run_dir


def _store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(
        tmp_path / "config" / "ann_workspace.json",
        project_manager=ProjectManager(allow_temp_paths=True),
    )


def test_workspace_store_creates_safe_empty_config(tmp_path: Path) -> None:
    config = tmp_path / "config" / "ann_workspace.json"

    store = WorkspaceStore(config, project_manager=ProjectManager(allow_temp_paths=True))

    payload = json.loads(config.read_text(encoding="utf-8"))
    assert store.load_projects() == []
    assert payload == {"version": 1, "projects": []}
    assert "secret" not in config.read_text(encoding="utf-8").lower()


def test_workspace_store_saves_and_loads_projects(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    store = _store(tmp_path)

    project = store.add_project("Local ANN", project_root)
    loaded = store.load_projects()

    assert loaded == [project]
    assert loaded[0].name == "Local ANN"
    assert loaded[0].root_path == str(project_root.resolve())


def test_add_valid_project_from_authorized_temp(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)

    project = _store(tmp_path).add_project("Temp Authorized", project_root)

    assert project.runs_path.endswith(str(Path("outputs") / "runs"))


def test_add_valid_project_from_mnt_d_syntax_warns_without_runs() -> None:
    result = ProjectManager().validate_project_root("/mnt/d/AgenticEngineeringNetwork")

    assert result.valid is True
    assert result.runs_path is not None


def test_rejects_path_traversal(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ValueError, match="Path traversal"):
        store.add_project("Traversal", tmp_path / "safe" / ".." / "other")


def test_rejects_git_directory(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path) / ".git"

    with pytest.raises(ValueError, match="Protected"):
        _store(tmp_path).add_project("Git", project_root)


def test_rejects_training_datasets(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path) / "training" / "datasets"

    with pytest.raises(ValueError, match="Protected"):
        _store(tmp_path).add_project("Datasets", project_root)


def test_rejects_models(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path) / "models"

    with pytest.raises(ValueError, match="Protected"):
        _store(tmp_path).add_project("Models", project_root)


def test_rejects_mnt_c_by_default() -> None:
    result = ProjectManager().validate_project_root("/mnt/c/Users/example/project")

    assert result.valid is False
    assert any("blocked" in error.lower() for error in result.errors)


def test_project_without_outputs_runs_is_warning_not_fatal(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)

    result = ProjectManager(allow_temp_paths=True).validate_project_root(project_root)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == ["Project does not contain outputs/runs yet."]


def test_project_with_outputs_runs_discovers_runs(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    _create_run(project_root)
    manager = ProjectManager(allow_temp_paths=True)
    project = _store(tmp_path).add_project("With Runs", project_root)

    runs = manager.discover_runs(project)

    assert [run.run_id for run in runs] == ["20260621_091500"]
    assert runs[0].has_summary is True
    assert runs[0].has_action_plan is True
    assert runs[0].patch_count == 1


def test_set_active_project_marks_only_one_active(tmp_path: Path) -> None:
    first = _create_project_root(tmp_path, "first")
    second = _create_project_root(tmp_path, "second")
    store = _store(tmp_path)
    first_project = store.add_project("First", first)
    second_project = store.add_project("Second", second)

    active = store.set_active_project(second_project.project_id)
    projects = store.load_projects()

    assert active.project_id == second_project.project_id
    assert [project.project_id for project in projects if project.is_active] == [second_project.project_id]
    assert first_project.project_id != active.project_id


def test_remove_project_eliminates_registration(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    store = _store(tmp_path)
    project = store.add_project("Remove Me", project_root)

    store.remove_project(project.project_id)

    assert store.load_projects() == []


def test_desktop_app_can_load_active_project(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    _create_run(project_root)
    store = _store(tmp_path)
    project = store.add_project("Active", project_root)
    active = store.set_active_project(project.project_id)

    desktop_store = DesktopDataStore(active.runs_path)

    assert desktop_store.load_latest_bundle() is not None


def test_runs_view_uses_active_project(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    _create_run(project_root)
    store = _store(tmp_path)
    project = store.add_project("Runs Project", project_root)
    active = store.set_active_project(project.project_id)

    snapshot = DesktopDataStore(active.runs_path).build_snapshot()

    assert snapshot["runs_root"] == active.runs_path
    assert snapshot["runs"][0]["run_id"] == "20260621_091500"


def test_project_manager_does_not_call_terminal_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _create_project_root(tmp_path)

    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Project Manager must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    _store(tmp_path).add_project("No Terminal", project_root)


def test_project_manager_does_not_call_patch_apply(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    store = _store(tmp_path)

    assert not hasattr(store, "apply_patch")
    assert not hasattr(store, "approve_patch")
    store.add_project("No Patch Apply", project_root)


def test_project_manager_does_not_mutate_approval_artifacts(tmp_path: Path) -> None:
    project_root = _create_project_root(tmp_path)
    approval = project_root / "outputs" / "runs" / "20260621_091500" / "approval.json"
    _write_json(approval, {"token": "do-not-touch", "approved": False})
    before = approval.read_text(encoding="utf-8")

    store = _store(tmp_path)
    project = store.add_project("No Approval Mutation", project_root)
    store.set_active_project(project.project_id)

    assert approval.read_text(encoding="utf-8") == before
