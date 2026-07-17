from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from agentic_network.desktop_app.main_window import (
    DesktopDataStore,
    DesktopSecurityError,
    PYSIDE6_AVAILABLE,
    create_main_window,
)
from agentic_network.desktop_app.navigation import navigation_labels, primary_navigation_labels
from agentic_network.desktop_app.project_manager import ProjectManager
from agentic_network.desktop_app.views.chat_view import CHAT_VIEW_MESSAGE, chat_runtime_snapshot
from agentic_network.desktop_app.views.dashboard_view import DASHBOARD_MESSAGE, dashboard_snapshot
from agentic_network.desktop_app.views.final_release_view import (
    FINAL_RELEASE_MESSAGE,
    final_release_snapshot,
)
from agentic_network.desktop_app.views.engineering_pipeline_view import (
    ENGINEERING_PIPELINE_MESSAGE,
    engineering_pipeline_snapshot,
)
from agentic_network.desktop_app.views.terminal_view import SAFE_TERMINAL_MESSAGE
from agentic_network.desktop_app.workspace_store import WorkspaceStore


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_run(root: Path, run_id: str = "20260621_080000") -> Path:
    run_dir = root / run_id
    patches = run_dir / "patches"
    patches.mkdir(parents=True)
    _write_json(
        run_dir / "summary.json",
        {
            "task": "Build a local ANN desktop foundation",
            "timestamp": "2026-06-21T08:00:00Z",
            "autonomous_loop_status": "PASSED",
        },
    )
    _write_json(
        run_dir / "37_parallel_review.json",
        {"status": "PASSED", "decision": "APPROVE_WITH_NOTES", "confidence": "High"},
    )
    _write_json(
        run_dir / "38_consensus_decision.json",
        {"status": "PASSED", "consensus_decision": "PROCEED", "confidence": "High"},
    )
    _write_json(
        run_dir / "39_action_plan.json",
        {
            "status": "VALID",
            "recommended_next_action": "inspect_desktop_foundation",
            "blocked": False,
            "executable": False,
            "planned_steps": [{"order": 1, "description": "Open the desktop dashboard"}],
        },
    )
    (patches / "retry_patch_001.diff").write_text(
        "diff --git a/example.py b/example.py\n+print('desktop')\n",
        encoding="utf-8",
    )
    return run_dir


