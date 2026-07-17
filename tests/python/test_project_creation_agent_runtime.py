from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.project_creation_agent.run import main as project_creation_main
from agentic_network.project_creation_agent.runtime import ProjectCreationPlan, plan_new_project


def _plan(tmp_path: Path, idea: str = "Create a local CRM for small businesses") -> ProjectCreationPlan:
    return _plan_with_target(tmp_path, idea, "/mnt/d/ANNProjects")


def _plan_with_target(tmp_path: Path, idea: str, target_root: str) -> ProjectCreationPlan:
    artifacts_root = tmp_path / "outputs" / "project_creation"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANN_PROJECT_CREATION_ARTIFACTS_ROOT", str(artifacts_root))
        return plan_new_project(idea=idea, target_root=target_root)


def _read_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_creates_project_creation_brief_md_json(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    brief_md = [path for path in plan.artifacts if path.endswith("40_project_creation_brief.md")]
    brief_json = [path for path in plan.artifacts if path.endswith("40_project_creation_brief.json")]

    assert len(brief_md) == 1
    assert len(brief_json) == 1
    assert Path(brief_md[0]).is_file()
    assert _read_json(brief_json[0])["project_type"] == "crm_saas"


def test_creates_project_structure_plan_md_json(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    structure_md = [path for path in plan.artifacts if path.endswith("41_project_structure_plan.md")]
    structure_json = [path for path in plan.artifacts if path.endswith("41_project_structure_plan.json")]

    assert len(structure_md) == 1
    assert len(structure_json) == 1
    assert "Folders To Create" in Path(structure_md[0]).read_text(encoding="utf-8")
    assert _read_json(structure_json[0])["project_slug"] == plan.project_slug


def test_valid_idea_produces_valid_plan(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert plan.status == "VALID"
    assert plan.project_name
    assert plan.next_action == "review_project_creation_plan"


def test_empty_idea_produces_invalid(tmp_path: Path) -> None:
    plan = _plan(tmp_path, idea="")

    assert plan.status == "INVALID"
    assert "Project idea is required." in plan.validation_errors


def test_target_root_path_traversal_is_blocked(tmp_path: Path) -> None:
    plan = _plan_with_target(tmp_path, "Create a CRM", "/mnt/d/ANNProjects/../Other")

    assert plan.status == "BLOCKED"
    assert any("traversal" in error.lower() for error in plan.validation_errors)


def test_mnt_c_blocked_by_default(tmp_path: Path) -> None:
    plan = _plan_with_target(tmp_path, "Create a CRM", "/mnt/c/Users/example/ANNProjects")

    assert plan.status == "BLOCKED"
    assert any("blocked" in error.lower() for error in plan.validation_errors)


def test_models_path_blocked(tmp_path: Path) -> None:
    plan = _plan_with_target(tmp_path, "Create a CRM", "/mnt/d/AgenticEngineeringNetwork/models")

    assert plan.status == "BLOCKED"
    assert any("protected" in error.lower() for error in plan.validation_errors)


def test_training_path_blocked(tmp_path: Path) -> None:
    plan = _plan_with_target(tmp_path, "Create a CRM", "/mnt/d/AgenticEngineeringNetwork/training")

    assert plan.status == "BLOCKED"
    assert any("protected" in error.lower() for error in plan.validation_errors)


def test_generated_plan_does_not_create_real_project_files(tmp_path: Path) -> None:
    target = tmp_path / "would_be_project"
    plan = _plan_with_target(tmp_path, "Create a CRM", "/mnt/d/ANNProjects")

    assert plan.status == "VALID"
    assert not target.exists()
    assert all("ANNProjects" not in artifact for artifact in plan.artifacts)


def test_plan_includes_folders_to_create(tmp_path: Path) -> None:
    assert "apps/web/src" in _plan(tmp_path).folders_to_create


def test_plan_includes_files_to_create(tmp_path: Path) -> None:
    assert any(item["path"] == "apps/api/app/main.py" for item in _plan(tmp_path).files_to_create)


def test_plan_includes_implementation_phases(tmp_path: Path) -> None:
    phases = _plan(tmp_path).implementation_phases

    assert len(phases) >= 5
    assert phases[0]["name"] == "Requirements"


def test_plan_includes_required_agents(tmp_path: Path) -> None:
    assert "Solution Architect Agent" in _plan(tmp_path).required_agents


def test_plan_includes_safety_constraints(tmp_path: Path) -> None:
    assert "No generated project files are written in v8.2." in _plan(tmp_path).safety_constraints


def test_cli_import_run_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifacts_root = tmp_path / "outputs" / "project_creation"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANN_PROJECT_CREATION_ARTIFACTS_ROOT", str(artifacts_root))
        exit_code = project_creation_main(
            [
                "--idea",
                "Create a local CRM",
                "--target-root",
                "/mnt/d/ANNProjects",
            ]
        )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "VALID"
    assert payload["target_root"].endswith("ANNProjects")
    assert "\\mnt\\d\\" not in payload["target_root"]
    assert len(payload["artifacts"]) == 4


def test_does_not_call_terminal_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Project Creation Agent must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert _plan(tmp_path).status == "VALID"


def test_does_not_call_patch_apply(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert plan.status == "VALID"
    assert not hasattr(plan, "apply_patch")
