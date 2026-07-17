import json
import shutil
from pathlib import Path

import pytest

from agentic_network.config import PipelineConfig
from agentic_network.execution_agent.runtime import (
    ExecutionPlanResult,
    parse_execution_plan_sections,
)
from agentic_network.pipeline.runner import PipelineRunner


APPROVAL_TOKEN = "I_APPROVE_PATCH_APPLICATION"
SANDBOX_RELATIVE_TARGET = "tests/.tmp/e2e_patch_apply_sandbox/sandbox_target.py"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sandbox_root() -> Path:
    return _project_root() / "tests" / ".tmp" / "e2e_patch_apply_sandbox"


@pytest.fixture()
def e2e_sandbox() -> tuple[Path, Path]:
    root = _sandbox_root()
    expected_parent = _project_root() / "tests" / ".tmp"
    if expected_parent.resolve() not in root.resolve().parents:
        raise AssertionError(f"Refusing to clean unexpected sandbox path: {root}")
    shutil.rmtree(root, ignore_errors=True)
    target = _project_root() / SANDBOX_RELATIVE_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('VALUE = "before"\n', encoding="utf-8")
    try:
        yield root, target
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _config(output_root: Path) -> PipelineConfig:
    return PipelineConfig(
        deepseek_gguf_path=None,
        qwen_base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        qwen_adapter_path=Path("training/adapters/qwen-7b-python-expert-v5"),
        output_dir=output_root / "runs",
        max_new_tokens=128,
        temperature=0.2,
        top_p=0.85,
        context_length=2048,
        use_4bit=True,
        stage_isolation="inprocess",
    )


def _sandbox_patch() -> str:
    return (
        f"--- a/{SANDBOX_RELATIVE_TARGET}\n"
        f"+++ b/{SANDBOX_RELATIVE_TARGET}\n"
        "@@ -1,1 +1,2 @@\n"
        ' VALUE = "before"\n'
        "+APPLIED_BY_ANN = True\n"
    )


def _sandbox_execution_plan() -> str:
    return f"""EXECUTION SUMMARY
- Generate a reviewable sandbox patch for the approved mock run.

FILES TO MODIFY
- {SANDBOX_RELATIVE_TARGET}

FILES TO CREATE
- None

FILES TO REVIEW
- {SANDBOX_RELATIVE_TARGET}

PATCH STRATEGY
- Apply one source-aware unified diff to the disposable sandbox fixture.

EXPECTED TEST IMPACT
- Test Runner remains skipped unless explicitly enabled.

SECURITY CONSIDERATIONS
- Patch target is limited to the disposable tests/.tmp sandbox path.

EXECUTION CONFIDENCE
High"""


def _sandbox_execution_stage_factory():
    def fake_execution_stage(*, artifacts, stage_timings):
        plan = _sandbox_execution_plan()
        artifact_path = Path(artifacts.root) / "11_execution_plan.md"
        patches_dir = Path(artifacts.root) / "patches"
        patch_path = patches_dir / "patch_001.diff"
        patches_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(plan.rstrip() + "\n", encoding="utf-8")
        patch_path.write_text(_sandbox_patch(), encoding="utf-8")
        stage_timings.append(
            {
                "stage": "execution",
                "stage_name": "Execution Agent",
                "model_backend": "none",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:00Z",
                "duration_seconds": 0.0,
                "input_char_count": 1,
                "output_char_count": len(plan),
                "gpu_config": {},
                "device_info": {},
                "static_sanity_ran": True,
                "fixer_ran": True,
                "post_fix_sanity_ran": True,
            }
        )
        return ExecutionPlanResult(
            run_dir=str(artifacts.root),
            final_decision="Approved",
            execution_plan=plan,
            parsed_sections=parse_execution_plan_sections(plan),
            warnings=[],
            validation_errors=[],
            artifact_path=str(artifact_path),
            patch_paths=[str(patch_path)],
            refused=False,
            source_aware=True,
            applicable_patch_count=1,
            no_target_reason="",
            candidate_files=[SANDBOX_RELATIVE_TARGET],
        )

    return fake_execution_stage


def _apply_stages() -> list[str]:
    return [
        "context",
        "product",
        "architect",
        "code",
        "test",
        "security",
        "reviewer",
        "fixer",
        "revision",
        "final",
        "execution",
        "patch_approval",
        "patch_apply",
        "test_runner",
        "merge_readiness",
        "human_approval",
        "knowledge",
        "handoff",
    ]


def test_e2e_mock_pipeline_applies_sandbox_patch_after_human_approval(
    e2e_sandbox: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_root, target = e2e_sandbox
    sentinel = sandbox_root / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    monkeypatch.setattr(
        "agentic_network.pipeline.runner._run_execution_stage",
        _sandbox_execution_stage_factory(),
    )
    runner = PipelineRunner(_config(sandbox_root), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=_apply_stages(),
        apply_requested=True,
        approve_patches=True,
        approval_token=APPROVAL_TOKEN,
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    target_text = target.read_text(encoding="utf-8")
    backup_path = output_dir / "backups" / SANDBOX_RELATIVE_TARGET
    handoff = (output_dir / "09_handoff_bundle.md").read_text(encoding="utf-8")

    assert result.stages_run.index("human_approval") < result.stages_run.index("patch_apply")
    assert summary["apply_requested"] is True
    assert summary["apply_orchestration_valid"] is True
    assert summary["human_approval_decision"] == "Approved"
    assert summary["human_approval_validation_passed"] is True
    assert summary["patch_apply_status"] == "APPLIED"
    assert summary["patch_apply_validation_passed"] is True
    assert str(target) in summary["patch_apply_files_modified"]
    assert str(backup_path) in summary["patch_apply_backups_created"]
    assert summary["merge_readiness_decision"] == "READY TO APPLY"
    assert 'APPLIED_BY_ANN = True' in target_text
    assert backup_path.read_text(encoding="utf-8") == 'VALUE = "before"\n'
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert "/mnt/c" not in json.dumps(summary).lower()
    assert "C:\\" not in json.dumps(summary)
    assert "13_patch_apply.md" in summary["handoff_included_artifacts"]
    assert "15_merge_readiness.md" in summary["handoff_included_artifacts"]
    assert "16_human_approval.md" in summary["handoff_included_artifacts"]
    assert "## 13 Patch Apply" in handoff
    assert "## 15 Merge Readiness" in handoff
    assert "## 16 Human Approval" in handoff


def test_e2e_mock_pipeline_apply_without_token_fails_before_patch_apply(
    e2e_sandbox: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_root, target = e2e_sandbox
    monkeypatch.setattr(
        "agentic_network.pipeline.runner._run_execution_stage",
        _sandbox_execution_stage_factory(),
    )
    runner = PipelineRunner(_config(sandbox_root), mock=True, mock_changes_required=False)

    with pytest.raises(ValueError, match="approval_token_missing"):
        runner.run(
            "Add rate limits to password reset requests.",
            stages=_apply_stages(),
            apply_requested=True,
            approve_patches=True,
        )

    run_dirs = sorted((sandbox_root / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert target.read_text(encoding="utf-8") == 'VALUE = "before"\n'
    assert not (run_dir / "13_patch_apply.md").exists()
    assert not (run_dir / "backups").exists()
    assert summary["apply_requested"] is True
    assert summary["approve_patches_flag"] is True
    assert summary["approval_token_provided"] is False
    assert summary["apply_orchestration_valid"] is False
    assert "approval_token_missing" in summary["apply_orchestration_errors"]
    assert summary["stages_run"] == []
