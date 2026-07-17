import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agentic_network.ui_backend import approval_runtime
from agentic_network.ui_backend import runtime


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "runs"
    root.mkdir(parents=True)
    return root


def _run(root: Path, run_id: str = "20260620_120000", *, summary: dict | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if summary is not None:
        _write(run_dir / "summary.json", json.dumps(summary, indent=2))
    return run_dir


def _write_action_plan(run_dir: Path, *, blocked: bool = True, executable: bool = False) -> None:
    _write(
        run_dir / "39_action_plan.json",
        json.dumps(
            {
                "status": "VALID",
                "recommended_next_action": "resolve_parallel_review_blockers",
                "user_message": "Inspect reviewer blockers before approving or applying anything.",
                "blocked": blocked,
                "executable": executable,
                "requires_human": True,
                "requires_terminal": False,
                "requires_approval": False,
                "requires_apply": False,
                "blocking_reasons": ["Parallel Review Gate is BLOCKED."] if blocked else [],
                "planned_steps": [
                    {
                        "order": 1,
                        "description": "Open 37_parallel_review.md.",
                        "subsystem": "Parallel Review Agent",
                        "action_type": "read_only",
                    }
                ],
                "allowed_actions": ["inspect_parallel_review"],
                "blocked_actions": ["apply_patch", "execute_terminal"],
                "prerequisites": ["37_parallel_review.md"],
                "risks": ["Applying while blocked is unsafe."],
                "expected_artifacts": ["updated_38_consensus_decision.md"],
                "responsible_subsystems": ["Parallel Review Agent", "Action Planner"],
            },
            indent=2,
        ),
    )


def test_list_runs_from_temporary_directory(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(
        root,
        summary={
            "task": "Build CRM",
            "patch_quality_decision": "IMPLEMENTATION_READY",
            "patch_apply_status": "SKIPPED",
            "test_runner_status": "PASSED",
            "autonomous_loop_status": "PASSED",
        },
    )

    runs = runtime.list_runs(root)

    assert len(runs) == 1
    assert runs[0]["run_id"] == "20260620_120000"
    assert runs[0]["task"] == "Build CRM"
    assert runs[0]["patch_quality_decision"] == "IMPLEMENTATION_READY"


def test_list_runs_ignores_invalid_entries_and_non_runs(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, "valid_run", summary={"task": "Valid"})
    (root / "not a run").mkdir()
    (root / "empty_run").mkdir()
    _write(root / "file.txt", "ignored")

    runs = runtime.list_runs(root)

    assert [run["run_id"] for run in runs] == ["valid_run"]


def test_get_run_detail_reads_summary_json(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Build LMS", "patch_apply_status": "PASSED"})

    detail = runtime.get_run_detail("20260620_120000", root)

    assert detail["summary"]["task"] == "Build LMS"
    assert detail["statuses"]["patch_apply_status"] == "PASSED"


def test_get_run_detail_returns_available_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Artifacts"})
    _write(run_dir / "01_product_requirements.md", "# Requirements")
    _write(run_dir / "repository_intelligence" / "project_summary.json", "{}")
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    detail = runtime.get_run_detail("20260620_120000", root)

    artifact_names = {artifact["name"] for artifact in detail["artifacts"]}
    patch_names = {patch["name"] for patch in detail["patches"]}
    assert "summary.json" in artifact_names
    assert "01_product_requirements.md" in artifact_names
    assert "repository_intelligence/project_summary.json" in artifact_names
    assert "patch_001.diff" in patch_names


def test_read_artifact_allowed(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Read artifact"})
    _write(run_dir / "25_patch_quality.md", "QUALITY\nIMPLEMENTATION_READY\n")

    content = runtime.read_artifact("20260620_120000", "25_patch_quality.md", root)

    assert "IMPLEMENTATION_READY" in content


def test_read_artifact_blocks_path_traversal(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Traversal"})
    _write(tmp_path / "secret.md", "nope")

    with pytest.raises(HTTPException) as exc:
        runtime.read_artifact("20260620_120000", "../secret.md", root)

    assert exc.value.status_code in {400, 403}


def test_read_patch_allowed(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Patch"})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    content = runtime.read_patch("20260620_120000", "patch_001.diff", root)

    assert "--- a/app.py" in content


def test_read_patch_blocks_path_traversal(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Patch traversal"})

    with pytest.raises(HTTPException) as exc:
        runtime.read_patch("20260620_120000", "../summary.json", root)

    assert exc.value.status_code in {400, 403}


def test_does_not_read_outside_outputs_runs(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Outside"})
    _write(tmp_path / "outside.txt", "outside")

    with pytest.raises(HTTPException):
        runtime.read_artifact("20260620_120000", "../../outside.txt", root)


def test_run_without_summary_does_not_break(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary=None)
    _write(run_dir / "00_context.md", "# Context")

    detail = runtime.get_run_detail("20260620_120000", root)

    assert detail["summary"] == {}
    assert detail["task"] == "Unknown task"
    assert detail["artifacts"][0]["name"] == "00_context.md"


def test_api_model_serialization_is_stable(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(
        root,
        summary={
            "task": "API",
            "autonomous_loop_status": "PASSED",
            "patch_quality_decision": "IMPLEMENTATION_READY",
            "patch_apply_status": "SKIPPED",
            "test_runner_status": "PASSED",
        },
    )
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")
    app = runtime.create_app(runs_root=root)
    client = TestClient(app)

    runs_response = client.get("/api/runs")
    detail_response = client.get("/api/runs/20260620_120000")

    assert runs_response.status_code == 200
    assert set(runs_response.json()["runs"][0]) == {
        "run_id",
        "path",
        "timestamp",
        "task",
        "autonomous_loop_status",
        "patch_quality_decision",
        "patch_apply_status",
        "test_runner_status",
    }
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert {"summary", "artifacts", "patches", "statuses", "warnings", "errors"} <= set(detail)


def test_cli_module_importable() -> None:
    from agentic_network.ui_backend import run

    parser = run.build_parser()
    args = parser.parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_patch_metadata_detects_files_touched(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"patch_quality_decision": "IMPLEMENTATION_READY"})
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- a/app/main.py
+++ b/app/main.py
@@ -1,1 +1,2 @@
 value = 1
+value = 2
""",
    )

    metadata = approval_runtime.get_patch_metadata("20260620_120000", "patch_001.diff", root)

    assert metadata["files_touched"] == ["app/main.py"]
    assert metadata["patch_quality_decision"] == "IMPLEMENTATION_READY"
    assert metadata["can_be_approved_from_ui"] is True


def test_patch_metadata_detects_created_file(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- /dev/null
+++ b/app/new_file.py
@@ -0,0 +1,1 @@
+value = 1
""",
    )

    metadata = approval_runtime.get_patch_metadata("20260620_120000", "patch_001.diff", root)

    assert metadata["creates_files"] is True
    assert metadata["files_touched"] == ["app/new_file.py"]


def test_patch_metadata_blocks_protected_paths(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- a/.git/config
+++ b/.git/config
@@ -1,1 +1,2 @@
 value = 1
+value = 2
""",
    )

    metadata = approval_runtime.get_patch_metadata("20260620_120000", "patch_001.diff", root)

    assert metadata["protected_path_detected"] is True
    assert metadata["can_be_approved_from_ui"] is False


def test_patch_metadata_detects_c_drive(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(
        run_dir / "patches" / "patch_001.diff",
        """--- a/app/main.py
+++ b/app/main.py
@@ -1,1 +1,2 @@
 value = 1
+path = "C:\\Users\\demo\\secret.txt"
""",
    )

    metadata = approval_runtime.get_patch_metadata("20260620_120000", "patch_001.diff", root)

    assert metadata["c_drive_detected"] is True
    assert metadata["can_be_approved_from_ui"] is False


def test_approve_without_token_fails(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    with pytest.raises(HTTPException) as exc:
        approval_runtime.approve_patch(
            "20260620_120000",
            {"patch_name": "patch_001.diff", "confirm_reviewed": True, "confirm_no_apply": True},
            root,
        )

    assert exc.value.status_code == 401


def test_approve_with_wrong_token_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "correct")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    with pytest.raises(HTTPException) as exc:
        approval_runtime.approve_patch(
            "20260620_120000",
            {
                "patch_name": "patch_001.diff",
                "approval_token": "wrong",
                "confirm_reviewed": True,
                "confirm_no_apply": True,
            },
            root,
        )

    assert exc.value.status_code == 403


def test_approve_without_confirm_reviewed_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    with pytest.raises(HTTPException) as exc:
        approval_runtime.approve_patch(
            "20260620_120000",
            {
                "patch_name": "patch_001.diff",
                "approval_token": "token",
                "confirm_no_apply": True,
            },
            root,
        )

    assert exc.value.status_code == 400


def test_get_action_plan_returns_data_when_artifact_exists(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Action plan"})
    _write_action_plan(run_dir)
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.get("/api/runs/20260620_120000/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "VALID"
    assert payload["next_action"] == "resolve_parallel_review_blockers"
    assert payload["blocked"] is True
    assert payload["executable"] is False
    assert payload["requires"]["human"] is True
    assert payload["requires"]["terminal"] is False


def test_missing_action_plan_returns_safe_payload(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Missing plan"})
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.get("/api/runs/20260620_120000/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "MISSING"
    assert payload["next_action"] == "missing_action_plan"
    assert payload["blocked"] is True
    assert payload["executable"] is False
    assert "39_action_plan.json is missing." in payload["blocking_reasons"]


def test_action_plan_path_traversal_is_blocked(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={"task": "Traversal"})
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.get("/api/runs/..%2Fsecret/action-plan")

    assert response.status_code in {404, 403}


def test_action_plan_payload_includes_ui_fields(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Fields"})
    _write_action_plan(run_dir)

    payload = runtime.get_action_plan_detail("20260620_120000", root)

    assert payload["next_action"] == "resolve_parallel_review_blockers"
    assert payload["blocked"] is True
    assert payload["executable"] is False
    assert payload["planned_steps"][0]["description"] == "Open 37_parallel_review.md."
    assert payload["allowed_actions"] == ["inspect_parallel_review"]
    assert payload["blocked_actions"] == ["apply_patch", "execute_terminal"]
    assert payload["responsible_subsystems"] == ["Parallel Review Agent", "Action Planner"]


def test_blocked_action_plan_is_not_executable(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Blocked"})
    _write_action_plan(run_dir, blocked=True, executable=True)

    payload = runtime.get_action_plan_detail("20260620_120000", root)

    assert payload["blocked"] is True
    assert payload["executable"] is False
    assert "apply_patch" in payload["blocked_actions"]


def test_no_action_plan_post_execute_endpoint_exists(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "No post"})
    _write_action_plan(run_dir)
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.post("/api/runs/20260620_120000/action-plan")

    assert response.status_code == 405


def test_action_plan_endpoint_does_not_call_terminal_or_patch_apply(tmp_path: Path, monkeypatch) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Read only"})
    _write_action_plan(run_dir)

    def terminal_explode(*_args, **_kwargs):
        raise AssertionError("Action Plan UI must not call Terminal Agent.")

    def patch_apply_explode(*_args, **_kwargs):
        raise AssertionError("Action Plan UI must not call Patch Apply.")

    monkeypatch.setattr("agentic_network.terminal_agent.runtime.run_terminal_command", terminal_explode)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime.apply_approved_patches", patch_apply_explode)
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.get("/api/runs/20260620_120000/action-plan")

    assert response.status_code == 200


def test_action_plan_endpoint_does_not_mutate_approval_artifacts(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Approval stable"})
    _write_action_plan(run_dir)
    approval = run_dir / "16_human_approval.md"
    _write(approval, "AUTHORIZATION DECISION\nApproved\n")
    before = approval.read_text(encoding="utf-8")
    client = TestClient(runtime.create_app(runs_root=root))

    response = client.get("/api/runs/20260620_120000/action-plan")

    assert response.status_code == 200
    assert approval.read_text(encoding="utf-8") == before


def test_run_detail_embeds_action_plan_view_without_breaking_previous_ui(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "Embedded"})
    _write_action_plan(run_dir)

    detail = runtime.get_run_detail("20260620_120000", root)

    assert "summary" in detail
    assert "artifacts" in detail
    assert "patches" in detail
    assert detail["action_plan_view"]["next_action"] == "resolve_parallel_review_blockers"


def test_approve_without_confirm_no_apply_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    with pytest.raises(HTTPException) as exc:
        approval_runtime.approve_patch(
            "20260620_120000",
            {
                "patch_name": "patch_001.diff",
                "approval_token": "token",
                "confirm_reviewed": True,
            },
            root,
        )

    assert exc.value.status_code == 400


def test_valid_approve_creates_json_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"patch_approval_decision": "Approved"})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    result = approval_runtime.approve_patch(
        "20260620_120000",
        {
            "patch_name": "patch_001.diff",
            "approval_token": "token",
            "confirm_reviewed": True,
            "confirm_no_apply": True,
            "note": "Looks safe",
        },
        root,
    )

    artifact = run_dir / result["artifact"]
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert result["status"] == "APPROVED_FOR_REVIEW"
    assert result["applied"] is False
    assert payload["patch_name"] == "patch_001.diff"
    assert payload["applied"] is False


def test_valid_approve_creates_or_updates_audit_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    approval_runtime.approve_patch(
        "20260620_120000",
        {
            "patch_name": "patch_001.diff",
            "approval_token": "token",
            "confirm_reviewed": True,
            "confirm_no_apply": True,
        },
        root,
    )

    audit = (run_dir / "ui_approval_audit.md").read_text(encoding="utf-8")
    assert "# UI Approval Audit" in audit
    assert "APPROVED_FOR_REVIEW" in audit
    assert "applied=false" in audit


def test_approve_does_not_apply_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")

    approval_runtime.approve_patch(
        "20260620_120000",
        {
            "patch_name": "patch_001.diff",
            "approval_token": "token",
            "confirm_reviewed": True,
            "confirm_no_apply": True,
        },
        root,
    )

    assert not (root.parent.parent / "app.py").exists()
    assert not (run_dir / "13_patch_apply.md").exists()


def test_get_approvals_lists_existing_approvals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")
    approval_runtime.approve_patch(
        "20260620_120000",
        {
            "patch_name": "patch_001.diff",
            "approval_token": "token",
            "confirm_reviewed": True,
            "confirm_no_apply": True,
        },
        root,
    )

    approvals = approval_runtime.list_approvals("20260620_120000", root)

    assert approvals["approvals"][0]["patch_name"] == "patch_001.diff"
    assert approvals["approvals"][0]["applied"] is False


def test_approve_blocks_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    _run(root, summary={})

    with pytest.raises(HTTPException) as exc:
        approval_runtime.approve_patch(
            "20260620_120000",
            {
                "patch_name": "../patch_001.diff",
                "approval_token": "token",
                "confirm_reviewed": True,
                "confirm_no_apply": True,
            },
            root,
        )

    assert exc.value.status_code in {400, 403}


def test_metadata_blocks_path_traversal(tmp_path: Path) -> None:
    root = _runs_root(tmp_path)
    _run(root, summary={})

    with pytest.raises(HTTPException) as exc:
        approval_runtime.get_patch_metadata("20260620_120000", "../patch_001.diff", root)

    assert exc.value.status_code in {400, 403}


def test_approval_api_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANN_UI_APPROVAL_TOKEN", "token")
    root = _runs_root(tmp_path)
    run_dir = _run(root, summary={"task": "API approval"})
    _write(run_dir / "patches" / "patch_001.diff", "--- a/app.py\n+++ b/app.py\n")
    client = TestClient(runtime.create_app(runs_root=root))

    metadata = client.get("/api/runs/20260620_120000/patch/patch_001.diff/metadata")
    approval = client.post(
        "/api/runs/20260620_120000/approve",
        json={
            "patch_name": "patch_001.diff",
            "approval_token": "token",
            "confirm_reviewed": True,
            "confirm_no_apply": True,
        },
    )
    approvals = client.get("/api/runs/20260620_120000/approvals")

    assert metadata.status_code == 200
    assert approval.status_code == 200
    assert approval.json()["applied"] is False
    assert approvals.status_code == 200
    assert approvals.json()["approvals"][0]["patch_name"] == "patch_001.diff"
