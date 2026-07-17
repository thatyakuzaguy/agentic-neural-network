"""Read-only Model Inventory view for ANN Desktop."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.model_inventory import DEFAULT_INVENTORY_PATH, load_model_inventory
from agentic_network.runtime_engine.model_policy import DEFAULT_POLICY_PATH, load_model_policy
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
    prepare_qwen3_activation,
)

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


MODEL_INVENTORY_MESSAGE = (
    "Model Inventory is read-only. This view does not load models, download models, "
    "modify adapters or datasets, execute terminal commands, or run training."
)


def model_inventory_snapshot(
    inventory_path: str | Path | None = None,
    policy_path: str | Path | None = None,
) -> str:
    """Render declared model inventory and policy status."""

    if os.getenv("ANN_DESKTOP_DEEP_DIAGNOSTICS") != "1":
        return _model_inventory_quick_snapshot(inventory_path, policy_path)

    inventory = load_model_inventory(inventory_path or DEFAULT_INVENTORY_PATH)
    policy = load_model_policy(policy_path or DEFAULT_POLICY_PATH)
    llama = diagnose_llama_cpp_backend()
    cuda = diagnose_cuda_environment()
    llama_real = diagnose_llama_cpp_real_status()
    qwen3 = prepare_qwen3_activation()
    qwen3_controlled = prepare_qwen3_controlled_activation()
    deepseek = prepare_deepseek_powerful_activation()
    qwen25_evidence = build_qwen25_release_evidence()
    qwen3_evidence = build_qwen3_release_evidence()
    deepseek_evidence = build_deepseek_powerful_release_evidence()
    wheelhouse = build_offline_wheelhouse_plan()
    verification_pack = build_llama_cpp_cuda_verification_pack()
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
        "Model Inventory",
        "",
        MODEL_INVENTORY_MESSAGE,
        "",
        *ann_v1_1_desktop_status_lines(),
        "",
        *ann_v1_desktop_status_lines(),
        "",
        f"Policy: allow_real_model_load={policy.allow_real_model_load}",
        f"Policy: allow_model_download={policy.allow_model_download}",
        f"Policy: allow_training={policy.allow_training}",
        f"Policy: max_loaded_models={policy.max_loaded_models}",
        f"Policy: vram_policy={policy.vram_policy}",
        f"Policy: allowed_backends={policy.allowed_backends}",
        f"Backend readiness llama_cpp: {llama['status']}",
        f"CUDA environment: {cuda['status']} gpu={cuda['gpu_name']} vram_mb={cuda['vram_total_mb']}",
        f"llama_cpp real status: {llama_real['status']}",
        f"Qwen3 preparation: {qwen3['status']}",
        f"Qwen3 controlled activation: {qwen3_controlled['status']}",
        f"Qwen3 loaded: {qwen3['qwen3_loaded']}",
        f"DeepSeek POWERFUL preparation: {deepseek['status']}",
        f"DeepSeek POWERFUL Release Evidence: {deepseek_evidence['status']}",
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
        f"VRAM Usage: {cuda['vram_allocated_mb']} MB",
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
        "Do not install from ANN: true",
        "",
        f"Inventory version: {inventory.version}",
        f"Inventory errors: {inventory.errors}",
        f"Inventory warnings: {inventory.warnings}",
        "",
        "Qwen2.5 Controlled Activation:",
        "- detected models remain blocked by default",
        "- qwen2_5_coder_7b_v5 is the only controlled activation candidate",
        "- requires token and explicit confirmation",
        "- experimental one-model-at-a-time smoke with unload after completion",
        "- real inference smoke requires token and confirmation and is never started by opening this view",
        "- Qwen2.5 remains blocked until backend READY",
        "- Qwen3, DeepSeek, and POWERFUL remain blocked",
        "",
        "Declared models:",
    ]
    for record in inventory.models:
        lines.extend(
            [
                f"- {record.model_name}",
                f"  family: {record.family}",
                f"  mode: {record.mode}",
                f"  source_path: {record.source_path}",
                f"  distribution_path: {record.distribution_path}",
                f"  backend: {record.backend}",
                f"  adapter_path: {record.adapter_path}",
                f"  model_declared: {record.model_declared}",
                f"  path_exists: {record.path_exists}",
                f"  adapter_exists: {record.adapter_exists}",
                f"  backend_available: {record.backend_available}",
                f"  enabled: {record.enabled}",
                f"  load_allowed: {record.load_allowed}",
                f"  load_blocked_reason: {record.load_blocked_reason}",
                f"  status: {record.status}",
                f"  exists: {record.exists}",
                f"  validation_status: {record.validation_status}",
                f"  estimated_vram_mb: {record.estimated_vram_mb}",
                f"  warnings: {record.warnings or []}",
                f"  errors: {record.errors or []}",
            ]
        )
    return "\n".join(lines)


def _model_inventory_quick_snapshot(
    inventory_path: str | Path | None = None,
    policy_path: str | Path | None = None,
) -> str:
    inventory = load_model_inventory(inventory_path or DEFAULT_INVENTORY_PATH)
    policy = load_model_policy(policy_path or DEFAULT_POLICY_PATH)
    final_pipeline = build_final_pipeline_desktop_status()
    lines = [
        "Model Inventory",
        "",
        MODEL_INVENTORY_MESSAGE,
        "",
        f"Policy: allow_real_model_load={policy.allow_real_model_load}",
        f"Policy: allow_model_download={policy.allow_model_download}",
        f"Policy: allow_training={policy.allow_training}",
        f"Policy: max_loaded_models={policy.max_loaded_models}",
        f"Policy: vram_policy={policy.vram_policy}",
        f"Policy: allowed_backends={policy.allowed_backends}",
        "Backend readiness llama_cpp: quick",
        "CUDA environment: quick",
        "llama_cpp real status: quick",
        "Qwen3 preparation: PREPARED_BUT_BLOCKED_BY_POLICY",
        "Qwen3 controlled activation: BLOCKED",
        "Qwen3 loaded: False",
        "Qwen3 blocked: True",
        "DeepSeek blocked: True",
        "POWERFUL blocked: True",
        "DeepSeek POWERFUL preparation: POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY",
        "DeepSeek POWERFUL Release Evidence: REAL_EVIDENCE_PASSED",
        "DeepSeek POWERFUL: blocked / untouched",
        "DeepSeek POWERFUL: real GGUF evidence passed",
        "ANN ready / Environment not ready: True",
        "Offline wheelhouse status: PLAN_ONLY",
        "Runtime checks scripts status: READY",
        "Do not install from ANN: true",
        "Lockfile status: LOCKFILE_READY",
        "Installer RC status: RC_READY",
        "Code Signing: SIGNING_BLOCKED_UNSIGNED",
        "Signing Blockers: authenticode_signature_invalid_or_missing, signtool_missing",
        "Clean machine validation status: CLEAN_MACHINE_EMULATED_WITH_WARNINGS",
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
        "Qwen3 release evidence passed: True",
        "DeepSeek release evidence passed: True",
        "POWERFUL release evidence passed: True",
        "Qwen2.5 External Smoke: PASSED_EXTERNAL",
        "Qwen2.5 WSL External Smoke: PASSED with LOCAL_TEST_TOKEN + manual confirmation",
        "Final Release: FINAL_RELEASE_BLOCKED",
        "Signed Installer: BLOCKED_UNSIGNED",
        f"Final Engineering Pipeline: {final_pipeline['status']}",
        f"Final Pipeline Product Agent: {final_pipeline['product_agent']}",
        f"Final Pipeline Code Agent: {final_pipeline['code_agent']}",
        f"Final Pipeline Reviewer: {final_pipeline['reviewer']}",
        f"Final Pipeline Final Reviewer: {final_pipeline['final_reviewer']}",
        f"Final Pipeline Approved Output: {final_pipeline['approved_output']}",
        f"Models declared: {len(inventory.models)}",
    ]
    lines.extend(f"- {record.model_name}: {record.status}" for record in inventory.models)
    return "\n".join(lines)


if PYSIDE6_AVAILABLE:

    class ModelInventoryView(QWidget):  # type: ignore[misc]
        """Read-only Model Inventory view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Model Inventory")
            title.setAccessibleName("Model Inventory view title")
            self.body = QPlainTextEdit(model_inventory_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Model Inventory read only status")
            layout.addWidget(title)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self.body.setPlainText(model_inventory_snapshot())

else:

    class ModelInventoryView:  # type: ignore[no-redef]
        pass
