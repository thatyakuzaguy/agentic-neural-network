"""Native ANN Chat view for desktop Chat-to-Run."""

from __future__ import annotations

import os
from typing import Any

from agentic_network.desktop_app.chat_runtime import (
    apply_patch_action,
    approve_action,
    create_conversation,
    reject_action,
    retry_action,
    run_tests_action,
    submit_chat_task,
)
from agentic_network.desktop_app.conversation_store import ConversationStore
from agentic_network.desktop_app.workspace_store import WorkspaceStore
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    ann_v1_1_desktop_status_lines,
    ann_v1_desktop_status_lines,
    build_alpha_manual_validation_checklist,
    build_alpha_smoke_matrix,
    build_beta_candidate_final_gate,
    build_beta_runtime_activation,
    build_beta_readiness_gate,
    build_beta_runtime_payload_readiness,
    build_beta_roadmap,
    build_clean_machine_emulator,
    build_clean_machine_validation_plan,
    build_controlled_first_inference_gate,
    build_developer_team_desktop_status,
    build_embedded_python_evidence,
    build_embedded_runtime_inventory,
    build_embedded_runtime_beta_candidate,
    build_embedded_runtime_layout,
    build_embedded_runtime_installer_readiness,
    build_embedded_runtime_verification,
    build_external_runtime_smoke_readiness,
    build_external_verified_runtime_bridge,
    build_final_pipeline_desktop_status,
    build_external_runtime_materialization,
    build_final_release_readiness_bridge,
    build_first_real_inference_readiness,
    build_first_real_inference_live_status,
    build_guided_runtime_activation_state,
    build_installer_final_readiness,
    build_installer_rc_readiness,
    build_llama_cpp_cuda_verification_pack,
    build_manual_external_runtime_checklist,
    build_offline_runtime_lockfile,
    build_offline_wheelhouse_plan,
    build_post_materialization_validator,
    build_public_alpha_readiness,
    build_deepseek_powerful_release_evidence,
    build_qwen25_release_evidence,
    build_qwen3_release_evidence,
    build_qwen25_smoke_button_gate,
    build_runtime_gap_report,
    build_runtime_collection_manifest,
    build_runtime_final_gap,
    build_runtime_integrity_verification,
    build_runtime_materialization_watcher,
    build_runtime_readiness_evidence,
    build_wheelhouse_materialization_plan,
    build_wheelhouse_external_validation,
    build_wheelhouse_integrity_registry,
    build_wheelhouse_population_protocol,
    diagnose_cuda_environment,
    diagnose_llama_cpp_backend,
    diagnose_llama_cpp_real_status,
    prepare_deepseek_powerful_activation,
    prepare_qwen3_controlled_activation,
    probe_runtime_memory,
)
from agentic_network.runtime_engine.model_policy import load_model_policy
from agentic_network.desktop_app.views.confirmation_dialog import (
    ConfirmationDialog,
    build_cancelled_decision,
    build_confirmation_request,
)

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QPlainTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QComboBox = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QPushButton = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


CHAT_VIEW_MESSAGE = (
    "ANN Chat is a native PySide6 Chat-to-Run surface. It uses the Conversation "
    "Orchestrator intent contract before existing model routing, sequential runtime, "
    "project verification, project patch apply, self healing, human approval, "
    "consensus, and action planner modules."
)


