import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_network.action_planner_agent.runtime import (
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    run_action_plan,
)
from agentic_network.handoff.runtime import build_handoff_bundle
from agentic_network.ui_backend.runtime import create_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "runs"
    root.mkdir(parents=True)
    return root


def _run(root: Path, run_id: str = "run_001", *, consensus: dict | None = None, summary: dict | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if summary is None:
        summary = {
            "task": "Build safe feature",
            "patch_quality_decision": "IMPLEMENTATION_READY",
            "patch_approval_decision": "Approved",
            "patch_approval_validation_passed": True,
            "output_files": {},
        }
    _write(run_dir / "summary.json", json.dumps(summary, indent=2))
    if consensus is not None:
        _write(run_dir / "38_consensus_decision.json", json.dumps(consensus, indent=2))
    return run_dir


def _consensus(decision: str = "BLOCKED", action: str = "resolve_parallel_review_blockers", **overrides) -> dict:
    payload = {
        "status": "VALID",
        "consensus_decision": decision,
        "confidence": "High",
        "reasons": ["Reason."],
        "blocking_findings": ["Parallel Review Gate is BLOCKED."] if decision == "BLOCKED" else [],
        "warnings": [],
        "signals_used": {
            "patch_quality_decision": "IMPLEMENTATION_READY",
            "parallel_review_decision": "APPROVED",
            "patch_approval_decision": "Approved",
        },
        "agent_votes": {},
        "recommended_next_action": action,
    }
    payload.update(overrides)
    return payload


def _write_parallel_review(run_dir: Path, *, blocked: bool = True) -> None:
    _write(
        run_dir / "37_parallel_review.json",
        json.dumps(
            {
                "status": "VALID",
                "decision": "BLOCKED" if blocked else "APPROVED",
                "agent_results": {
                    "integration_review": {"decision": "BLOCKED" if blocked else "APPROVED"}
                },
            },
            indent=2,
        ),
    )
    _write(run_dir / "37_parallel_review.md", "ANN Parallel Review\n")


def test_creates_action_plan_markdown(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus())
    _write_parallel_review(run_dir)

    result = run_action_plan(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert (run_dir / MARKDOWN_ARTIFACT).exists()


def test_creates_action_plan_json(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus())
    _write_parallel_review(run_dir)

    result = run_action_plan(run_dir, runs_root=root)
    payload = json.loads((run_dir / JSON_ARTIFACT).read_text(encoding="utf-8"))

    assert payload["recommended_next_action"] == result.recommended_next_action
    assert payload["status"] == "VALID"


def test_resolve_parallel_review_blockers_creates_non_executable_plan(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus())
    _write_parallel_review(run_dir)

    result = run_action_plan(run_dir, runs_root=root)

    assert result.recommended_next_action == "resolve_parallel_review_blockers"
    assert result.executable is False
    assert result.blocked is True
    assert "apply_patch" in result.blocked_actions
    assert "Parallel Review Agent" in result.responsible_subsystems


def test_run_tests_plan_requires_terminal_but_does_not_execute(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("NEEDS_REVISION", "run_tests"))

    def explode(*args, **kwargs):
        raise AssertionError("Action Planner must not execute terminal commands.")

    monkeypatch.setattr("subprocess.run", explode)
    result = run_action_plan(run_dir, runs_root=root)

    assert result.executable is True
    assert result.requires_terminal is True
    assert "terminal_agent_allowlisted_pytest_after_confirmation" in result.allowed_actions


def test_apply_patch_plan_requires_approval_and_apply_but_does_not_apply(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    summary = {
        "patch_quality_decision": "IMPLEMENTATION_READY",
        "patch_approval_decision": "Approved",
        "patch_approval_validation_passed": True,
        "human_approval_decision": "Approved",
        "human_approval_validation_passed": True,
        "output_files": {},
    }
    run_dir = _run(
        root,
        consensus=_consensus(
            "APPROVED_TO_APPLY",
            "request_human_approval_then_patch_apply",
            signals_used={
                "patch_quality_decision": "IMPLEMENTATION_READY",
                "parallel_review_decision": "APPROVED",
                "patch_approval_decision": "Approved",
            },
        ),
        summary=summary,
    )
    patch = run_dir / "patches" / "patch_001.diff"
    _write(patch, "--- a/app.py\n+++ b/app.py\n")
    before = patch.read_text(encoding="utf-8")

    result = run_action_plan(run_dir, runs_root=root)

    assert result.requires_approval is True
    assert result.requires_apply is True
    assert result.executable is True
    assert patch.read_text(encoding="utf-8") == before


def test_retry_plan_requires_autonomous_loop_and_retry_gates(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("RETRY_RECOMMENDED", "run_guarded_retry_loop"))

    result = run_action_plan(run_dir, runs_root=root)

    assert result.requires_approval is True
    assert result.requires_apply is True
    assert "Autonomous Loop" in result.responsible_subsystems
    assert "--run-tests" in result.prerequisites


def test_test_contract_challenge_plan_blocks_code_rewrite(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        consensus=_consensus(
            "NEEDS_REVISION",
            "challenge_or_repair_test_contract_before_code_fix",
            blocking_findings=["Test Validity Gate classified the failing assertion as TEST_EXPECTATION_SUSPECT."],
        ),
    )

    result = run_action_plan(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert result.blocked is True
    assert result.executable is False
    assert "rewrite_code_under_test" in result.blocked_actions
    assert "Test Validity Gate" in result.responsible_subsystems


def test_architecture_refactor_review_plan_blocks_localized_retry(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        consensus=_consensus(
            "NEEDS_REVISION",
            "run_architecture_refactor_review",
            blocking_findings=["Architecture Entropy Gate reported REFACTOR_RECOMMENDED with score 58."],
        ),
    )

    result = run_action_plan(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert result.blocked is True
    assert result.executable is False
    assert "localized_retry_patch" in result.blocked_actions
    assert "Architecture Entropy Gate" in result.responsible_subsystems


def test_unknown_recommended_next_action_produces_blocked_manual_review_plan(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("NEEDS_REVISION", "teleport_to_prod"))

    result = run_action_plan(run_dir, runs_root=root)

    assert result.status == "INVALID"
    assert result.blocked is True
    assert result.executable is False
    assert "Unsupported recommended_next_action: teleport_to_prod." in result.blocking_reasons


def test_missing_consensus_artifact_is_handled_safely(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=None)

    result = run_action_plan(run_dir, runs_root=root)

    assert result.status == "INVALID"
    assert result.blocked is True
    assert "missing_artifact:38_consensus_decision.json" in result.validation_errors
    assert (run_dir / MARKDOWN_ARTIFACT).exists()
    assert (run_dir / JSON_ARTIFACT).exists()


def test_blocked_consensus_creates_blocked_plan(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("BLOCKED", "manual_review"))

    result = run_action_plan(run_dir, runs_root=root)

    assert result.blocked is True
    assert result.executable is False
    assert "Consensus decision is BLOCKED." in result.blocking_reasons


def test_approved_to_apply_executable_only_when_prerequisites_are_present(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        consensus=_consensus(
            "APPROVED_TO_APPLY",
            "request_human_approval_then_patch_apply",
            signals_used={
                "patch_quality_decision": "IMPLEMENTATION_READY",
                "parallel_review_decision": "APPROVED",
                "patch_approval_decision": "Approved",
            },
        ),
        summary={"patch_quality_decision": "IMPLEMENTATION_READY", "patch_approval_decision": "Approved", "output_files": {}},
    )

    result = run_action_plan(run_dir, runs_root=root)

    assert result.executable is True
    assert result.blocking_reasons == []


def test_does_not_call_patch_apply(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("APPROVED_TO_APPLY", "apply_patch"))

    def explode(*args, **kwargs):
        raise AssertionError("Patch Apply must not be called by Action Planner.")

    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime.apply_approved_patches", explode)
    result = run_action_plan(run_dir, runs_root=root)

    assert result.status in {"VALID", "INVALID"}


def test_does_not_call_terminal_agent(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("NEEDS_REVISION", "run_tests"))

    def explode(*args, **kwargs):
        raise AssertionError("Terminal Agent must not be called by Action Planner.")

    monkeypatch.setattr("agentic_network.terminal_agent.runtime.run_terminal_command", explode)
    result = run_action_plan(run_dir, runs_root=root)

    assert result.requires_terminal is True


def test_does_not_mutate_approval_artifacts_or_tokens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "secret-token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus("APPROVED_TO_APPLY", "apply_patch"))
    approval = run_dir / "16_human_approval.md"
    _write(approval, "AUTHORIZATION DECISION\nApproved\n")
    before = approval.read_text(encoding="utf-8")

    run_action_plan(run_dir, runs_root=root)

    assert approval.read_text(encoding="utf-8") == before


def test_handoff_includes_action_plan_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, consensus=_consensus())
    _write_parallel_review(run_dir)
    run_action_plan(run_dir, runs_root=root)

    handoff = build_handoff_bundle(run_dir)

    assert MARKDOWN_ARTIFACT in handoff.included_artifacts
    assert JSON_ARTIFACT in handoff.included_artifacts
    assert "## 39 Action Plan" in (run_dir / "09_handoff_bundle.md").read_text(encoding="utf-8")


def test_ui_exposes_action_plan_status_if_artifacts_exist(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, "20260620_120000", consensus=_consensus())
    _write_parallel_review(run_dir)
    run_action_plan(run_dir, runs_root=root)
    client = TestClient(create_app(runs_root=root))

    detail = client.get("/api/runs/20260620_120000")
    artifact = client.get("/api/runs/20260620_120000/artifact/39_action_plan.md")

    assert detail.status_code == 200
    payload = detail.json()
    artifact_names = {item["name"] for item in payload["artifacts"]}
    assert MARKDOWN_ARTIFACT in artifact_names
    assert JSON_ARTIFACT in artifact_names
    assert payload["statuses"]["action_plan_status"] == "VALID"
    assert payload["statuses"]["action_plan_next_action"] == "resolve_parallel_review_blockers"
    assert payload["statuses"]["action_plan_blocked"] == "True"
    assert artifact.status_code == 200
    assert "ANN Action Plan" in artifact.text


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, consensus=_consensus())

    result = run_action_plan("../run_001", runs_root=root)

    assert result.status == "INVALID"
    assert result.blocked is True
    assert "run_dir_path_traversal_blocked" in result.validation_errors
    assert result.artifacts == []
