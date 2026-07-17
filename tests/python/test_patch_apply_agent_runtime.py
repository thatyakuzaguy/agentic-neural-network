import json
from pathlib import Path

import pytest

from agentic_network.patch_apply_agent.runtime import (
    APPLY_STATUS_APPLIED,
    APPLY_STATUS_DRY_RUN_FAILED,
    APPLY_STATUS_DRY_RUN_PASSED,
    APPLY_STATUS_FAILED,
    APPLY_STATUS_REJECTED,
    APPLY_STATUS_SKIPPED,
    PATCH_APPLY_OUTPUT_FILE,
    apply_approved_patches,
)


@pytest.fixture(autouse=True)
def _allow_tmp_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", "/mnt/c,/mnt/d,/mnt/e")
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "")


def _write_summary(
    run_dir: Path,
    *,
    final: str = "Approved",
    approval: str = "Approved",
    validation: bool = True,
    human_decision: str | None = None,
    human_validation: bool | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "final_decision": final,
        "patch_approval_decision": approval,
        "patch_approval_validation_passed": validation,
        "output_files": {},
    }
    if human_decision is not None:
        payload["human_approval_decision"] = human_decision
    if human_validation is not None:
        payload["human_approval_validation_passed"] = human_validation
    (run_dir / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "12_patch_approval.md").write_text(
        "APPROVAL DECISION\nApproved\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )




def _write_human_approval(run_dir: Path, *, decision: str = "Approved") -> None:
    (run_dir / "16_human_approval.md").write_text(
        "HUMAN APPROVAL SUMMARY\n"
        "- Human apply authorization decision recorded.\n\n"
        "AUTHORIZATION DECISION\n"
        f"{decision}\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )


def _write_patch(run_dir: Path, patch_text: str) -> Path:
    patches_dir = run_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patches_dir / "patch_001.diff"
    patch_path.write_text(patch_text, encoding="utf-8")
    return patch_path


def _patch_for(target: str) -> str:
    return (
        f"--- a/{target}\n"
        f"+++ b/{target}\n"
        "@@ -1,2 +1,2 @@\n"
        "-old value\n"
        "+new value\n"
        " unchanged\n"
    )


def test_without_explicit_approval_is_skipped(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir)

    assert result.status == APPLY_STATUS_SKIPPED
    assert "approve_patches_flag_missing" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert (run_dir / PATCH_APPLY_OUTPUT_FILE).exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["patch_apply_status"] == APPLY_STATUS_SKIPPED
    assert summary["patch_apply_approved_flag"] is False


def test_dry_run_passes_without_modifying_files(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_PASSED
    assert result.validation_errors == []
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []
    assert str(target) in result.files_modified
    assert "APPLY STATUS\nDry Run Passed" in result.report


def test_real_apply_without_human_approval_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_not_approved" in result.validation_errors
    assert "human_approval_validation_failed" in result.validation_errors
    assert "human_approval_artifact_missing" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []
    assert not (run_dir / "backups").exists()


def test_rejected_when_prior_patch_approval_is_not_approved(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_summary(run_dir, approval="Rejected")
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_REJECTED
    assert "patch_approval_decision_not_approved" in result.validation_errors


def test_protected_paths_are_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, _patch_for("training/datasets/data.jsonl"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_FAILED
    assert "protected_path_modified:training/datasets/data.jsonl" in result.validation_errors


def test_c_drive_paths_are_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(
        run_dir,
        "--- a/app/safe.txt\n+++ C:\\tmp\\safe.txt\n@@ -1 +1 @@\n-old\n+new\n",
    )
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_FAILED
    assert "forbidden_c_path_present" in result.validation_errors


def test_dangerous_commands_are_rejected_even_if_summary_was_approved(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(
        run_dir,
        "--- a/app/safe.txt\n+++ b/app/safe.txt\n@@ -1 +1 @@\n-old\n+sudo rm -rf outputs/history\n",
    )
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_FAILED
    assert "dangerous_command_present" in result.validation_errors


def test_malformed_patch_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, "this is not a unified diff\n")
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_FAILED
    assert "malformed_patch_no_file_headers" in result.validation_errors


def test_no_model_loading(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    def explode(*_args, **_kwargs):
        raise AssertionError("Patch Apply Agent must not load a model")

    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", explode, raising=False)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", explode, raising=False)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_PASSED



def test_real_apply_with_human_approval_denied_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, human_decision="Denied", human_validation=True)
    _write_human_approval(run_dir, decision="Denied")
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_not_approved" in result.validation_errors
    assert "human_approval_artifact_not_approved" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []


def test_real_apply_with_human_approval_validation_failed_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, human_decision="Approved", human_validation=False)
    _write_human_approval(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_validation_failed" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []


def test_real_apply_with_summary_approved_but_artifact_missing_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, human_decision="Approved", human_validation=True)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_artifact_missing" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []


def test_real_apply_with_artifact_approved_but_summary_denied_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, human_decision="Denied", human_validation=True)
    _write_human_approval(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_not_approved" in result.validation_errors
    assert target.read_text(encoding="utf-8") == "old value\nunchanged\n"
    assert result.backups_created == []


def test_real_apply_with_valid_human_approval_applies_patch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app" / "safe.txt"
    target.parent.mkdir()
    target.write_text("old value\nunchanged\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, human_decision="Approved", human_validation=True)
    _write_human_approval(run_dir)
    _write_patch(run_dir, _patch_for("app/safe.txt"))
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_APPLIED
    assert result.validation_errors == []
    assert target.read_text(encoding="utf-8") == "new value\nunchanged\n"
    assert len(result.backups_created) == 1
    assert Path(result.backups_created[0]).read_text(encoding="utf-8") == "old value\nunchanged\n"


def _write_minimal_approved_apply_run(run_dir: Path) -> None:
    _write_summary(
        run_dir,
        final="Approved",
        approval="Approved",
        validation=True,
        human_decision="Approved",
        human_validation=True,
    )
    (run_dir / "08_final_review.md").write_text(
        "FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    _write_human_approval(run_dir, decision="Approved")


def _sandbox_patch(target: str = "tests/.tmp/patch_apply_sandbox/sandbox_target.py") -> str:
    return (
        f"--- a/{target}\n"
        f"+++ b/{target}\n"
        "@@ -1,1 +1,2 @@\n"
        " VALUE = \"before\"\n"
        "+APPLIED_BY_ANN = True\n"
    )


def test_source_aware_sandbox_apply_creates_backup_and_updates_summary(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    sandbox_dir = repo / "tests" / ".tmp" / "patch_apply_sandbox"
    sandbox_dir.mkdir(parents=True)
    target = sandbox_dir / "sandbox_target.py"
    target.write_text('VALUE = "before"\n', encoding="utf-8")
    sentinel = repo / "tests" / ".tmp" / "patch_apply_sandbox" / "sentinel.py"
    sentinel.write_text('UNCHANGED = True\n', encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_minimal_approved_apply_run(run_dir)
    _write_patch(run_dir, _sandbox_patch())
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_APPLIED
    assert result.validation_errors == []
    assert target.read_text(encoding="utf-8") == 'VALUE = "before"\nAPPLIED_BY_ANN = True\n'
    assert sentinel.read_text(encoding="utf-8") == 'UNCHANGED = True\n'
    assert (run_dir / PATCH_APPLY_OUTPUT_FILE).exists()
    assert len(result.backups_created) == 1
    backup = Path(result.backups_created[0])
    assert run_dir / "backups" in backup.parents
    assert backup.name == "sandbox_target.py"
    assert backup.read_text(encoding="utf-8") == 'VALUE = "before"\n'
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["patch_apply_status"] == APPLY_STATUS_APPLIED
    assert summary["patch_apply_validation_passed"] is True
    assert summary["patch_apply_backups_created"] == result.backups_created
    assert summary["patch_apply_files_modified"] == [str(target)]


def test_source_aware_sandbox_apply_missing_human_approval_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    sandbox_dir = repo / "tests" / ".tmp" / "patch_apply_sandbox"
    sandbox_dir.mkdir(parents=True)
    target = sandbox_dir / "sandbox_target.py"
    target.write_text('VALUE = "before"\n', encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_summary(run_dir, final="Approved", approval="Approved", validation=True)
    (run_dir / "08_final_review.md").write_text(
        "FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    _write_patch(run_dir, _sandbox_patch())
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_REJECTED
    assert "human_approval_not_approved" in result.validation_errors
    assert "human_approval_validation_failed" in result.validation_errors
    assert "human_approval_artifact_missing" in result.validation_errors
    assert target.read_text(encoding="utf-8") == 'VALUE = "before"\n'
    assert result.backups_created == []
    assert not (run_dir / "backups").exists()


def test_source_aware_sandbox_apply_rejects_protected_targets(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    _write_minimal_approved_apply_run(run_dir)
    protected_patches = [
        _sandbox_patch("outputs/runs/sandbox_target.py"),
        _sandbox_patch("knowledge/sandbox_target.py"),
        _sandbox_patch("training/datasets/sandbox_target.py"),
    ]
    patches_dir = run_dir / "patches"
    patches_dir.mkdir(parents=True)
    for index, patch_text in enumerate(protected_patches, start=1):
        (patches_dir / f"patch_{index:03d}.diff").write_text(patch_text, encoding="utf-8")
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_FAILED
    assert any(error.startswith("protected_path_modified:outputs/") for error in result.validation_errors)
    assert any(error.startswith("protected_path_modified:knowledge/") for error in result.validation_errors)
    assert any(error.startswith("protected_path_modified:training/datasets/") for error in result.validation_errors)
    assert result.backups_created == []
    assert not (run_dir / "backups").exists()