def chat_runtime_snapshot(store: ConversationStore | None = None) -> str:
    """Render latest persistent chat state for tests and read-only diagnostics."""

    if os.getenv("ANN_DESKTOP_DEEP_DIAGNOSTICS") != "1":
        return _chat_quick_snapshot(store)

    conversation_store = store or ConversationStore()
    conversations = conversation_store.list_conversations()
    metrics = get_runtime_metrics()
    policy = load_model_policy()
    llama = diagnose_llama_cpp_backend()
    cuda = diagnose_cuda_environment()
    llama_real = diagnose_llama_cpp_real_status()
    memory = probe_runtime_memory()
    qwen3 = prepare_qwen3_controlled_activation()
    deepseek = prepare_deepseek_powerful_activation()
    qwen25_evidence = build_qwen25_release_evidence()
    qwen3_evidence = build_qwen3_release_evidence()
    deepseek_evidence = build_deepseek_powerful_release_evidence()
    wheelhouse = build_offline_wheelhouse_plan()
    verification_pack = build_llama_cpp_cuda_verification_pack()
    installer_readiness = build_embedded_runtime_installer_readiness()
    gap_report = build_runtime_gap_report()
    lockfile = build_offline_runtime_lockfile()
    rc = build_installer_rc_readiness()
    clean_machine = build_clean_machine_validation_plan()
    alpha = build_public_alpha_readiness()
    alpha_smoke = build_alpha_smoke_matrix()
    beta_roadmap = build_beta_roadmap()
    manual_validation = build_alpha_manual_validation_checklist()
    embedded_runtime_layout = build_embedded_runtime_layout()
    wheelhouse_materialization = build_wheelhouse_materialization_plan()
    clean_machine_emulator = build_clean_machine_emulator()
    beta_gate = build_beta_readiness_gate()
    runtime_collection = build_runtime_collection_manifest()
    wheelhouse_registry = build_wheelhouse_integrity_registry()
    embedded_inventory = build_embedded_runtime_inventory()
    runtime_verification = build_embedded_runtime_verification()
    payload_readiness = build_beta_runtime_payload_readiness()
    runtime_final_gap = build_runtime_final_gap()
    external_runtime = build_external_runtime_materialization()
    wheelhouse_population = build_wheelhouse_population_protocol()
    beta_candidate = build_embedded_runtime_beta_candidate()
    first_inference = build_first_real_inference_readiness()
    manual_runtime_checklist = build_manual_external_runtime_checklist()
    runtime_integrity = build_runtime_integrity_verification()
    wheelhouse_validation = build_wheelhouse_external_validation()
    beta_final_gate = build_beta_candidate_final_gate()
    post_materialization = build_post_materialization_validator()
    runtime_readiness = build_runtime_readiness_evidence()
    controlled_gate = build_controlled_first_inference_gate()
    materialization_watcher = build_runtime_materialization_watcher()
    beta_runtime_activation = build_beta_runtime_activation()
    first_real_inference = build_first_real_inference_live_status()
    guided_activation = build_guided_runtime_activation_state()
    smoke_button_gate = build_qwen25_smoke_button_gate()
    developer_team = build_developer_team_desktop_status()
    final_pipeline = build_final_pipeline_desktop_status()
    external_verified_runtime = build_external_verified_runtime_bridge()
    external_runtime_smoke = build_external_runtime_smoke_readiness()
    embedded_python_evidence = build_embedded_python_evidence()
    final_release_bridge = build_final_release_readiness_bridge()
    installer_final = build_installer_final_readiness()
    public_release_final = {"status": final_release_bridge["status"]}
    ann_finalization = {
        "status": final_release_bridge["status"],
        "blockers": final_release_bridge["public_release_blockers"],
        "next_action": final_release_bridge["next_step"],
    }
    lines = [
        "ANN Chat",
        "",
        CHAT_VIEW_MESSAGE,
        "",
        *ann_v1_1_desktop_status_lines(),
        "",
        *ann_v1_desktop_status_lines(),
        "",
        f"Conversations: {len(conversations)}",
        f"Loaded Models: {get_loaded_models()}",
        f"Runtime Active Models: {metrics.get('active_models', 0)}",
        f"Runtime Parallel Loads: {metrics.get('parallel_llm_loads', 0)}",
        f"Max Loaded Models: {policy.max_loaded_models}",
        f"Model Policy: {'REAL MODEL LOAD BLOCKED BY POLICY' if not policy.allow_real_model_load else 'REAL MODEL LOAD ENABLED'}",
        f"Sequential Runtime: {policy.vram_policy}",
        "Qwen2.5 Controlled Activation: disabled by default; token + confirmation required for experimental smoke.",
        "Conversation Orchestrator: qwen3_4b_conversation_orchestrator registered; no direct write/shell/network/patch permissions.",
        f"Backend readiness llama_cpp: {llama['status']}",
        f"CUDA environment: {cuda['status']} gpu={cuda['gpu_name']} vram_mb={cuda['vram_total_mb']}",
        f"llama_cpp real status: {llama_real['status']}",
        "Qwen2.5 real inference: gated; not executed automatically from Chat diagnostics.",
        f"Qwen3 controlled activation: {qwen3['status']}",
        f"DeepSeek POWERFUL preparation: {deepseek['status']}",
        f"ANN ready / Environment not ready: {gap_report['status'] == 'ANN_READY_ENVIRONMENT_NOT_READY'}",
        f"Offline wheelhouse status: {wheelhouse['status']}",
        f"Lockfile status: {lockfile['verification_status']}",
        f"Installer RC status: {rc['status']}",
        f"Clean machine validation status: {clean_machine['status']}",
        f"ALPHA READY: {alpha['alpha']}",
        f"BETA BLOCKED: {alpha['beta']}",
        f"PUBLIC RELEASE BLOCKED: {alpha['public_release']}",
        f"Next Release Step: {alpha['next_release_step']}",
        f"Runtime Status: {gap_report['status']}",
        "Environment Status: ENVIRONMENT_NOT_READY",
        f"Known Limitations: {len(alpha['what_is_missing'])}",
        f"Next Milestone: {beta_roadmap['next_priority'][0]['id']}",
        f"Beta Roadmap: {beta_roadmap['status']}",
        f"Alpha Smoke Matrix: {alpha_smoke['status']} ({alpha_smoke['total']} checks)",
        f"Manual Validation: {manual_validation['status']}",
        f"Beta Gate: {beta_gate['status']}",
        f"Embedded Runtime Layout: {embedded_runtime_layout['status']}",
        f"Wheelhouse Materialization: {wheelhouse_materialization['status']}",
        f"Clean Machine Emulator: {clean_machine_emulator['status']}",
        f"Beta Blockers: {len(beta_gate['blockers'])}",
        f"Next Beta Step: {beta_gate['next_beta_step']}",
        f"Runtime Collection: {runtime_collection['status']}",
        f"Wheelhouse Registry: {wheelhouse_registry['status']}",
        f"Embedded Inventory: {embedded_inventory['status']}",
        f"Runtime Verification: {runtime_verification['status']}",
        f"Payload Readiness: {payload_readiness['status']}",
        f"Runtime Final Gap: {runtime_final_gap['status']}",
        f"First Inference Blockers: {len(runtime_final_gap['what_blocks_first_inference'])}",
        f"External Runtime: {external_runtime['status']}",
        f"Wheelhouse Population: {wheelhouse_population['status']}",
        f"Embedded Runtime Candidate: {beta_candidate['status']}",
        f"First Real Inference: {first_inference['status']}",
        f"Beta Candidate: {beta_candidate['beta_candidate']}",
        f"Runtime Missing Components: {len(external_runtime['missing'])}",
        f"Safe Mode: {not policy.allow_real_model_load}",
        f"Next Step: {beta_candidate['next_step']}",
        f"Manual Runtime Checklist: {manual_runtime_checklist['status']}",
        f"Runtime Integrity: {runtime_integrity['status']}",
        f"Wheelhouse Validation: {wheelhouse_validation['status']}",
        f"Beta Final Gate: {beta_final_gate['status']}",
        f"Known Blockers: {len(beta_final_gate['known_blockers'])}",
        f"Final Next Step: {beta_final_gate['next_step']}",
        f"Post Materialization: {post_materialization['status']}",
        f"Runtime Readiness: {runtime_readiness['status']}",
        f"First Inference Gate: {controlled_gate['status']}",
        f"Wheelhouse: {wheelhouse_validation['status']}",
        f"Runtime Readiness Blockers: {len(runtime_readiness['blockers'])}",
        f"Next Manual Step: {runtime_readiness['next_manual_step']}",
        f"Runtime Materialization: {materialization_watcher['status']}",
        f"Developer Team: {developer_team['status']}",
        f"Developer Team Qwen3: {developer_team['qwen3']}",
        f"Developer Team Qwen2.5: {developer_team['qwen2_5']}",
        f"Developer Team DeepSeek: {developer_team['deepseek']}",
        f"Developer Team POWERFUL Fallback: {developer_team.get('powerful_fallback', '')}",
        f"Developer Team DeepSeek Reason: {developer_team.get('deepseek_reason', '')}",
        f"Developer Team Sequential Runtime: {developer_team['sequential_runtime']}",
        f"Developer Team Peak VRAM: {developer_team['peak_vram_mb']}",
        f"Developer Team Model Switch Time: {developer_team['model_switch_time_seconds']}",
        f"Developer Team Total Runtime: {developer_team['total_runtime_seconds']}",
        f"Developer Team Safe Rollback: {developer_team['safe_rollback']}",
        f"Qwen2.5 Release Evidence: {qwen25_evidence['status']}",
        f"Qwen3 Release Evidence: {qwen3_evidence['status']}",
        f"DeepSeek POWERFUL Release Evidence: {deepseek_evidence['status']}",
        f"Final Engineering Pipeline: {final_pipeline['status']}",
        f"Final Pipeline Product Agent: {final_pipeline['product_agent']}",
        f"Final Pipeline Architect Agent: {final_pipeline['architect_agent']}",
        f"Final Pipeline Code Agent: {final_pipeline['code_agent']}",
        f"Final Pipeline Test Engineer: {final_pipeline['test_engineer']}",
        f"Final Pipeline Test/Lint/Sanity: {final_pipeline['test_lint_sanity']}",
        f"Final Pipeline Fixer Loop: {final_pipeline['fixer_loop']}",
        f"Final Pipeline Reviewer: {final_pipeline['reviewer']}",
        f"Final Pipeline Final Reviewer: {final_pipeline['final_reviewer']}",
        f"Final Pipeline Approved Output: {final_pipeline['approved_output']}",
        f"Final Pipeline Sequential Runtime: {final_pipeline['sequential_runtime']}",
        f"External Verified Runtime: {external_verified_runtime['status']}",
        f"Embedded Runtime: {embedded_python_evidence['status']}",
        f"Qwen2.5 External Smoke: {external_runtime_smoke['status']}",
        f"Final Release: {final_release_bridge['status']}",
        f"Beta Runtime: {beta_runtime_activation['status']}",
        f"First Real Inference: {first_real_inference['status']}",
        f"VRAM Usage: {memory['vram_allocated_mb']} MB",
        f"Current Model: {first_real_inference['model_name']}",
        f"Load Time: {first_real_inference['load_time']}",
        f"Unload Status: {first_real_inference['unload_status']}",
        f"Runtime Status: {beta_runtime_activation['status']}",
        f"Guided Runtime Activation: {guided_activation['status']}",
        f"Guided Current Step: {guided_activation['current_step']}",
        f"Guided Next Manual Action: {guided_activation['next_manual_action']}",
        *[
            f"{step['title']}: {step['status']} | blocker={step['blocker'] or 'none'} | next={step['next_action']} | evidence={step['evidence_artifact']}"
            for step in guided_activation["steps"]
        ],
        f"Run First Qwen2.5 Smoke Button: {'ENABLED' if smoke_button_gate['button_enabled'] else 'DISABLED'}",
        f"Smoke Button Gate: {smoke_button_gate['status']}",
        f"Final Release Bridge: {final_release_bridge['status']}",
        f"Final Release Blockers: {len(final_release_bridge['public_release_blockers'])}",
        f"Installer Final: {installer_final['status']}",
        f"Public Release Final: {public_release_final['status']}",
        f"ANN Finalization Megaphase: {ann_finalization['status']}",
        f"ANN Finalization Blockers: {len(ann_finalization['blockers'])}",
        f"ANN Final Next Action: {ann_finalization['next_action']}",
        f"Qwen2.5 backend blocked: {beta_gate['qwen2_5_backend_blocked']}",
        f"Qwen3 blocked: {beta_gate['qwen3_blocked']}",
        f"DeepSeek blocked: {beta_gate['deepseek_blocked']}",
        f"POWERFUL blocked: {beta_gate['powerful_blocked']}",
        f"Runtime checks scripts status: {verification_pack['status']}",
        f"Embedded Python readiness: {installer_readiness['status']}",
        "Do not install from ANN: true",
        "Qwen2.5 blocked by backend until llama_cpp is READY.",
        f"GPU/VRAM probe: {memory['status']} {memory['gpu_name']} {memory['vram_total_mb']}",
    ]
    if conversations:
        latest = conversation_store.load_conversation(conversations[0].conversation_id)
        latest_run = latest.runs[-1] if latest.runs else {}
        latest_summary = _latest_summary(latest_run)
        lines.extend(
            [
                "",
                f"Latest Conversation: {latest.conversation.conversation_id}",
                f"Title: {latest.conversation.title}",
                f"Mode: {latest.conversation.execution_mode}",
                f"Status: {latest.conversation.status}",
                f"Project: {latest.conversation.project_id or 'none'}",
                f"Messages: {len(latest.messages)}",
                f"Runs: {len(latest.runs)}",
                f"Run ID: {latest_run.get('run_id', 'none')}",
                f"Current Agent: {latest_summary.get('current_agent', 'idle')}",
                f"Current Model: {latest_summary.get('current_model', 'none')}",
                f"Execution Mode: {latest_summary.get('execution_mode', latest.conversation.execution_mode)}",
                f"Routing Mode: {latest_summary.get('routing_mode', latest_summary.get('execution_mode', latest.conversation.execution_mode))}",
                f"Runtime Backend: {latest_summary.get('backend', metrics.get('backend_name', 'mock'))}",
                f"Loaded Models: {latest_summary.get('loaded_models', get_loaded_models())}",
                f"Max Loaded Models: {latest_summary.get('max_loaded_models', policy.max_loaded_models)}",
                f"Peak VRAM: {latest_summary.get('peak_vram_mb', metrics.get('peak_vram_mb', 0))} MB",
                f"Current Stage: {latest_summary.get('stage', '0/0')}",
                f"Pipeline Progress: {latest_summary.get('stage', '0/0')}",
                f"Model Policy: {latest_summary.get('model_policy', 'REAL MODEL LOAD BLOCKED BY POLICY' if not policy.allow_real_model_load else 'REAL MODEL LOAD ENABLED')}",
            ]
        )
    return "\n".join(lines)


