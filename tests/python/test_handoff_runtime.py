import json
from pathlib import Path

from agentic_network.handoff.runtime import HANDOFF_OUTPUT_FILE, build_handoff_bundle


ARTIFACT_CONTENT = {
    "00_context.md": "PROJECT CONTEXT\n- Similar authentication-related workflows have been processed previously.",
    "01_product_requirements.md": "REQUIREMENTS\n- Rate limit password reset requests.",
    "02_architecture_plan.md": "TECHNICAL SUMMARY\n- Add a scoped rate-limit plan.",
    "03_code.md": "CODE CHANGES\n- Plan request tracking.",
    "04_tests.md": "TEST SCENARIOS\n- Verify excessive requests are blocked.",
    "05_security.md": "SECURITY FINDINGS\n- Preserve generic reset feedback.",
    "06_review.md": "APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
    "07_fix_plan.md": "READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh",
    "08_final_review.md": "FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh",
    "10_knowledge_capture.md": "LESSONS LEARNED\n- Rate limiting requires balancing usability and abuse prevention.\n\nREUSABLE PATTERNS\n- Rate-limited user actions.\n\nPRODUCT INSIGHTS\n- Recovery flows require clear user messaging.\n\nARCHITECTURE INSIGHTS\n- Centralized policy management improves consistency.\n\nTESTING INSIGHTS\n- Time-based behavior requires deterministic testing.\n\nSECURITY INSIGHTS\n- User enumeration risks should be minimized.\n\nFUTURE REUSE SCORE\nHigh\n\nCONFIDENCE\nHigh",
}


def _write_complete_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "00_user_request.md").write_text(
        "Add rate limits to password reset requests.\n",
        encoding="utf-8",
    )
    for filename, content in ARTIFACT_CONTENT.items():
        (run_dir / filename).write_text(content + "\n", encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "Add rate limits to password reset requests.",
                "stages_run": [
                    "product",
                    "architect",
                    "code",
                    "test",
                    "security",
                    "reviewer",
                    "fixer",
                    "final",
                    "knowledge",
                ],
                "final_decision": "Approved",
                "reviewer_approval_status": "Approved",
                "fixer_ready_for_rereview": "Yes",
                "final_validation_passed": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_handoff_bundle_builds_from_complete_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_complete_run(run_dir)

    result = build_handoff_bundle(run_dir)

    bundle = (run_dir / HANDOFF_OUTPUT_FILE).read_text(encoding="utf-8")
    assert result.validation_errors == []
    assert result.missing_artifacts == []
    assert len(result.included_artifacts) == 10
    assert result.final_decision == "Approved"
    assert "# ANN Handoff Bundle" in bundle
    assert "## 00 Context" in bundle
    assert "## 01 Product Requirements" in bundle
    assert "Rate limit password reset requests" in bundle
    assert "- Final decision: Approved" in bundle
    assert '"final_decision": "Approved"' in bundle


def test_handoff_bundle_handles_missing_artifact_gracefully(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_complete_run(run_dir)
    (run_dir / "04_tests.md").unlink()

    result = build_handoff_bundle(run_dir)

    bundle = (run_dir / HANDOFF_OUTPUT_FILE).read_text(encoding="utf-8")
    assert result.validation_errors == []
    assert "04_tests.md" in result.missing_artifacts
    assert "missing_artifact:04_tests.md" in result.warnings
    assert "_Artifact missing: 04_tests.md_" in bundle
    assert '"missing_artifacts": [' in bundle


def test_handoff_bundle_includes_summary_decisions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_complete_run(run_dir)
    summary_path = run_dir / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["final_decision"] = "Rejected"
    payload["reviewer_approval_status"] = "Needs Fixes"
    payload["fixer_ready_for_rereview"] = "No"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = build_handoff_bundle(run_dir)

    bundle = (run_dir / HANDOFF_OUTPUT_FILE).read_text(encoding="utf-8")
    assert result.final_decision == "Rejected"
    assert result.reviewer_approval_status == "Needs Fixes"
    assert result.fixer_ready_for_rereview == "No"
    assert "- Final decision: Rejected" in bundle
    assert "- Reviewer approval status: Needs Fixes" in bundle
    assert "- Fixer ready for re-review: No" in bundle
