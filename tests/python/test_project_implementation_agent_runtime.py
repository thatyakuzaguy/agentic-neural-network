from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.project_implementation_agent.run import main as implementation_main
from agentic_network.project_implementation_agent.runtime import start_project_implementation


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "scaffolded_project"
    (root / "apps" / "api" / "app").mkdir(parents=True)
    (root / "apps" / "web" / "src").mkdir(parents=True)
    (root / "README.md").write_text("# Scaffolded Project\n", encoding="utf-8")
    return root


def _start(tmp_path: Path, objective: str = "Create a local CRM for small businesses"):
    root = _project_root(tmp_path)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS", "1")
        return start_project_implementation(root, objective)


def test_project_implementation_starts_successfully(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert result.status == "PLANNED"
    assert result.objective == "Create a local CRM for small businesses"


def test_creates_implementation_artifacts(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert any(path.endswith("44_project_implementation_plan.md") for path in result.artifacts)
    assert any(path.endswith("44_project_implementation_plan.json") for path in result.artifacts)
    assert all(Path(path).is_file() for path in result.artifacts if not path.endswith("summary.json"))


def test_creates_feature_backlog(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert result.backlog_items
    assert any(path.endswith("45_feature_backlog.json") for path in result.artifacts)


def test_generates_patches(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert result.patches_generated
    assert all(Path(path).name.startswith("patch_") for path in result.patches_generated)
    assert "diff --git" in Path(result.patches_generated[0]).read_text(encoding="utf-8")


def test_consensus_generated(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert result.consensus["consensus_decision"] == "PROCEED_TO_REVIEW"
    assert any(path.endswith("38_consensus_decision.json") for path in result.artifacts)


def test_action_plan_generated(tmp_path: Path) -> None:
    result = _start(tmp_path)

    assert result.next_action == "review_generated_patch_set"
    assert any(path.endswith("39_action_plan.json") for path in result.artifacts)


def test_no_terminal_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project_root(tmp_path)

    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Implementation kickoff must not execute terminal commands.")

    monkeypatch.setenv("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS", "1")
    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert start_project_implementation(root, "Create a CRM").status == "PLANNED"


def test_no_package_installation(tmp_path: Path) -> None:
    result = _start(tmp_path)
    run_root = Path(result.project_root)

    assert not (run_root / "node_modules").exists()
    assert not (run_root / ".venv").exists()
    assert result.consensus["safety"]["package_installation"] is False


def test_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Implementation kickoff must not use network.")

    monkeypatch.setattr("socket.create_connection", fail_network)

    result = _start(tmp_path)

    assert result.consensus["safety"]["network"] is False


def test_no_patch_apply(tmp_path: Path) -> None:
    result = _start(tmp_path)
    project_root = Path(result.project_root)

    assert not (project_root / "docs" / "features").exists()
    assert result.consensus["safety"]["patch_apply"] is False


def test_no_write_outside_project_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside_marker.txt"

    result = _start(tmp_path)

    assert not outside.exists()
    for artifact in result.artifacts:
        assert Path(artifact).resolve().is_relative_to(Path(result.project_root).resolve())
    for patch in result.patches_generated:
        assert Path(patch).resolve().is_relative_to(Path(result.project_root).resolve())


def test_desktop_builder_view_loads() -> None:
    from agentic_network.desktop_app.navigation import navigation_labels
    from agentic_network.desktop_app.views.project_builder_view import PROJECT_BUILDER_MESSAGE

    assert "Project Builder" in navigation_labels()
    assert "patch proposals only" in PROJECT_BUILDER_MESSAGE


def test_blocks_c_drive_by_default(tmp_path: Path) -> None:
    result = start_project_implementation("C:\\ANNProjects\\crm", "Create a CRM")

    assert result.status == "BLOCKED"
    assert any("blocked" in error.lower() for error in result.validation_errors)
    assert result.artifacts == []


def test_blocks_protected_paths() -> None:
    result = start_project_implementation("/mnt/d/AgenticEngineeringNetwork/models/project", "Create a CRM")

    assert result.status == "BLOCKED"
    assert any("protected" in error.lower() for error in result.validation_errors)


def test_cli_run_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project_root(tmp_path)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS", "1")
        exit_code = implementation_main(
            [
                "--project-root",
                str(root),
                "--objective",
                "Create a local CRM for small businesses",
            ]
        )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PLANNED"
    assert payload["patches_generated"]