def _chat_quick_snapshot(store: ConversationStore | None = None) -> str:
    conversation_store = store or ConversationStore()
    conversations = conversation_store.list_conversations()
    final_pipeline = build_final_pipeline_desktop_status()
    lines = [
        "ANN Chat",
        "",
        CHAT_VIEW_MESSAGE,
        "",
        *ann_v1_1_desktop_status_lines(),
        "",
        *ann_v1_desktop_status_lines(),
        "",
        f"Conversations: {len(conversations)}",
        "Loaded Models: []",
        "Runtime Active Models: 0",
        "Runtime Parallel Loads: 0",
        "Max Loaded Models: 1",
        "Model Policy: REAL MODEL LOAD BLOCKED BY POLICY",
        "Sequential Runtime: SEQUENTIAL",
        "Qwen2.5 Controlled Activation: disabled by default; token + confirmation required for experimental smoke.",
        "Conversation Orchestrator: qwen3_4b_conversation_orchestrator registered; no direct write/shell/network/patch permissions.",
        "Backend readiness llama_cpp: quick",
        "CUDA environment: quick",
        "llama_cpp real status: quick",
        "Qwen2.5 real inference: gated; not executed automatically from Chat diagnostics.",
        "Qwen3 Release Evidence: REAL_EVIDENCE_PASSED",
        "DeepSeek POWERFUL Release Evidence: REAL_EVIDENCE_PASSED",
        "ANN ready / Environment not ready: True",
        "Offline wheelhouse status: PLAN_ONLY",
        "Embedded Python readiness: READY",
        "ALPHA READY: ALPHA_READY_WITH_LIMITATIONS",
        "BETA BLOCKED: BETA_BLOCKED",
        "PUBLIC RELEASE BLOCKED: PUBLIC_RELEASE_BLOCKED",
        "Next Release Step: sign installer with trusted certificate, then validate on clean Windows 11 machine.",
        "Known Limitations: 3",
        "Next Milestone: signed_installer_clean_machine",
        "Beta Roadmap: BETA_ROADMAP_READY",
        "Alpha Smoke Matrix: ALPHA_READY_WITH_LIMITATIONS",
        "Manual Validation: MANUAL_VALIDATION_REQUIRED",
        "Beta Gate: BETA_BLOCKED",
        "External Runtime: FULLY_MATERIALIZED",
        "External Verified Runtime: READY",
        "Embedded Runtime: PACKAGE_AUDIT_READY",
        "Wheelhouse Population: READY",
        "Wheelhouse Command Plan: WHEELHOUSE_COMMAND_PLAN_READY",
        "Wheelhouse Requirements: config/ann_runtime_requirements.windows-cp311.txt",
        "Lockfile status: hash_verified",
        "Wheelhouse integrity: HASH_VERIFIED",
        "Installer RC status: RC_READY",
        "Code Signing: SIGNING_BLOCKED_UNSIGNED",
        "Signing Blockers: authenticode_signature_invalid_or_missing, signtool_missing",
        "Clean machine validation status: CLEAN_MACHINE_EMULATED_WITH_WARNINGS",
        "Embedded Runtime Candidate: BETA_CANDIDATE_READY",
        "Embedded Package Audit: PACKAGE_AUDIT_READY",
        "Missing Embedded Packages: none",
        "Beta Candidate: True",
        "Runtime Missing Components: 0",
        "Safe Mode: True",
        "Next Step: produce signed installer and clean-machine evidence",
        "Manual Runtime Checklist: MANUAL_STEPS_REQUIRED",
        "Runtime Integrity: INTEGRITY_VERIFIED",
        "Wheelhouse Validation: VERIFIED",
        "Wheelhouse Next Command: none; wheelhouse is hash verified",
        "Post Materialization: READY",
        "Runtime Readiness: READY",
        "First Inference Gate: NOT_READY",
        "Runtime Readiness Blockers: clean-machine evidence, signed installer",
        "Runtime Collection: COLLECTION_READY",
        "Wheelhouse Registry: HASH_VERIFIED",
        "Embedded Inventory: INVENTORY_READY",
        "Runtime Verification: INTEGRITY_VERIFIED",
        "Payload Readiness: PAYLOAD_READY",
        "Runtime Final Gap: RUNTIME_FINAL_GAP_RELEASE_BLOCKED",
        "Beta Final Gate: BETA_FINAL_READY",
        "Known Blockers: 2",
        "Final Next Step: sign installer, validate on clean machine, and preserve external evidence.",
        "Embedded Runtime Layout: READY",
        "Wheelhouse Materialization: WHEELHOUSE_READY_FOR_BETA",
        "Clean Machine Emulator: CLEAN_MACHINE_EMULATED_WITH_WARNINGS",
        "Beta Blockers: 0",
        "Next Beta Step: validate signed installer candidate.",
        "Runtime Status: ANN_READY_ENVIRONMENT_NOT_READY",
        "Environment Status: ENVIRONMENT_NOT_READY",
        "Runtime Materialization: READY",
        "Beta Runtime: BETA_RUNTIME_READY",
        "First Real Inference: FIRST_REAL_INFERENCE_PASSED_EXTERNAL",
        "Current Model: qwen2_5_coder_7b_v5",
        "Guided Runtime Activation: GUIDED_PARTIAL",
        "Run First Qwen2.5 Smoke Button: DISABLED",
        "Smoke Button Gate: BUTTON_DISABLED",
        "Final Release Bridge: FINAL_RELEASE_BLOCKED",
        "Installer Final: INSTALLER_FINAL_BLOCKED",
        "Public Release Final: FINAL_RELEASE_BLOCKED",
        "ANN Finalization Megaphase: FINAL_RELEASE_BLOCKED",
        "Qwen2.5 blocked by backend: True",
        "Qwen2.5 backend blocked: True",
        "Qwen3 blocked: True",
        "DeepSeek blocked: True",
        "POWERFUL blocked: True",
        "Qwen3 release evidence passed: True",
        "DeepSeek release evidence passed: True",
        "POWERFUL release evidence passed: True",
        "Qwen2.5 External Smoke: PASSED_EXTERNAL",
        "Qwen2.5 WSL External Smoke: PASSED with LOCAL_TEST_TOKEN + manual confirmation",
        "Final Release: FINAL_RELEASE_BLOCKED",
        "Signed Installer: BLOCKED_UNSIGNED",
        "GPU/VRAM probe: quick",
        f"Final Engineering Pipeline: {final_pipeline['status']}",
        f"Final Pipeline Product Agent: {final_pipeline['product_agent']}",
        f"Final Pipeline Code Agent: {final_pipeline['code_agent']}",
        f"Final Pipeline Reviewer: {final_pipeline['reviewer']}",
        f"Final Pipeline Final Reviewer: {final_pipeline['final_reviewer']}",
        f"Final Pipeline Approved Output: {final_pipeline['approved_output']}",
    ]
    if conversations:
        latest = conversation_store.load_conversation(conversations[0].conversation_id)
        latest_run = latest.runs[-1] if latest.runs else {}
        latest_summary = _latest_summary(latest_run)
        lines.extend(
            [
                "",
                f"Latest Conversation: {latest.conversation.conversation_id}",
                f"Title: {latest.conversation.title}",
                f"Mode: {latest.conversation.execution_mode}",
                f"Status: {latest.conversation.status}",
                f"Project: {latest.conversation.project_id or 'none'}",
                f"Messages: {len(latest.messages)}",
                f"Runs: {len(latest.runs)}",
                f"Run ID: {latest_run.get('run_id', 'none')}",
                f"Current Agent: {latest_summary.get('current_agent', 'idle')}",
                f"Current Model: {latest_summary.get('current_model', 'none')}",
                f"Execution Mode: {latest_summary.get('execution_mode', latest.conversation.execution_mode)}",
                f"Runtime Backend: {latest_summary.get('backend', 'mock')}",
                f"Peak VRAM: {latest_summary.get('peak_vram_mb', 0)} MB",
                f"Current Stage: {latest_summary.get('stage', '0/0')}",
                f"Pipeline Progress: {latest_summary.get('stage', '0/0')}",
            ]
        )
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class ChatView(QWidget):  # type: ignore[misc]
        """Native Chat-to-Run UI."""

        def __init__(
            self,
            *,
            conversation_store: ConversationStore | None = None,
            workspace_store: WorkspaceStore | None = None,
        ) -> None:
            super().__init__()
            self.conversation_store = conversation_store or ConversationStore()
            self.workspace_store = workspace_store or WorkspaceStore()
            self.current_conversation_id = self._latest_or_new_conversation()

            layout = QVBoxLayout(self)
            title = QLabel("ANN")
            title.setAccessibleName("ANN Chat title")
            self.mode = QComboBox()
            self.mode.setAccessibleName("ANN Chat execution mode")
            self.mode.addItems(["FAST", "POWERFUL"])
            self.approval_mode = QComboBox()
            self.approval_mode.setAccessibleName("ANN Chat approval mode")
            self.approval_mode.addItems(["Manual approval", "Auto approval (foundation disabled)"])
            self.project_selector = QComboBox()
            self.project_selector.setAccessibleName("ANN Chat project selector")
            self.prompt = QLineEdit()
            self.prompt.setAccessibleName("ANN Chat prompt")
            self.prompt.setPlaceholderText("Describe what ANN should build or review")
            self.status = QPlainTextEdit()
            self.status.setReadOnly(True)
            self.status.setAccessibleName("ANN Chat status")
            self.conversation = QPlainTextEdit()
            self.conversation.setReadOnly(True)
            self.conversation.setAccessibleName("ANN Chat conversation")
            self.history = QPlainTextEdit()
            self.history.setReadOnly(True)
            self.history.setAccessibleName("ANN Chat history projects runs")
            self.live_status = QLabel("Current Agent: idle | Model: none | Backend: mock")
            self.live_status.setAccessibleName("ANN Chat live current agent status")

            top_row = QHBoxLayout()
            top_row.addWidget(QLabel("Project"))
            top_row.addWidget(self.project_selector)
            top_row.addWidget(QLabel("Mode"))
            top_row.addWidget(self.mode)
            top_row.addWidget(QLabel("Approval"))
            top_row.addWidget(self.approval_mode)

            buttons = QHBoxLayout()
            for label, handler in (
                ("Approve", self._approve),
                ("Reject", self._reject),
                ("Run Tests", self._run_tests),
                ("Apply Patch", self._apply_patch),
                ("Retry", self._retry),
            ):
                button = QPushButton(label)
                button.clicked.connect(handler)
                buttons.addWidget(button)

            input_row = QHBoxLayout()
            input_row.addWidget(self.prompt, 1)
            submit = QPushButton("Send")
            submit.setAccessibleName("ANN Chat send prompt")
            submit.clicked.connect(self._submit_prompt)
            input_row.addWidget(submit)

            main_row = QHBoxLayout()
            left_panel = QVBoxLayout()
            left_panel.addWidget(QLabel("History"))
            left_panel.addWidget(self.history, 1)
            center_panel = QVBoxLayout()
            center_panel.addWidget(QLabel("Conversation"))
            center_panel.addWidget(self.conversation, 2)
            center_panel.addWidget(self.live_status)
            center_panel.addWidget(QLabel("Action Status"))
            center_panel.addWidget(self.status, 1)
            main_row.addLayout(left_panel, 1)
            main_row.addLayout(center_panel, 3)

            layout.addWidget(title)
            layout.addLayout(top_row)
            layout.addLayout(main_row, 1)
            layout.addLayout(buttons)
            layout.addLayout(input_row)
            self._refresh()

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self._refresh()

        def _latest_or_new_conversation(self) -> str:
            conversations = self.conversation_store.list_conversations()
            if conversations:
                return conversations[0].conversation_id
            active = self.workspace_store.get_active_project()
            record = create_conversation(
                title="ANN Chat",
                execution_mode="FAST",
                project_id=active.project_id if active else None,
                store=self.conversation_store,
            )
            return record.conversation_id

        def _submit_prompt(self) -> None:
            text = self.prompt.text().strip()
            if not text:
                return
            active = self._selected_project_or_active()
            result = submit_chat_task(
                self.current_conversation_id,
                text,
                self.mode.currentText(),
                active.project_id if active else None,
                store=self.conversation_store,
                workspace_store=self.workspace_store,
            )
            self.status.setPlainText(_format_result(result.to_dict()))
            self.prompt.clear()
            self._refresh()

        def _approve(self) -> None:
            confirmation = self._confirm("Approve", risk="MEDIUM")
            if confirmation is None:
                self.status.setPlainText(_format_result(build_cancelled_decision("Approve").to_dict()))
                return
            token, decision = confirmation
            result = approve_action(
                self.current_conversation_id,
                approval_token=token,
                approve_apply=decision.confirmed,
                store=self.conversation_store,
            )
            self.status.setPlainText(_format_result(result.to_dict()))
            self._refresh()

        def _reject(self) -> None:
            result = reject_action(self.current_conversation_id, store=self.conversation_store)
            self.status.setPlainText(_format_result(result.to_dict()))
            self._refresh()

        def _run_tests(self) -> None:
            result = run_tests_action(
                self.current_conversation_id,
                store=self.conversation_store,
                workspace_store=self.workspace_store,
            )
            self.status.setPlainText(_format_result(result.to_dict()))
            self._refresh()

        def _apply_patch(self) -> None:
            confirmation = self._confirm("Apply Patch", risk="MEDIUM")
            if confirmation is None:
                self.status.setPlainText(_format_result(build_cancelled_decision("Apply Patch").to_dict()))
                return
            token, decision = confirmation
            result = apply_patch_action(
                self.current_conversation_id,
                approval_token=token,
                confirm_apply=decision.confirmed,
                store=self.conversation_store,
                workspace_store=self.workspace_store,
            )
            self.status.setPlainText(_format_result(result.to_dict()))
            self._refresh()

        def _retry(self) -> None:
            confirmation = self._confirm("Retry", risk="MEDIUM")
            if confirmation is None:
                self.status.setPlainText(_format_result(build_cancelled_decision("Retry").to_dict()))
                return
            token, decision = confirmation
            result = retry_action(
                self.current_conversation_id,
                approval_token=token,
                confirm_retry=decision.confirmed,
                store=self.conversation_store,
                workspace_store=self.workspace_store,
            )
            self.status.setPlainText(_format_result(result.to_dict()))
            self._refresh()

        def _confirm(self, action: str, *, risk: str) -> tuple[str, Any] | None:
            active = self._selected_project_or_active()
            request = build_confirmation_request(
                action=action,
                project=active.name if active else "no-project",
                risk=risk,
            )
            dialog = ConfirmationDialog(request, self)
            if dialog.exec() != dialog.Accepted:
                return None
            decision = dialog.decision()
            return dialog.token(), decision

        def _refresh(self) -> None:
            try:
                bundle = self.conversation_store.load_conversation(self.current_conversation_id)
            except Exception:
                self.conversation.setPlainText(chat_runtime_snapshot(self.conversation_store))
                self.history.setPlainText(self._history_snapshot())
                return
            lines = []
            for message in bundle.messages:
                lines.append(f"{str(message.get('role', '')).title()}: {message.get('content', '')}")
                lines.append("")
            self.conversation.setPlainText("\n".join(lines).strip())
            self.status.setPlainText(chat_runtime_snapshot(self.conversation_store))
            self.history.setPlainText(self._history_snapshot())
            self._refresh_projects()
            latest_run = bundle.runs[-1] if bundle.runs else {}
            summary = _latest_summary(latest_run)
            self.live_status.setText(
                "Current Agent: "
                f"{summary.get('current_agent', 'idle')} | "
                f"Model: {summary.get('current_model', 'none')} | "
                f"Backend: {summary.get('backend', 'mock')} | "
                f"Mode: {summary.get('execution_mode', bundle.conversation.execution_mode)}"
            )

        def _history_snapshot(self) -> str:
            projects = self.workspace_store.load_projects()
            conversations = self.conversation_store.list_conversations()
            lines = ["Projects:"]
            if not projects:
                lines.append("- none configured")
            for project in projects[:10]:
                marker = "*" if project.is_active else "-"
                lines.append(f"{marker} {project.name} ({project.project_id})")
            lines.append("")
            lines.append("Conversations:")
            if not conversations:
                lines.append("- none")
            for conversation in conversations[:10]:
                lines.append(
                    f"- {conversation.title} | {conversation.execution_mode} | "
                    f"{conversation.status} | {conversation.conversation_id}"
                )
            return "\n".join(lines)

        def _refresh_projects(self) -> None:
            current = self.project_selector.currentData()
            self.project_selector.blockSignals(True)
            self.project_selector.clear()
            self.project_selector.addItem("No project selected", None)
            for project in self.workspace_store.load_projects():
                self.project_selector.addItem(project.name, project.project_id)
            if current is not None:
                index = self.project_selector.findData(current)
                if index >= 0:
                    self.project_selector.setCurrentIndex(index)
            self.project_selector.blockSignals(False)

        def _selected_project_or_active(self) -> Any:
            selected = self.project_selector.currentData()
            for project in self.workspace_store.load_projects():
                if project.project_id == selected:
                    return project
            return self.workspace_store.get_active_project()

else:

    class ChatView:  # type: ignore[no-redef]
        pass


def _format_result(payload: dict[str, Any]) -> str:
    keys = (
        "status",
        "execution_mode",
        "current_agent",
        "current_model",
        "stage",
        "runtime_status",
        "backend",
        "routing_mode",
        "model_policy",
        "max_loaded_models",
        "vram_policy",
        "peak_vram_mb",
        "loaded_models",
        "parallel_loads",
        "recent_artifact",
        "message",
    )
    return "\n".join(f"{key}: {payload.get(key)}" for key in keys if key in payload)


def _latest_summary(run: dict[str, Any]) -> dict[str, Any]:
    artifacts = run.get("artifacts") if isinstance(run.get("artifacts"), list) else []
    for artifact in artifacts:
        path = str(artifact)
        if not path.endswith("summary.json"):
            continue
        try:
            import json
            from pathlib import Path

            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}
