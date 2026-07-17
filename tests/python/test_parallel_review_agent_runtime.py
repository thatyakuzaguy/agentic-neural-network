import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_network.handoff.runtime import build_handoff_bundle
from agentic_network.parallel_review_agent.runtime import run_parallel_review
from agentic_network.ui_backend.runtime import create_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "runs"
    root.mkdir(parents=True)
    return root


def _run(root: Path, run_id: str = "run_001") -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    _write(run_dir / "summary.json", json.dumps({"task": "Build safe feature"}, indent=2))
    _write(run_dir / "00_context.md", "# Context\n")
    _write(run_dir / "01_product_requirements.md", "# Requirements\n")
    _write(run_dir / "02_architecture_plan.md", "# Architecture\nService, API, and tests are aligned.\n")
    _write(run_dir / "03_code.md", "# Code\n")
    _write(run_dir / "04_tests.md", "# Tests\nUnit and integration tests are planned.\n")
    _write(run_dir / "05_security.md", "# Security\nNo dangerous behavior found.\n")
    _write(run_dir / "06_review.md", "# Review\nApproved.\n")
    _write(run_dir / "07_fix_plan.md", "# Fix Plan\nNo fixes required.\n")
    _write(run_dir / "08_final_review.md", "# Final\nApproved.\n")
    _write(run_dir / "10_knowledge_capture.md", "# Knowledge\n")
    _write(run_dir / "11_execution_plan.md", "# Execution\n")
    _write(run_dir / "12_patch_approval.md", "DECISION\nApproved\n")
    _write(run_dir / "13_patch_apply.md", "STATUS\nSKIPPED\n")
    _write(run_dir / "14_test_run.md", "STATUS\nPASSED\n")
    _write(run_dir / "15_merge_readiness.md", "MERGE DECISION\nREADY TO APPLY\n")
    _write(run_dir / "25_patch_quality.md", "QUALITY\nIMPLEMENTATION_READY\n")
    _write(run_dir / "27_autonomous_loop.md", "STATUS\nPASSED\n")
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- a/app/main.py
+++ b/app/main.py
@@ -1,1 +1,2 @@
 value = 1
+value = 2
""",
    )
    return run_dir


def test_creates_parallel_review_markdown(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)

    result = run_parallel_review(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert (run_dir / "37_parallel_review.md").exists()


def test_creates_parallel_review_json(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)

    result = run_parallel_review(run_dir, runs_root=root)

    payload = json.loads((run_dir / "37_parallel_review.json").read_text(encoding="utf-8"))
    assert result.decision == payload["decision"]
    assert payload["status"] == "VALID"


def test_aggregates_required_reviewers(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)

    result = run_parallel_review(run_dir, runs_root=root)

    assert set(result.agent_results) == {
        "architecture_review",
        "security_review",
        "test_review",
        "patch_quality_review",
        "integration_review",
    }


def test_approved_when_all_agents_pass(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)

    result = run_parallel_review(run_dir, runs_root=root)

    assert result.decision == "APPROVED"
    assert result.confidence == "High"
    assert result.blocking_findings == []
    assert result.warnings == []


def test_needs_revision_when_non_blocking_issues_exist(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    (run_dir / "14_test_run.md").unlink()

    result = run_parallel_review(run_dir, runs_root=root)

    assert result.decision == "NEEDS_REVISION"
    assert any("No executed test run" in warning for warning in result.warnings)


def test_blocked_when_protected_path_or_dangerous_finding_appears(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- a/.git/config
+++ b/.git/config
@@ -1,1 +1,2 @@
 value = 1
+value = 2
""",
    )

    result = run_parallel_review(run_dir, runs_root=root)

    assert result.decision == "BLOCKED"
    assert any("Protected path" in finding for finding in result.blocking_findings)


def test_missing_artifact_is_handled_gracefully(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    (run_dir / "05_security.md").unlink()

    result = run_parallel_review(run_dir, runs_root=root)

    assert result.status == "VALID"
    assert result.decision == "NEEDS_REVISION"
    assert any("Security artifact is missing" in warning for warning in result.warnings)


def test_path_traversal_run_dir_is_blocked(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root)

    result = run_parallel_review("../run_001", runs_root=root)

    assert result.status == "INVALID"
    assert result.decision == "BLOCKED"
    assert "run_dir_path_traversal_blocked" in result.validation_errors


def test_does_not_modify_patches(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    patch_path = run_dir / "patches" / "patch_001.diff"
    before = patch_path.read_text(encoding="utf-8")

    run_parallel_review(run_dir, runs_root=root)

    assert patch_path.read_text(encoding="utf-8") == before


def test_does_not_call_patch_apply(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    existing_apply = (run_dir / "13_patch_apply.md").read_text(encoding="utf-8")

    run_parallel_review(run_dir, runs_root=root)

    assert (run_dir / "13_patch_apply.md").read_text(encoding="utf-8") == existing_apply


def test_does_not_call_terminal_agent(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)

    def explode(*args, **kwargs):
        raise AssertionError("Terminal Agent must not be called by Parallel Review.")

    monkeypatch.setattr("subprocess.run", explode)
    result = run_parallel_review(run_dir, runs_root=root)

    assert result.status == "VALID"


def test_handoff_includes_parallel_review_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root)
    run_parallel_review(run_dir, runs_root=root)

    handoff = build_handoff_bundle(run_dir)

    assert "37_parallel_review.md" in handoff.included_artifacts
    assert "37_parallel_review.json" in handoff.included_artifacts
    bundle = (run_dir / "09_handoff_bundle.md").read_text(encoding="utf-8")
    assert "## 37 Parallel Review" in bundle


def test_ui_can_expose_and_open_parallel_review_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, "20260620_120000")
    run_parallel_review(run_dir, runs_root=root)
    client = TestClient(create_app(runs_root=root))

    detail = client.get("/api/runs/20260620_120000")
    artifact = client.get("/api/runs/20260620_120000/artifact/37_parallel_review.md")

    assert detail.status_code == 200
    payload = detail.json()
    artifact_names = {item["name"] for item in payload["artifacts"]}
    assert "37_parallel_review.md" in artifact_names
    assert payload["statuses"]["parallel_review_decision"] == "APPROVED"
    assert artifact.status_code == 200
    assert "ANN Parallel Review" in artifact.text
