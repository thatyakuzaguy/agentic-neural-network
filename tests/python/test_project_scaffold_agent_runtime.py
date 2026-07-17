from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.project_scaffold_agent.run import main as scaffold_main
from agentic_network.project_scaffold_agent.runtime import (
    apply_project_scaffold,
    preview_project_scaffold,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_plan_dir(
    tmp_path: Path,
    *,
    target_root: Path | str | None = None,
    slug: str = "local-crm",
    folders: list[str] | None = None,
    files: list[dict[str, str]] | None = None,
) -> Path:
    plan_dir = tmp_path / "outputs" / "project_creation" / "20260621_100000_local-crm"
    target = str(target_root or (tmp_path / "scaffold_targets"))
    brief = {
        "status": "VALID",
        "project_name": "Local CRM",
        "project_slug": slug,
        "project_type": "crm_saas",
        "target_root": target,
    }
    structure = {
        **brief,
        "folders_to_create": folders or ["apps/web/src", "apps/api/app", "docs"],
        "files_to_create": files
        or [
            {"path": "README.md", "purpose": "Project guide"},
            {"path": ".env.example", "purpose": "Non-secret environment template"},
            {"path": "apps/api/app/main.py", "purpose": "FastAPI starter"},
            {"path": "apps/web/package.json", "purpose": "Frontend manifest"},
        ],
    }
    _write_json(plan_dir / "40_project_creation_brief.json", brief)
    _write_json(plan_dir / "41_project_structure_plan.json", structure)
    return plan_dir


def _allow_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_SCAFFOLD_TARGETS", "1")


def test_preview_reads_40_41_plan_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    preview = preview_project_scaffold(plan_dir)

    assert preview.project_name == "Local CRM"
    assert preview.project_slug == "local-crm"
    assert preview.status == "VALID"


def test_preview_creates_42_project_scaffold_preview_md_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    preview = preview_project_scaffold(plan_dir)

    assert (plan_dir / "42_project_scaffold_preview.md").is_file()
    assert (plan_dir / "42_project_scaffold_preview.json").is_file()
    assert len(preview.artifacts) == 2


def test_preview_lists_folders_files_to_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    preview = preview_project_scaffold(_create_plan_dir(tmp_path))

    assert "apps/web/src" in preview.folders
    assert any(item["path"] == "README.md" for item in preview.files)
    assert preview.would_create


def test_apply_dry_run_creates_no_project_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, dry_run=True)

    assert result.status == "DRY_RUN"
    assert not Path(result.project_path).exists()
    assert (plan_dir / "43_project_scaffold_apply.json").is_file()


def test_apply_without_token_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, dry_run=False, confirm_create=True)

    assert result.status == "BLOCKED"
    assert any("approval_token" in error for error in result.validation_errors)


def test_apply_without_confirm_create_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(
        plan_dir,
        approval_token="local-test-token",
        dry_run=False,
        confirm_create=False,
    )

    assert result.status == "BLOCKED"
    assert any("confirm_create" in error for error in result.validation_errors)


def test_apply_with_valid_token_and_confirm_creates_project_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(
        plan_dir,
        approval_token="local-test-token",
        dry_run=False,
        confirm_create=True,
    )

    assert result.status == "APPLIED"
    assert Path(result.project_path).is_dir()


def test_apply_creates_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, "local-test-token", True, False)

    assert (Path(result.project_path) / "apps" / "web" / "src").is_dir()


def test_apply_creates_starter_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, "local-test-token", True, False)

    assert (Path(result.project_path) / "README.md").is_file()
    assert (Path(result.project_path) / "apps" / "api" / "app" / "main.py").is_file()


def test_apply_does_not_create_real_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, "local-test-token", True, False)

    assert not (Path(result.project_path) / ".env").exists()
    env_example = (Path(result.project_path) / ".env.example").read_text(encoding="utf-8")
    assert "sk-" not in env_example
    assert "SECRET_KEY=" not in env_example


def test_existing_project_path_is_not_overwritten_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_temp(monkeypatch)
    monkeypatch.setenv("ANN_PROJECT_SCAFFOLD_TOKEN", "local-test-token")
    target_root = tmp_path / "scaffold_targets"
    (target_root / "local-crm").mkdir(parents=True)
    plan_dir = _create_plan_dir(tmp_path, target_root=target_root)

    result = apply_project_scaffold(plan_dir, "local-test-token", True, False)

    assert result.status == "BLOCKED"
    assert any("already exists" in error for error in result.validation_errors)


def test_mnt_c_blocked_by_default(tmp_path: Path) -> None:
    plan_dir = _create_plan_dir(tmp_path, target_root="/mnt/c/ANNProjects")

    preview = preview_project_scaffold(plan_dir)

    assert preview.status == "BLOCKED"
    assert any("blocked" in error.lower() for error in preview.validation_errors)


def test_c_drive_blocked_by_default(tmp_path: Path) -> None:
    plan_dir = _create_plan_dir(tmp_path, target_root="C:\\ANNProjects")

    preview = preview_project_scaffold(plan_dir)

    assert preview.status == "BLOCKED"
    assert any("blocked" in error.lower() for error in preview.validation_errors)


def test_path_traversal_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path, folders=["apps/../escape"])

    preview = preview_project_scaffold(plan_dir)

    assert preview.status in {"BLOCKED", "INVALID"}
    assert preview.blocked_paths == ["apps/../escape"]


def test_git_path_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path, files=[{"path": ".git/config", "purpose": "bad"}])

    preview = preview_project_scaffold(plan_dir)

    assert preview.status == "BLOCKED"
    assert ".git/config" in preview.blocked_paths


def test_models_path_blocked(tmp_path: Path) -> None:
    plan_dir = _create_plan_dir(tmp_path, target_root="/mnt/d/AgenticEngineeringNetwork/models")

    preview = preview_project_scaffold(plan_dir)

    assert preview.status == "BLOCKED"


def test_training_path_blocked(tmp_path: Path) -> None:
    plan_dir = _create_plan_dir(tmp_path, target_root="/mnt/d/AgenticEngineeringNetwork/training")

    preview = preview_project_scaffold(plan_dir)

    assert preview.status == "BLOCKED"


def test_does_not_call_terminal_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)

    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Project Scaffold Agent must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert preview_project_scaffold(_create_plan_dir(tmp_path)).status == "VALID"


def test_does_not_call_patch_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    result = apply_project_scaffold(plan_dir, dry_run=True)

    assert result.status == "DRY_RUN"
    assert not hasattr(result, "apply_patch")


def test_cli_preview_and_dry_run_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _allow_temp(monkeypatch)
    plan_dir = _create_plan_dir(tmp_path)

    preview_exit = scaffold_main([str(plan_dir), "--preview"])
    preview_payload = json.loads(capsys.readouterr().out)
    dry_exit = scaffold_main([str(plan_dir), "--apply", "--dry-run"])
    dry_payload = json.loads(capsys.readouterr().out)

    assert preview_exit == 0
    assert dry_exit == 0
    assert preview_payload["status"] == "VALID"
    assert dry_payload["status"] == "DRY_RUN"
