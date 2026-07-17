import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_network.consensus_agent.runtime import (
    DECISION_APPROVED_TO_APPLY,
    DECISION_BLOCKED,
    DECISION_FAILED_PERMANENTLY,
    DECISION_NEEDS_REVISION,
    DECISION_NO_ACTION,
    DECISION_RETRY_RECOMMENDED,
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    run_consensus_decision,
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


def _run(root: Path, run_id: str = "run_001", *, summary: dict | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if summary is not None:
        _write(run_dir / "summary.json", json.dumps(summary, indent=2))
    return run_dir


def _write_parallel(run_dir: Path, decision: str = "APPROVED") -> None:
    _write(
        run_dir / "37_parallel_review.json",
        json.dumps(
            {
                "status": "VALID",
                "decision": decision,
                "confidence": "High",
                "consensus_summary": f"Parallel review decision is {decision}.",
                "validation_errors": [],
            },
            indent=2,
        ),
    )


def _approved_summary(**overrides) -> dict:
    payload = {
        "task": "Build safe feature",
        "patch_quality_decision": "IMPLEMENTATION_READY",
        "patch_quality_score": 95,
        "patch_approval_decision": "Approved",
        "patch_approval_validation_passed": True,
        "patch_apply_status": "SKIPPED",
        "test_runner_status": "PASSED",
        "merge_readiness_decision": "READY TO APPLY",
        "output_files": {},
    }
    payload.update(overrides)
    return payload


def _write_patch_signals(run_dir: Path) -> None:
    _write(run_dir / "12_patch_approval.md", "APPROVAL DECISION\nApproved\n")
    _write(run_dir / "25_patch_quality.md", "QUALITY\nIMPLEMENTATION_READY\n")
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")


def test_creates_consensus_markdown(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir)
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert (run_dir / MARKDOWN_ARTIFACT).exists()


def test_creates_consensus_json(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir)
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)
    payload = json.loads((run_dir / JSON_ARTIFACT).read_text(encoding="utf-8"))

    assert payload["consensus_decision"] == result.consensus_decision
    assert payload["status"] == "VALID"


def test_approved_to_apply_when_all_core_signals_approve(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_APPROVED_TO_APPLY
    assert result.confidence == "High"
    assert result.recommended_next_action == "request_human_approval_then_patch_apply"


def test_blocked_when_parallel_review_gate_blocked(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "BLOCKED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_BLOCKED
    assert any("Parallel Review Gate" in finding for finding in result.blocking_findings)


def test_needs_revision_when_patch_quality_needs_revision(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary(patch_quality_decision="NEEDS_REVISION"))
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NEEDS_REVISION
    assert result.recommended_next_action == "revise_patch_or_enter_retry_loop"


def test_style_only_patch_quality_is_advisory_no_action(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary=_approved_summary(
            patch_quality_decision="LOW_VALUE_COMMENT_ONLY",
            patch_quality_reasons=[
                "Comment-only patch.",
                "No functional behavior added.",
            ],
            patch_approval_decision="Approved",
            test_runner_status="PASSED",
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NO_ACTION
    assert result.recommended_next_action == "wait_for_functional_evidence_or_user_preference"
    assert result.agent_votes["style_disagreement_suppression"] == DECISION_NO_ACTION
    assert any("Style-only disagreement" in reason for reason in result.reasons)
    assert any("did not consume retry attempts" in warning for warning in result.warnings)


def test_style_only_parallel_review_revision_is_suppressed(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write(
        run_dir / "37_parallel_review.json",
        json.dumps(
            {
                "status": "VALID",
                "decision": "NEEDS_REVISION",
                "confidence": "Medium",
                "consensus_summary": "Reviewer prefers a more idiomatic refactor style.",
                "warnings": ["Stylistic naming preference only."],
                "blocking_findings": [],
                "style_only_disagreement": True,
                "validation_errors": [],
            },
            indent=2,
        ),
    )
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NO_ACTION
    assert result.recommended_next_action == "wait_for_functional_evidence_or_user_preference"
    assert result.signals_used["parallel_review_style_only_disagreement"] is True


def test_failed_tests_override_style_only_suppression(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary=_approved_summary(
            patch_quality_decision="LOW_VALUE_COMMENT_ONLY",
            patch_quality_reasons=["Comment-only patch."],
            test_runner_status="FAILED_TESTS",
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NEEDS_REVISION
    assert result.recommended_next_action == "run_self_healing_or_request_revision"
    assert "style_disagreement_suppression" not in result.agent_votes


def test_retry_recommended_when_tests_failed_and_self_healing_has_retry_patch(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary=_approved_summary(
            test_runner_status="FAILED",
            self_healing_status="RETRY_PATCH_GENERATED",
            self_healing_last_patch="19_retry_patch_001.diff",
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_RETRY_RECOMMENDED
    assert result.recommended_next_action == "run_guarded_retry_loop"


def test_bad_test_expectation_blocks_code_retry_even_when_retry_patch_exists(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary=_approved_summary(
            test_runner_status="FAILED_TESTS",
            self_healing_status="RETRY_PATCH_GENERATED",
            self_healing_last_patch="19_retry_patch_001.diff",
            test_validity_status="TEST_EXPECTATION_SUSPECT",
            test_validity_classification="TEST_EXPECTATION_SUSPECT",
            test_validity_reasons=["Assertion expectation conflicts with product contract: float_vs_integer"],
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NEEDS_REVISION
    assert result.recommended_next_action == "challenge_or_repair_test_contract_before_code_fix"
    assert result.agent_votes["test_validity"] == DECISION_NEEDS_REVISION
    assert any("Test Validity Gate" in finding for finding in result.blocking_findings)


def test_architecture_entropy_blocks_more_localized_retry_patches(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    for index in range(1, 5):
        old = root / f"old_{index:03d}"
        _write(
            old / "patches" / "patch_001.diff",
            "diff --git a/app/hotspot.py b/app/hotspot.py\n"
            "--- a/app/hotspot.py\n"
            "+++ b/app/hotspot.py\n"
            "@@ -1,1 +1,2 @@\n"
            " def existing():\n"
            f"+VALUE_{index} = {index}\n",
        )
        _write(old / "summary.json", json.dumps({"output_files": {}}, indent=2))
    run_dir = _run(
        root,
        summary=_approved_summary(
            test_runner_status="FAILED",
            self_healing_status="RETRY_PATCH_GENERATED",
            self_healing_last_patch="19_retry_patch_001.diff",
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)
    _write(
        run_dir / "patches" / "patch_001.diff",
        "diff --git a/app/hotspot.py b/app/hotspot.py\n"
        "--- a/app/hotspot.py\n"
        "+++ b/app/hotspot.py\n"
        "@@ -1,1 +1,4 @@\n"
        " def existing():\n"
        "+if edge_case:\n"
        "+    return handle(edge_case)\n"
        "+elif other:\n"
        "+    return handle(other)\n",
    )

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NEEDS_REVISION
    assert result.recommended_next_action == "run_architecture_refactor_review"
    assert result.agent_votes["architecture_entropy"] == DECISION_NEEDS_REVISION
    assert any("Architecture Entropy Gate" in finding for finding in result.blocking_findings)


def test_failed_permanently_when_autonomous_loop_exhausted(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary(autonomous_loop_status="FAILED_PERMANENTLY"))
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_FAILED_PERMANENTLY
    assert result.recommended_next_action == "escalate_to_human_engineer_with_retry_history"


def test_no_action_when_no_patch_or_active_stage_exists(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Idle", "output_files": {}})

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision == DECISION_NO_ACTION
    assert result.recommended_next_action == "wait_for_new_plan_or_patch"


def test_missing_summary_json_is_invalid_and_blocked_safe(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=None)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.status == "INVALID"
    assert result.consensus_decision == DECISION_BLOCKED
    assert "missing_summary_json" in result.validation_errors
    assert (run_dir / MARKDOWN_ARTIFACT).exists()
    assert (run_dir / JSON_ARTIFACT).exists()


def test_contradictory_signals_are_revision_safe(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary=_approved_summary(
            patch_apply_status="APPLIED",
            test_runner_status="FAILED",
            merge_readiness_decision="READY TO MERGE",
        ),
    )
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.consensus_decision in {DECISION_NEEDS_REVISION, DECISION_BLOCKED}


def test_handoff_includes_consensus_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)
    run_consensus_decision(run_dir, runs_root=root)

    handoff = build_handoff_bundle(run_dir)

    assert MARKDOWN_ARTIFACT in handoff.included_artifacts
    assert JSON_ARTIFACT in handoff.included_artifacts
    assert "## 38 Consensus Decision" in (run_dir / "09_handoff_bundle.md").read_text(encoding="utf-8")


def test_ui_exposes_consensus_status_and_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, "20260620_120000", summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)
    run_consensus_decision(run_dir, runs_root=root)
    client = TestClient(create_app(runs_root=root))

    detail = client.get("/api/runs/20260620_120000")
    artifact = client.get("/api/runs/20260620_120000/artifact/38_consensus_decision.md")

    assert detail.status_code == 200
    payload = detail.json()
    artifact_names = {item["name"] for item in payload["artifacts"]}
    assert MARKDOWN_ARTIFACT in artifact_names
    assert JSON_ARTIFACT in artifact_names
    assert payload["statuses"]["consensus_status"] == "VALID"
    assert payload["statuses"]["consensus_decision"] == DECISION_APPROVED_TO_APPLY
    assert payload["statuses"]["consensus_confidence"] == "High"
    assert artifact.status_code == 200
    assert "ANN Consensus Decision" in artifact.text


def test_consensus_does_not_apply_patches(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)
    patch_path = run_dir / "patches" / "patch_001.diff"
    before = patch_path.read_text(encoding="utf-8")

    run_consensus_decision(run_dir, runs_root=root)

    assert patch_path.read_text(encoding="utf-8") == before


def test_consensus_does_not_call_terminal(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)

    def explode(*args, **kwargs):
        raise AssertionError("Consensus Engine must not call terminal or subprocess.")

    monkeypatch.setattr("subprocess.run", explode)

    result = run_consensus_decision(run_dir, runs_root=root)

    assert result.status == "VALID"


def test_consensus_does_not_mutate_approval_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=_approved_summary())
    _write_parallel(run_dir, "APPROVED")
    _write_patch_signals(run_dir)
    approval = run_dir / "16_human_approval.md"
    _write(approval, "AUTHORIZATION DECISION\nApproved\n")
    before = approval.read_text(encoding="utf-8")

    run_consensus_decision(run_dir, runs_root=root)

    assert approval.read_text(encoding="utf-8") == before


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary=_approved_summary())

    result = run_consensus_decision("../run_001", runs_root=root)

    assert result.status == "INVALID"
    assert result.consensus_decision == DECISION_BLOCKED
    assert "run_dir_path_traversal_blocked" in result.validation_errors
    assert result.artifacts == []