def test_desktop_app_runtime_starts_without_qt_window(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    snapshot = DesktopDataStore(root).build_snapshot()

    assert snapshot["dashboard_visible"] is True
    assert snapshot["security"]["local_only"] is True
    assert snapshot["security"]["cloud"] is False


def test_sidebar_visible() -> None:
    assert primary_navigation_labels() == [
        "Dashboard",
        "Projects",
        "Engineering Pipeline",
        "Model Manager",
        "Knowledge",
        "Runtime",
        "Artifacts",
        "Logs",
        "Settings",
    ]
    assert navigation_labels() == [
        "Dashboard",
        "Engineering Pipeline",
        "First Run",
        "Chat",
        "Projects",
        "Project Creation",
        "Project Scaffold",
        "Project Builder",
        "End-to-End Builder",
        "Project Patch Review",
        "Project Verification",
        "Project Test Generation",
        "Project Self Healing",
        "Runs",
        "Consensus",
        "Parallel Review",
        "Next Step",
        "Patches",
        "Terminal",
        "Approvals",
        "Skills",
        "Skill Permissions",
        "Skill Audit",
        "Skill Runtime",
        "Skill Evidence",
        "Model Routing",
        "Model Inventory",
        "Runtime Engine",
        "Final Release",
    ]


def test_views_load_expected_ids(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    snapshot = DesktopDataStore(root).build_snapshot()

    assert snapshot["views"] == [
        "dashboard",
        "engineering_pipeline",
        "first_run",
        "chat",
        "projects",
        "project_creation",
        "project_scaffold",
        "project_builder",
        "project_builder_orchestrator",
        "project_patch_review",
        "project_verification",
        "project_test_generation",
        "project_self_healing",
        "runs",
        "consensus",
        "parallel_review",
        "action_plan",
        "patches",
        "terminal",
        "approvals",
        "skills",
        "skill_permissions",
        "skill_audit",
        "skill_runtime",
        "skill_evidence",
        "model_routing",
        "model_inventory",
        "runtime_engine",
        "final_release",
    ]


def test_dashboard_visible(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    snapshot = DesktopDataStore(root).build_snapshot()

    assert snapshot["latest_run_id"] == "20260621_080000"
    assert snapshot["latest"]["summary"]["task"] == "Build a local ANN desktop foundation"
    dashboard = dashboard_snapshot(snapshot)
    assert "Enterprise AI Engineering UI" in DASHBOARD_MESSAGE
    assert dashboard["brand"] == "ANN"
    assert dashboard["product"] == "Agentic Neural Network"
    assert dashboard["pipeline"]["runtime_monitor"]["vram_policy"] == "SEQUENTIAL"


def test_engineering_pipeline_ui_snapshot_is_functional(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    snapshot = DesktopDataStore(root).build_snapshot()
    pipeline = engineering_pipeline_snapshot(snapshot)

    assert "Engineering Pipeline" in navigation_labels()
    assert "Enterprise Cyberpunk" in ENGINEERING_PIPELINE_MESSAGE
    assert "does not execute terminal commands" in ENGINEERING_PIPELINE_MESSAGE
    assert pipeline["pipeline_status"] == "APPROVED_OUTPUT_READY"
    assert pipeline["progress"] == 100
    assert pipeline["runtime_monitor"]["vram_policy"] == "SEQUENTIAL"
    assert pipeline["runtime_monitor"]["parallel_llm_loads"] == 0
    assert pipeline["terminal"]["safe"] is True
    assert pipeline["terminal"]["auto_execute"] is False
    assert "Product Agent" in [stage["title"] for stage in pipeline["stages"]]
    assert "Fine-tuned Qwen2.5" in [stage["model"] for stage in pipeline["stages"]]


def test_action_plan_visible(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    bundle = DesktopDataStore(root).load_latest_bundle()

    assert bundle is not None
    assert bundle.action_plan["recommended_next_action"] == "inspect_desktop_foundation"


def test_consensus_visible(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    bundle = DesktopDataStore(root).load_latest_bundle()

    assert bundle is not None
    assert bundle.consensus["consensus_decision"] == "PROCEED"


def test_parallel_review_visible(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    bundle = DesktopDataStore(root).load_latest_bundle()

    assert bundle is not None
    assert bundle.parallel_review["decision"] == "APPROVE_WITH_NOTES"


def test_patch_viewer_visible(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    bundle = DesktopDataStore(root).load_latest_bundle()

    assert bundle is not None
    assert bundle.patches[0].name == "retry_patch_001.diff"
    assert "diff --git" in bundle.patches[0].content


def test_terminal_view_no_execution() -> None:
    assert "No command is executed" in SAFE_TERMINAL_MESSAGE
    assert not hasattr(DesktopDataStore, "run_terminal_command")
    assert not hasattr(DesktopDataStore, "execute")


def test_project_test_generation_view_is_read_only() -> None:
    from agentic_network.desktop_app.views.project_test_generation_view import (
        PROJECT_TEST_GENERATION_MESSAGE,
    )

    assert "Project Test Generation" in navigation_labels()
    assert "does not execute terminal commands" in PROJECT_TEST_GENERATION_MESSAGE
    assert "Generated test patches" in PROJECT_TEST_GENERATION_MESSAGE


def test_skills_view_is_read_only() -> None:
    from agentic_network.desktop_app.views.skills_view import SKILLS_VIEW_MESSAGE, skills_snapshot

    assert "Skills" in navigation_labels()
    assert "does not execute skills" in SKILLS_VIEW_MESSAGE
    assert "internet_search" in skills_snapshot()


def test_skill_permission_and_audit_views_load() -> None:
    from agentic_network.desktop_app.views.skill_audit_view import SKILL_AUDIT_MESSAGE
    from agentic_network.desktop_app.views.first_run_view import FIRST_RUN_MESSAGE, first_run_snapshot
    from agentic_network.desktop_app.views.skill_evidence_view import SKILL_EVIDENCE_MESSAGE
    from agentic_network.desktop_app.views.skill_permission_view import (
        SKILL_PERMISSION_MESSAGE,
        permission_snapshot,
    )
    from agentic_network.desktop_app.views.skill_runtime_view import SKILL_RUNTIME_MESSAGE
    from agentic_network.desktop_app.views.model_routing_view import (
        MODEL_ROUTING_MESSAGE,
        model_routing_snapshot,
    )
    from agentic_network.desktop_app.views.model_inventory_view import (
        MODEL_INVENTORY_MESSAGE,
        model_inventory_snapshot,
    )
    from agentic_network.desktop_app.views.runtime_engine_view import (
        RUNTIME_ENGINE_MESSAGE,
        runtime_engine_snapshot,
    )

    assert "Skill Permissions" in navigation_labels()
    assert "First Run" in navigation_labels()
    assert "Chat" in navigation_labels()
    assert "Skill Audit" in navigation_labels()
    assert "Skill Runtime" in navigation_labels()
    assert "Skill Evidence" in navigation_labels()
    assert "Model Routing" in navigation_labels()
    assert "Model Inventory" in navigation_labels()
    assert "Runtime Engine" in navigation_labels()
    assert "Final Release" in navigation_labels()
    assert "does not execute skills" in SKILL_PERMISSION_MESSAGE
    assert "does not execute skills" in SKILL_AUDIT_MESSAGE
    assert "does not execute automatically" in SKILL_RUNTIME_MESSAGE
    assert "read-only advisory" in SKILL_EVIDENCE_MESSAGE
    assert "does not download models" in MODEL_ROUTING_MESSAGE
    assert "Default mode" in model_routing_snapshot()
    assert "does not load models" in MODEL_INVENTORY_MESSAGE
    assert "deepseek_r1_distill_qwen_14b" in model_inventory_snapshot()
    assert "does not download models" in RUNTIME_ENGINE_MESSAGE
    assert "VRAM Policy" in runtime_engine_snapshot()
    assert "does not sign binaries" in FINAL_RELEASE_MESSAGE
    assert "native PySide6" in CHAT_VIEW_MESSAGE
    assert "ANN Chat" in chat_runtime_snapshot()
    assert "does not install dependencies" in FIRST_RUN_MESSAGE
    assert "First Run / System Check" in first_run_snapshot()
    assert "github" in permission_snapshot()


def test_final_release_view_renders_aggregate_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agentic_network.desktop_app.views.final_release_view.build_cli_final_release_report",
        lambda **_kwargs: {
            "status": "FINAL_RELEASE_BLOCKED",
            "exit_code": 2,
            "runtime_materialization": "READY",
            "wheelhouse_integrity": "HASH_VERIFIED",
            "embedded_package_audit": "PACKAGE_AUDIT_READY",
            "installer_rc": "RC_READY",
            "installer_final": "INSTALLER_FINAL_BLOCKED",
            "final_release_bridge": "FINAL_RELEASE_BLOCKED",
            "public_release": "FINAL_RELEASE_BLOCKED",
            "ann_finalization": "FINAL_RELEASE_BLOCKED",
            "local_install_smoke_passed": True,
            "external_clean_machine_passed": False,
            "signed_installer": False,
            "code_signing_status": "SIGNING_BLOCKED_UNSIGNED",
            "blockers": [{"id": "signed_installer"}],
            "next_step": "sign installer",
            "no_internet": True,
            "no_downloads": True,
            "no_installs": True,
            "no_model_load": True,
            "no_inference": True,
            "no_training": True,
            "no_external_signing": True,
            "no_external_install": True,
            "external_release_evidence_blockers": [
                {"id": "signed_installer"},
                {"id": "external_clean_machine"},
            ],
            "release_operator_environment_blockers": [
                {"id": "signtool_available"},
                {"id": "certificate_thumbprint_provided"},
            ],
            "final_release_path_contract_ready": True,
            "final_release_path_contract": [
                {
                    "id": "installer_root",
                    "passed": True,
                    "expected": "installer",
                    "actual": "installer",
                },
                {
                    "id": "bundle_root",
                    "passed": True,
                    "expected": "outputs/release_candidates/ANN_RC_HANDOFF",
                    "actual": "outputs/release_candidates/ANN_RC_HANDOFF",
                },
                {
                    "id": "signing_evidence",
                    "passed": True,
                    "expected": "installer/release_signing_evidence.json",
                    "actual": "installer/release_signing_evidence.json",
                },
                {
                    "id": "clean_machine_marker",
                    "passed": True,
                    "expected": "D:/ANN/clean_machine_external_validation.json",
                    "actual": "D:/ANN/clean_machine_external_validation.json",
                },
            ],
            "release_signing_plan_status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "release_signing_plan_safety_ready": True,
            "release_signing_commands": [
                "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                '-CertificateThumbprint "<CERT_THUMBPRINT>"'
            ],
            "release_operator_environment_command": (
                "PYTHONPATH=. python scripts/runtime/verify_release_operator_environment.py "
                '--installer-root installer --certificate-thumbprint "<CERT_THUMBPRINT>" '
                "--output-dir outputs/runtime_finalization_20260707"
            ),
            "external_release_evidence_safety_ready": True,
            "release_operator_environment_safety_ready": True,
            "release_evidence_contract_ready": False,
            "release_operator_signing_thumbprint_match": False,
            "external_release_evidence_report": {
                "status": "EXTERNAL_RELEASE_EVIDENCE_BLOCKED",
                "installer_hashes_match_handoff": True,
                "installer_hashes_match_clean_machine": False,
                "release_signing_evidence_valid": False,
                "clean_machine_signing_evidence_hash_match": False,
                "clean_machine_transfer_manifest_hash_match": False,
                "bundle": {"status": "HANDOFF_VERIFIED"},
                "signing": {
                    "status": "SIGNING_BLOCKED_UNSIGNED",
                    "signed_installer": False,
                    "untimestamped_binaries": ["ANN_Setup.exe"],
                },
                "clean_machine": {"status": "LOCAL_INSTALL_SMOKE_PASSED"},
                "blockers": [{"id": "signed_installer"}, {"id": "external_clean_machine"}],
                "next_step": "sign and validate externally",
                "no_install": True,
                "no_signing": True,
            },
            "release_operator_environment": {
                "status": "RELEASE_OPERATOR_ENV_BLOCKED",
                "certificate_thumbprint": "",
                "code_signing_readiness": {"status": "SIGNING_BLOCKED_UNSIGNED"},
                "release_signing_plan_status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
                "blockers": [{"id": "signtool_available"}, {"id": "certificate_thumbprint_provided"}],
                "next_step": "install signtool",
                "no_signing": True,
                "no_install": True,
            },
        },
    )

    snapshot = final_release_snapshot()

    assert "Final Release Verification" in snapshot
    assert "Status: FINAL_RELEASE_BLOCKED" in snapshot
    assert "Exit Code: 2" in snapshot
    assert "Runtime Materialization: READY" in snapshot
    assert "Blockers: signed_installer" in snapshot
    assert "Final Release Path Contract: PASS" in snapshot
    assert "Release Signing Plan Safety: PASS" in snapshot
    assert "External Evidence Safety: PASS" in snapshot
    assert "Operator Environment Safety: PASS" in snapshot
    assert "Release Evidence Contract: BLOCKED" in snapshot
    assert "Operator/Signing Thumbprint Match: BLOCKED" in snapshot
    assert "External Release Evidence:" in snapshot
    assert "- Status: EXTERNAL_RELEASE_EVIDENCE_BLOCKED" in snapshot
    assert "- Handoff Bundle: HANDOFF_VERIFIED" in snapshot
    assert "- Handoff Installer Hash Match: PASS" in snapshot
    assert "- Signed Installer: BLOCKED" in snapshot
    assert "- Authenticode Timestamp: BLOCKED_MISSING_TIMESTAMP" in snapshot
    assert "- Release Signing Evidence: BLOCKED" in snapshot
    assert "- Clean-Machine Signing Evidence Hash Match: BLOCKED" in snapshot
    assert "- Clean-Machine Transfer Manifest Hash Match: BLOCKED" in snapshot
    assert "- Clean-Machine Installer Hash Match: BLOCKED" in snapshot
    assert "- Blockers: signed_installer, external_clean_machine" in snapshot
    assert "Release Operator Environment:" in snapshot
    assert "- Status: RELEASE_OPERATOR_ENV_BLOCKED" in snapshot
    assert "- Code Signing Readiness: SIGNING_BLOCKED_UNSIGNED" in snapshot
    assert "- Release Signing Plan: SIGNING_PLAN_READY_FOR_RELEASE_MACHINE" in snapshot
    assert "- Blockers: signtool_available, certificate_thumbprint_provided" in snapshot
    assert "Final Release Path Contract:" in snapshot
    assert "- installer_root: PASS expected=installer actual=installer" in snapshot
    assert (
        "- signing_evidence: PASS expected=installer/release_signing_evidence.json "
        "actual=installer/release_signing_evidence.json"
    ) in snapshot
    assert "Release Safety Invariants:" in snapshot
    assert "- Release Signing Plan Safety: PASS" in snapshot
    assert "- External Evidence Safety: PASS" in snapshot
    assert "- Operator Environment Safety: PASS" in snapshot
    assert "Release Commands:" in snapshot
    assert "Operator Preflight: PYTHONPATH=. python scripts/runtime/verify_release_operator_environment.py" in snapshot
    assert "Final Verifier: PYTHONPATH=. python scripts/runtime/verify_final_release.py" in snapshot
    assert "Release Signing Plan Commands:" in snapshot
    assert "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1" in snapshot
    assert '--certificate-thumbprint "<CERT_THUMBPRINT>"' in snapshot
    assert "No external signing: True" in snapshot
    assert "No operator signing: True" in snapshot
    assert "No operator install: True" in snapshot
    assert "No model load: True" in snapshot


def test_no_access_outside_outputs_runs(tmp_path: Path) -> None:
    allowed_root = tmp_path / "outputs" / "runs"
    arbitrary_root = tmp_path / "other-runs"
    outside_root = tmp_path / "knowledge" / "runs"

    with pytest.raises(DesktopSecurityError):
        DesktopDataStore(arbitrary_root)

    with pytest.raises(DesktopSecurityError):
        DesktopDataStore(outside_root)

    _create_run(allowed_root)
    assert DesktopDataStore(allowed_root).list_runs()


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)
    store = DesktopDataStore(root)

    with pytest.raises(DesktopSecurityError):
        store.resolve_run_dir("../20260621_080000")


def test_desktop_does_not_invoke_subprocess_for_terminal_or_patch_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Desktop foundation must not execute subprocesses.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    snapshot = DesktopDataStore(root).build_snapshot()

    assert snapshot["security"]["terminal_auto_execute"] is False
    assert snapshot["security"]["patch_auto_apply"] is False
    assert snapshot["security"]["approval_auto_grant"] is False


@pytest.mark.skipif(
    not PYSIDE6_AVAILABLE or os.environ.get("ANN_ENABLE_QT_WINDOW_TESTS") != "1",
    reason="Native Qt window test is covered by manual smoke unless explicitly enabled.",
)
def test_desktop_app_creates_native_window_when_qt_is_available(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "runs"
    _create_run(root)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    workspace_store = WorkspaceStore(
        tmp_path / "config" / "ann_workspace.json",
        project_manager=ProjectManager(allow_temp_paths=True),
    )
    window = create_main_window(DesktopDataStore(root), workspace_store)

    assert window.windowTitle() == "Agentic Engineering Network"
    assert window.sidebar.count() == len(primary_navigation_labels())
    window.close()
    app.quit()
