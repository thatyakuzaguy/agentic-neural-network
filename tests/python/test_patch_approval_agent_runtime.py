from pathlib import Path

from agentic_network.patch_approval_agent.runtime import (
    PATCH_APPROVAL_OUTPUT_FILE,
    approve_patches,
    parse_patch_approval_sections,
    validate_patch_safety,
)


def _write_run(run_dir: Path, *, decision: str = "Approved", patch_text: str | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "11_execution_plan.md").write_text(
        "EXECUTION SUMMARY\n"
        "- Generate reviewable patch proposals.\n\n"
        "EXECUTION CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "08_final_review.md").write_text(
        "FINAL DECISION\n"
        f"{decision}\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    patches_dir = run_dir / "patches"
    patches_dir.mkdir(exist_ok=True)
    (patches_dir / "patch_001.diff").write_text(
        patch_text
        or "--- old\n+++ new\n@@\n- Existing planning state.\n+ Proposed safe patch note.\n",
        encoding="utf-8",
    )


def test_approved_patch_set(tmp_path: Path) -> None:
    _write_run(tmp_path, decision="Approved")

    result = approve_patches(tmp_path)

    assert result.decision == "Approved"
    assert result.validation_errors == []
    assert result.validation_passed is True
    assert (tmp_path / PATCH_APPROVAL_OUTPUT_FILE).exists()
    parsed = parse_patch_approval_sections(result.approval_output)
    assert parsed["approval_decision"] == "Approved"
    assert parsed["confidence"] == "High"


def test_rejected_patch_set_when_final_not_approved(tmp_path: Path) -> None:
    _write_run(tmp_path, decision="Rejected")

    result = approve_patches(tmp_path)

    assert result.decision == "Rejected"
    assert result.validation_passed is False
    assert "final_decision_not_approved" in result.validation_errors
    assert "APPROVAL DECISION\nRejected" in result.approval_output


def test_dangerous_commands_are_rejected(tmp_path: Path) -> None:
    _write_run(
        tmp_path,
        patch_text="--- old\n+++ new\n@@\n+ sudo rm -rf outputs/history\n+ os.system('pytest')\n",
    )

    result = approve_patches(tmp_path)

    assert result.decision == "Rejected"
    assert "dangerous_command_present" in result.validation_errors


def test_dangerous_paths_are_rejected(tmp_path: Path) -> None:
    _write_run(
        tmp_path,
        patch_text="--- old\n+++ new\n@@\n+ write to /mnt/c/tmp/file\n+ write to C:\\tmp\\file\n",
    )

    result = approve_patches(tmp_path)

    assert result.decision == "Rejected"
    assert "forbidden_c_path_present" in result.validation_errors


def test_repository_protected_paths_are_rejected(tmp_path: Path) -> None:
    errors = validate_patch_safety(
        patch_texts=[
            "--- a/training/datasets/data.jsonl\n"
            "+++ b/training/datasets/data.jsonl\n"
            "@@\n"
            "+ changed dataset\n",
            "--- a/.git/config\n+++ b/.git/config\n@@\n+ changed git config\n",
            "--- a/outputs/runs/old.md\n+++ b/outputs/runs/old.md\n@@\n+ changed output history\n",
        ],
        patch_paths=[tmp_path / "patches" / "patch_001.diff"],
        project_root=Path("/mnt/d/AgenticEngineeringNetwork"),
    )

    assert "protected_path_modified:training/datasets/data.jsonl" in errors
    assert "protected_path_modified:.git/config" in errors
    assert "protected_path_modified:outputs/runs/old.md" in errors


def test_no_model_loading(monkeypatch, tmp_path: Path) -> None:
    _write_run(tmp_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("Patch Approval Agent must not load a model")

    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", explode, raising=False)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", explode, raising=False)

    result = approve_patches(tmp_path)

    assert result.validation_passed is True
