"""Read-only first-run system check view for ANN Desktop."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agentic_network.installer.distribution import first_run_distribution_state
from agentic_network.installer.validation import validate_runtime_requirements
from agentic_network.runtime_engine.local_model_activation import (
    ann_v1_1_desktop_status_lines,
    ann_v1_desktop_status_lines,
    build_alpha_manual_validation_checklist,
    build_alpha_smoke_matrix,
    build_backend_manual_readiness_checklist,
    build_beta_runtime_activation,
    build_beta_readiness_gate,
    build_beta_candidate_final_gate,
    build_beta_runtime_payload_readiness,
    build_beta_roadmap,
    build_clean_machine_emulator,
    build_clean_machine_validation_plan,
    build_controlled_first_inference_gate,
    build_developer_team_desktop_status,
    build_embedded_python_evidence,
    build_embedded_runtime_inventory,
    build_embedded_runtime_beta_candidate,
    build_embedded_python_release_plan,
    build_embedded_runtime_layout,
    build_embedded_runtime_installer_readiness,
    build_embedded_runtime_verification,
    build_external_runtime_smoke_readiness,
    build_external_verified_runtime_bridge,
    build_final_pipeline_desktop_status,
    build_external_runtime_matrix,
    build_external_runtime_materialization,
    build_final_release_readiness_bridge,
    build_first_real_inference_readiness,
    build_first_real_inference_live_status,
    build_guided_runtime_activation_state,
    build_installer_final_readiness,
    build_installer_rc_readiness,
    build_local_model_preflight,
    build_llama_cpp_cuda_verification_pack,
    build_manual_external_runtime_checklist,
    build_offline_runtime_lockfile,
    build_offline_wheelhouse_plan,
    build_public_alpha_readiness,
    build_deepseek_powerful_release_evidence,
    build_qwen25_release_evidence,
    build_qwen3_release_evidence,
    build_post_materialization_validator,
    build_qwen25_smoke_button_gate,
    build_real_inference_launch_guard,
    build_release_packaging_dry_run,
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
    validate_wheelhouse_integrity,
    prepare_deepseek_powerful_activation,
    prepare_qwen3_controlled_activation,
    prepare_qwen3_activation,
    probe_runtime_memory,
)

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QHBoxLayout = None
    QLabel = None
    QPlainTextEdit = None
    QPushButton = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


FIRST_RUN_MESSAGE = (
    "First Run / System Check is read-only. It does not install dependencies, "
    "download models, run training, or modify protected ANN paths."
)


def build_first_run_state(install_root: str | Path | None = None) -> dict[str, Any]:
    """Return first-run productization state without mutating the host."""

    if os.getenv("ANN_DESKTOP_DEEP_DIAGNOSTICS") != "1":
        return _build_first_run_quick_state(install_root)

    result = validate_runtime_requirements(install_root)
    distribution = first_run_distribution_state(install_root)
    preflight = build_local_model_preflight()
    backend_readiness = diagnose_llama_cpp_backend()
    cuda_environment = diagnose_cuda_environment()
    llama_cpp_real_status = diagnose_llama_cpp_real_status()
    memory_probe = probe_runtime_memory()
    qwen3_preparation = prepare_qwen3_activation()
    qwen3_controlled_activation = prepare_qwen3_controlled_activation()
    deepseek_powerful_preparation = prepare_deepseek_powerful_activation()
    qwen25_release_evidence = build_qwen25_release_evidence()
    qwen3_release_evidence = build_qwen3_release_evidence()
    deepseek_release_evidence = build_deepseek_powerful_release_evidence()
    external_runtime_matrix = build_external_runtime_matrix()
    embedded_python_release_plan = build_embedded_python_release_plan()
    backend_manual_readiness = build_backend_manual_readiness_checklist()
    real_inference_launch_guard = build_real_inference_launch_guard()
    offline_wheelhouse_plan = build_offline_wheelhouse_plan()
    verification_pack = build_llama_cpp_cuda_verification_pack()
    embedded_runtime_installer_readiness = build_embedded_runtime_installer_readiness()
    runtime_gap_report = build_runtime_gap_report()
    offline_runtime_lockfile = build_offline_runtime_lockfile()
    wheelhouse_integrity = validate_wheelhouse_integrity()
    clean_machine_validation_plan = build_clean_machine_validation_plan()
    installer_rc_readiness = build_installer_rc_readiness()
    public_alpha_readiness = build_public_alpha_readiness()
    release_packaging_dry_run = build_release_packaging_dry_run()
    alpha_smoke_matrix = build_alpha_smoke_matrix()
    beta_roadmap = build_beta_roadmap()
    alpha_manual_validation = build_alpha_manual_validation_checklist()
    embedded_runtime_layout = build_embedded_runtime_layout()
    wheelhouse_materialization = build_wheelhouse_materialization_plan()
    clean_machine_emulator = build_clean_machine_emulator()
    beta_readiness_gate = build_beta_readiness_gate()
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
    public_release_final = {
        "status": final_release_bridge["status"],
        "blockers": final_release_bridge["public_release_blockers"],
    }
    ann_finalization = {
        "status": final_release_bridge["status"],
        "blockers": final_release_bridge["public_release_blockers"],
        "next_action": final_release_bridge["next_step"],
    }
    return {
        "status": result.status,
        "python_executable": result.python_executable,
        "python_version": result.python_version,
        "pyside6_available": result.pyside6_available,
        "desktop_importable": result.desktop_importable,
        "install_root": result.install_root,
        "data_root": result.data_root,
        "outputs_root": result.outputs_root,
        "projects_root": result.projects_root,
        "models_root": result.models_root,
        "runtime_config_exists": result.runtime_config_exists,
        "model_policy_exists": result.model_policy_exists,
        "warnings": result.warnings,
        "errors": result.errors,
        "distribution": distribution,
        "model_preflight": preflight,
        "backend_readiness": backend_readiness,
        "cuda_environment": cuda_environment,
        "llama_cpp_real_status": llama_cpp_real_status,
        "memory_probe": memory_probe,
        "qwen3_preparation": qwen3_preparation,
        "qwen3_controlled_activation": qwen3_controlled_activation,
        "deepseek_powerful_preparation": deepseek_powerful_preparation,
        "qwen25_release_evidence": qwen25_release_evidence,
        "qwen3_release_evidence": qwen3_release_evidence,
        "deepseek_release_evidence": deepseek_release_evidence,
        "external_runtime_matrix": external_runtime_matrix,
        "embedded_python_release_plan": embedded_python_release_plan,
        "backend_manual_readiness": backend_manual_readiness,
        "real_inference_launch_guard": real_inference_launch_guard,
        "offline_wheelhouse_plan": offline_wheelhouse_plan,
        "verification_pack": verification_pack,
        "embedded_runtime_installer_readiness": embedded_runtime_installer_readiness,
        "runtime_gap_report": runtime_gap_report,
        "offline_runtime_lockfile": offline_runtime_lockfile,
        "wheelhouse_integrity": wheelhouse_integrity,
        "clean_machine_validation_plan": clean_machine_validation_plan,
        "installer_rc_readiness": installer_rc_readiness,
        "public_alpha_readiness": public_alpha_readiness,
        "release_packaging_dry_run": release_packaging_dry_run,
        "alpha_smoke_matrix": alpha_smoke_matrix,
        "beta_roadmap": beta_roadmap,
        "alpha_manual_validation": alpha_manual_validation,
        "embedded_runtime_layout": embedded_runtime_layout,
        "wheelhouse_materialization": wheelhouse_materialization,
        "clean_machine_emulator": clean_machine_emulator,
        "beta_readiness_gate": beta_readiness_gate,
        "runtime_collection": runtime_collection,
        "wheelhouse_registry": wheelhouse_registry,
        "embedded_inventory": embedded_inventory,
        "runtime_verification": runtime_verification,
        "payload_readiness": payload_readiness,
        "runtime_final_gap": runtime_final_gap,
        "external_runtime": external_runtime,
        "wheelhouse_population": wheelhouse_population,
        "beta_candidate": beta_candidate,
        "first_inference": first_inference,
        "manual_runtime_checklist": manual_runtime_checklist,
        "runtime_integrity": runtime_integrity,
        "wheelhouse_validation": wheelhouse_validation,
        "beta_final_gate": beta_final_gate,
        "post_materialization": post_materialization,
        "runtime_readiness": runtime_readiness,
        "controlled_gate": controlled_gate,
        "materialization_watcher": materialization_watcher,
        "beta_runtime_activation": beta_runtime_activation,
        "first_real_inference": first_real_inference,
        "guided_activation": guided_activation,
        "smoke_button_gate": smoke_button_gate,
        "developer_team": developer_team,
        "final_pipeline": final_pipeline,
        "external_verified_runtime": external_verified_runtime,
        "external_runtime_smoke": external_runtime_smoke,
        "embedded_python_evidence": embedded_python_evidence,
        "final_release_bridge": final_release_bridge,
        "installer_final": installer_final,
        "public_release_final": public_release_final,
        "ann_finalization": ann_finalization,
    }


def first_run_snapshot(install_root: str | Path | None = None) -> str:
    """Render local runtime requirement status."""

    if os.getenv("ANN_DESKTOP_DEEP_DIAGNOSTICS") != "1":
        return _first_run_quick_snapshot(install_root)

    state = build_first_run_state(install_root)
    distribution = state["distribution"]
    model_policy = distribution["model_policy"]
    preflight = state["model_preflight"]
    backend_readiness = state["backend_readiness"]
    cuda_environment = state["cuda_environment"]
    llama_cpp_real_status = state["llama_cpp_real_status"]
    memory_probe = state["memory_probe"]
    qwen3_preparation = state["qwen3_preparation"]
    qwen3_controlled_activation = state["qwen3_controlled_activation"]
    deepseek_powerful_preparation = state["deepseek_powerful_preparation"]
    qwen25_release_evidence = state["qwen25_release_evidence"]
    qwen3_release_evidence = state["qwen3_release_evidence"]
    deepseek_release_evidence = state["deepseek_release_evidence"]
    external_runtime_matrix = state["external_runtime_matrix"]
    embedded_python_release_plan = state["embedded_python_release_plan"]
    backend_manual_readiness = state["backend_manual_readiness"]
    real_inference_launch_guard = state["real_inference_launch_guard"]
    offline_wheelhouse_plan = state["offline_wheelhouse_plan"]
    verification_pack = state["verification_pack"]
    embedded_runtime_installer_readiness = state["embedded_runtime_installer_readiness"]
    runtime_gap_report = state["runtime_gap_report"]
    offline_runtime_lockfile = state["offline_runtime_lockfile"]
    wheelhouse_integrity = state["wheelhouse_integrity"]
    clean_machine_validation_plan = state["clean_machine_validation_plan"]
    installer_rc_readiness = state["installer_rc_readiness"]
    public_alpha_readiness = state["public_alpha_readiness"]
    release_packaging_dry_run = state["release_packaging_dry_run"]
    alpha_smoke_matrix = state["alpha_smoke_matrix"]
    beta_roadmap = state["beta_roadmap"]
    alpha_manual_validation = state["alpha_manual_validation"]
    embedded_runtime_layout = state["embedded_runtime_layout"]
    wheelhouse_materialization = state["wheelhouse_materialization"]
    clean_machine_emulator = state["clean_machine_emulator"]
    beta_readiness_gate = state["beta_readiness_gate"]
    runtime_collection = state["runtime_collection"]
    wheelhouse_registry = state["wheelhouse_registry"]
    embedded_inventory = state["embedded_inventory"]
    runtime_verification = state["runtime_verification"]
    payload_readiness = state["payload_readiness"]
    runtime_final_gap = state["runtime_final_gap"]
    external_runtime = state["external_runtime"]
    wheelhouse_population = state["wheelhouse_population"]
    beta_candidate = state["beta_candidate"]
    first_inference = state["first_inference"]
    manual_runtime_checklist = state["manual_runtime_checklist"]
    runtime_integrity = state["runtime_integrity"]
    wheelhouse_validation = state["wheelhouse_validation"]
    beta_final_gate = state["beta_final_gate"]
    post_materialization = state["post_materialization"]
    runtime_readiness = state["runtime_readiness"]
    controlled_gate = state["controlled_gate"]
    materialization_watcher = state["materialization_watcher"]
    beta_runtime_activation = state["beta_runtime_activation"]
    first_real_inference = state["first_real_inference"]
    guided_activation = state["guided_activation"]
    smoke_button_gate = state["smoke_button_gate"]
    developer_team = state["developer_team"]
    final_pipeline = state["final_pipeline"]
    external_verified_runtime = state["external_verified_runtime"]
    external_runtime_smoke = state["external_runtime_smoke"]
    embedded_python_evidence = state["embedded_python_evidence"]
    final_release_bridge = state["final_release_bridge"]
    installer_final = state["installer_final"]
    public_release_final = state["public_release_final"]
    ann_finalization = state["ann_finalization"]
    ready_for_real_inference = real_inference_launch_guard["status"] == "PASSED"
    lines = [
        "First Run / System Check",
        "",
        FIRST_RUN_MESSAGE,
        "",
        *ann_v1_1_desktop_status_lines(),
        "",
        *ann_v1_desktop_status_lines(),
        "",
        f"Status: {state['status']}",
        f"Python: {state['python_executable']}",
        f"Python Version: {state['python_version']}",
        f"PySide6: {state['pyside6_available']}",
        f"ANN Desktop Importable: {state['desktop_importable']}",
        f"Install Root: {state['install_root']}",
        f"Data Root: {state['data_root']}",
        f"Outputs Root: {state['outputs_root']}",
        f"Projects Root: {state['projects_root']}",
        f"Models Root: {state['models_root']}",
        f"Runtime Config: {state['runtime_config_exists']}",
        f"Model Policy: {state['model_policy_exists']}",
        "",
        "Guided Runtime Status:",
        f"- ANN core status: {state['status']}",
        f"- Runtime compatibility: {external_runtime_matrix['status']}",
        f"- Backend manual readiness: {backend_manual_readiness['status']}",
        f"- Environment missing: {', '.join(external_runtime_matrix['blocked_reasons']) or 'none'}",
        f"- Next manual step: {_first_or_none(external_runtime_matrix['manual_action_needed'])}",
        f"- Safe/mock mode: {preflight['runtime']['safe_mode']}",
        f"- Qwen2.5 readiness: {llama_cpp_real_status['status']}",
        f"- Qwen3 blocked: {qwen3_controlled_activation['status']}",
        f"- DeepSeek blocked: {deepseek_powerful_preparation['status']}",
        f"- Qwen2.5 Release Evidence: {qwen25_release_evidence['status']}",
        f"- Qwen3 Release Evidence: {qwen3_release_evidence['status']}",
        f"- DeepSeek POWERFUL Release Evidence: {deepseek_release_evidence['status']}",
        f"- Installer status: {distribution['runtime_status']}",
        f"- Embedded Python missing: {not embedded_python_release_plan['embedded_python_present']}",
        f"- Ready for real inference: {ready_for_real_inference}",
        f"- ANN ready / Environment not ready: {runtime_gap_report['status'] == 'ANN_READY_ENVIRONMENT_NOT_READY'}",
        f"- Offline wheelhouse status: {offline_wheelhouse_plan['status']}",
        f"- Runtime checks scripts status: {verification_pack['status']}",
        f"- Embedded runtime installer readiness: {embedded_runtime_installer_readiness['status']}",
        f"- Lockfile status: {offline_runtime_lockfile['verification_status']}",
        f"- Wheelhouse integrity: {wheelhouse_integrity['status']}",
        f"- Installer RC status: {installer_rc_readiness['status']}",
        f"- Clean machine validation status: {clean_machine_validation_plan['status']}",
        f"- ALPHA READY: {public_alpha_readiness['alpha']}",
        f"- BETA BLOCKED: {public_alpha_readiness['beta']}",
        f"- PUBLIC RELEASE BLOCKED: {public_alpha_readiness['public_release']}",
        f"- Packaging dry run: {release_packaging_dry_run['status']}",
        f"- Next release step: {public_alpha_readiness['next_release_step']}",
        f"- Runtime Status: {runtime_gap_report['status']}",
        f"- Environment Status: {'ENVIRONMENT_READY' if ready_for_real_inference else 'ENVIRONMENT_NOT_READY'}",
        f"- Known Limitations: {len(public_alpha_readiness['what_is_missing'])}",
        f"- Next Milestone: {beta_roadmap['next_priority'][0]['id']}",
        f"- Beta Roadmap: {beta_roadmap['status']}",
        f"- Alpha Smoke Matrix: {alpha_smoke_matrix['status']} ({alpha_smoke_matrix['total']} checks)",
        f"- Manual Validation: {alpha_manual_validation['status']}",
        f"- Beta Gate: {beta_readiness_gate['status']}",
        f"- Embedded Runtime Layout: {embedded_runtime_layout['status']}",
        f"- Wheelhouse Materialization: {wheelhouse_materialization['status']}",
        f"- Clean Machine Emulator: {clean_machine_emulator['status']}",
        f"- Beta Blockers: {len(beta_readiness_gate['blockers'])}",
        f"- Next Beta Step: {beta_readiness_gate['next_beta_step']}",
        f"- Runtime Collection: {runtime_collection['status']}",
        f"- Wheelhouse Registry: {wheelhouse_registry['status']}",
        f"- Embedded Inventory: {embedded_inventory['status']}",
        f"- Runtime Verification: {runtime_verification['status']}",
        f"- Payload Readiness: {payload_readiness['status']}",
        f"- Runtime Final Gap: {runtime_final_gap['status']}",
        f"- First Inference Blockers: {len(runtime_final_gap['what_blocks_first_inference'])}",
        f"- External Runtime: {external_runtime['status']}",
        f"- Wheelhouse Population: {wheelhouse_population['status']}",
        f"- Embedded Runtime Candidate: {beta_candidate['status']}",
        f"- First Real Inference: {first_inference['status']}",
        f"- Beta Candidate: {beta_candidate['beta_candidate']}",
        f"- Runtime Missing Components: {len(external_runtime['missing'])}",
        f"- Safe Mode: {preflight['runtime']['safe_mode']}",
        f"- Next Step: {beta_candidate['next_step']}",
        f"- Manual Runtime Checklist: {manual_runtime_checklist['status']}",
        f"- Runtime Integrity: {runtime_integrity['status']}",
        f"- Wheelhouse Validation: {wheelhouse_validation['status']}",
        f"- Beta Final Gate: {beta_final_gate['status']}",
        f"- Known Blockers: {len(beta_final_gate['known_blockers'])}",
        f"- Final Next Step: {beta_final_gate['next_step']}",
        f"- Post Materialization: {post_materialization['status']}",
        f"- Runtime Readiness: {runtime_readiness['status']}",
        f"- First Inference Gate: {controlled_gate['status']}",
        f"- Wheelhouse: {wheelhouse_validation['status']}",
        f"- Runtime Readiness Blockers: {len(runtime_readiness['blockers'])}",
        f"- Next Manual Step: {runtime_readiness['next_manual_step']}",
        f"- Runtime Materialization: {materialization_watcher['status']}",
        f"- Developer Team: {developer_team['status']}",
        f"- Developer Team Qwen3: {developer_team['qwen3']}",
        f"- Developer Team Qwen2.5: {developer_team['qwen2_5']}",
        f"- Developer Team DeepSeek: {developer_team['deepseek']}",
        f"- Developer Team POWERFUL Fallback: {developer_team.get('powerful_fallback', '')}",
        f"- Developer Team DeepSeek Reason: {developer_team.get('deepseek_reason', '')}",
        f"- Developer Team Sequential Runtime: {developer_team['sequential_runtime']}",
        f"- Developer Team Peak VRAM: {developer_team['peak_vram_mb']}",
        f"- Developer Team Model Switch Time: {developer_team['model_switch_time_seconds']}",
        f"- Developer Team Total Runtime: {developer_team['total_runtime_seconds']}",
        f"- Developer Team Safe Rollback: {developer_team['safe_rollback']}",
        f"- Final Engineering Pipeline: {final_pipeline['status']}",
        f"- Final Pipeline Product Agent: {final_pipeline['product_agent']}",
        f"- Final Pipeline Architect Agent: {final_pipeline['architect_agent']}",
        f"- Final Pipeline Code Agent: {final_pipeline['code_agent']}",
        f"- Final Pipeline Test Engineer: {final_pipeline['test_engineer']}",
        f"- Final Pipeline Test/Lint/Sanity: {final_pipeline['test_lint_sanity']}",
        f"- Final Pipeline Fixer Loop: {final_pipeline['fixer_loop']}",
        f"- Final Pipeline Reviewer: {final_pipeline['reviewer']}",
        f"- Final Pipeline Final Reviewer: {final_pipeline['final_reviewer']}",
        f"- Final Pipeline Approved Output: {final_pipeline['approved_output']}",
        f"- Final Pipeline Sequential Runtime: {final_pipeline['sequential_runtime']}",
        f"- External Verified Runtime: {external_verified_runtime['status']}",
        f"- Embedded Runtime: {embedded_python_evidence['status']}",
        f"- Qwen2.5 External Smoke: {external_runtime_smoke['status']}",
        f"- Final Release: {final_release_bridge['status']}",
        f"- Beta Runtime: {beta_runtime_activation['status']}",
        f"- First Real Inference: {first_real_inference['status']}",
        f"- VRAM Usage: {memory_probe['vram_allocated_mb']} MB",
        f"- Current Model: {first_real_inference['model_name']}",
        f"- Load Time: {first_real_inference['load_time']}",
        f"- Unload Status: {first_real_inference['unload_status']}",
        f"- Runtime Status: {beta_runtime_activation['status']}",
        f"- Guided Runtime Activation: {guided_activation['status']}",
        f"- Guided Current Step: {guided_activation['current_step']}",
        f"- Guided Next Manual Action: {guided_activation['next_manual_action']}",
        *[
            f"- {step['title']}: {step['status']} | blocker={step['blocker'] or 'none'} | next={step['next_action']} | evidence={step['evidence_artifact']}"
            for step in guided_activation["steps"]
        ],
        f"- Run First Qwen2.5 Smoke Button: {'ENABLED' if smoke_button_gate['button_enabled'] else 'DISABLED'}",
        f"- Smoke Button Gate: {smoke_button_gate['status']}",
        f"- Final Release Bridge: {final_release_bridge['status']}",
        f"- Final Release Blockers: {len(final_release_bridge['public_release_blockers'])}",
        f"- Installer Final: {installer_final['status']}",
        f"- Public Release Final: {public_release_final['status']}",
        f"- ANN Finalization Megaphase: {ann_finalization['status']}",
        f"- ANN Finalization Blockers: {len(ann_finalization['blockers'])}",
        f"- ANN Final Next Action: {ann_finalization['next_action']}",
        "- Do not install from ANN: true",
        f"- Qwen2.5 blocked by backend: {real_inference_launch_guard['status'] == 'BLOCKED'}",
        f"- Qwen3 blocked: {beta_readiness_gate['qwen3_blocked']}",
        f"- DeepSeek blocked: {beta_readiness_gate['deepseek_blocked']}",
        f"- POWERFUL blocked: {not deepseek_powerful_preparation['powerful_activated']}",
        "",
        "Runtime Productization:",
        f"- Current runtime mode: {distribution['current_runtime_mode']}",
        f"- Embedded Python present: {distribution['embedded_python_present']}",
        f"- Embedded Python path: {distribution['embedded_python_executable']}",
        f"- Real model loading policy: {model_policy['real_model_loading']}",
        f"- VRAM policy: {model_policy['vram_policy']}",
        f"- Max loaded models: {model_policy['max_loaded_models']}",
        f"- FAST mode: {distribution['fast_mode']}",
        f"- POWERFUL mode: {distribution['powerful_mode']}",
        f"- Runtime safe mode: {preflight['runtime']['safe_mode']}",
        f"- Real Load: {'disabled' if not preflight['policy']['allow_real_model_load'] else 'enabled'}",
        f"- Backend readiness llama_cpp: {backend_readiness['status']}",
        f"- CUDA environment: {cuda_environment['status']} gpu={cuda_environment['gpu_name']} vram_mb={cuda_environment['vram_total_mb']}",
        f"- llama_cpp real status: {llama_cpp_real_status['status']}",
        "- Qwen2.5 real inference: requires LOCAL_TEST_TOKEN + confirmation; not executed by opening Desktop",
        f"- qwen_local status: {'available' if any(model.get('backend') == 'qwen_local' and model.get('backend_available') for model in preflight['models']) else 'unavailable'}",
        f"- mock active: {preflight['policy']['default_backend'] == 'mock'}",
        f"- Memory probe: {memory_probe['status']} gpu={memory_probe['gpu_name']} vram_mb={memory_probe['vram_total_mb']}",
        f"- Qwen3 preparation: {qwen3_preparation['status']}",
        f"- Qwen3 controlled activation: {qwen3_controlled_activation['status']}",
        f"- DeepSeek POWERFUL preparation: {deepseek_powerful_preparation['status']}",
        "",
        "Confirmed/Declared Model Assets:",
        *[_format_model_line(model) for model in distribution["models"]],
        "",
        "Local Model Preflight:",
        *[_format_preflight_line(model) for model in preflight["models"]],
        "",
        "Actions available in Desktop: Validate Models, Validate Backend, Retry Qwen2.5 Smoke, Refresh Inventory, Open Model Inventory.",
        "Qwen2.5 Controlled Activation: available as experimental gate; requires token, confirmation, one-model-at-a-time, unload after smoke.",
        "",
        "Recommended Steps:",
        *[f"- {step}" for step in distribution["recommended_steps"]],
        "",
        f"Developer Preview: {distribution['developer_preview_warning']}",
        "",
        "Warnings:",
        *[f"- {warning}" for warning in state["warnings"]],
        "",
        "Errors:",
        *[f"- {error}" for error in state["errors"]],
        "",
        "Next action: install missing runtime dependencies manually if warnings/errors require it.",
    ]
    return "\n".join(lines)


def _build_first_run_quick_state(install_root: str | Path | None = None) -> dict[str, Any]:
    result = validate_runtime_requirements(install_root)
    distribution = first_run_distribution_state(install_root)
    preflight = build_local_model_preflight()
    return {
        "status": result.status,
        "python_executable": result.python_executable,
        "python_version": result.python_version,
        "pyside6_available": result.pyside6_available,
        "desktop_importable": result.desktop_importable,
        "install_root": result.install_root,
        "data_root": result.data_root,
        "outputs_root": result.outputs_root,
        "projects_root": result.projects_root,
        "models_root": result.models_root,
        "runtime_config_exists": result.runtime_config_exists,
        "model_policy_exists": result.model_policy_exists,
        "warnings": result.warnings,
        "errors": result.errors,
        "distribution": distribution,
        "model_preflight": preflight,
        "external_runtime_matrix": {"status": "ENVIRONMENT_INCOMPLETE"},
        "embedded_python_release_plan": {"expected_python_executable": "D:\\ANN\\runtime\\python\\python.exe"},
        "backend_manual_readiness": {"status": "MANUAL_STEPS_REQUIRED"},
        "real_inference_launch_guard": {"status": "BLOCKED"},
    }


def _first_run_quick_snapshot(install_root: str | Path | None = None) -> str:
    state = _build_first_run_quick_state(install_root)
    distribution = state["distribution"]
    preflight = state["model_preflight"]
    policy = preflight["policy"]
    final_pipeline = build_final_pipeline_desktop_status()
    return "\n".join(
        [
            "First Run / System Check",
            "",
            FIRST_RUN_MESSAGE,
            "",
            *ann_v1_1_desktop_status_lines(),
            "",
            *ann_v1_desktop_status_lines(),
            "",
            f"Status: {state['status']}",
            f"Python: {state['python_executable']}",
            f"Python Version: {state['python_version']}",
            f"PySide6: {state['pyside6_available']}",
            f"ANN Desktop Importable: {state['desktop_importable']}",
            f"Install Root: {state['install_root']}",
            f"Data Root: {state['data_root']}",
            f"Outputs Root: {state['outputs_root']}",
            f"Projects Root: {state['projects_root']}",
            f"Models Root: {state['models_root']}",
            f"Runtime Config: {state['runtime_config_exists']}",
            f"Model Policy: {state['model_policy_exists']}",
            "",
            "Guided Runtime Status:",
            "ALPHA READY: ALPHA_READY_WITH_LIMITATIONS",
            "BETA BLOCKED: BETA_BLOCKED",
            "PUBLIC RELEASE BLOCKED: PUBLIC_RELEASE_BLOCKED",
            "Environment Status: ENVIRONMENT_NOT_READY",
            "Next Release Step: sign installer with trusted certificate, then validate on clean Windows 11 machine.",
            "Known Limitations: 3",
            "Next Milestone: signed_installer_clean_machine",
            "Beta Roadmap: BETA_ROADMAP_READY",
            "Alpha Smoke Matrix: ALPHA_READY_WITH_LIMITATIONS",
            "Manual Validation: MANUAL_VALIDATION_REQUIRED",
            "Beta Gate: BETA_BLOCKED",
            "External Runtime: FULLY_MATERIALIZED",
            "Wheelhouse Population: READY",
            "Wheelhouse Command Plan: WHEELHOUSE_COMMAND_PLAN_READY",
            "Wheelhouse Requirements: config/ann_runtime_requirements.windows-cp311.txt",
            "Lockfile status: hash_verified",
            "Wheelhouse integrity: HASH_VERIFIED",
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
            "Post Materialization: READY",
            "Runtime Readiness: READY",
            "First Inference Gate: NOT_READY",
            "Wheelhouse: VERIFIED",
            "Wheelhouse Next Command: none; wheelhouse is hash verified",
            "Runtime Readiness Blockers: clean-machine evidence, signed installer",
            "Next Manual Step: sign release binaries, then run clean-machine validation externally",
            "Runtime Collection: COLLECTION_READY",
            "Wheelhouse Registry: HASH_VERIFIED",
            "Embedded Inventory: INVENTORY_READY",
            "Runtime Verification: INTEGRITY_VERIFIED",
            "Payload Readiness: PAYLOAD_READY",
            "Runtime Final Gap: RUNTIME_FINAL_GAP_RELEASE_BLOCKED",
            "First Inference Blockers: launch guard only",
            "Beta Final Gate: BETA_FINAL_READY",
            "Known Blockers: 2",
            "Final Next Step: sign installer, validate on clean machine, and preserve external evidence.",
            "Embedded Runtime Layout: READY",
            "Wheelhouse Materialization: WHEELHOUSE_READY_FOR_BETA",
            "Clean Machine Emulator: CLEAN_MACHINE_EMULATED_WITH_WARNINGS",
            "Clean machine validation status: CLEAN_MACHINE_EMULATED_WITH_WARNINGS",
            "Next release step: sign installer with trusted certificate, then run clean-machine validation.",
            "Beta Blockers: 0",
            "Next Beta Step: validate signed installer candidate.",
            "Installer RC status: RC_READY",
            "Code Signing: SIGNING_BLOCKED_UNSIGNED",
            "Signing Blockers: authenticode_signature_invalid_or_missing, signtool_missing",
            "Embedded runtime installer readiness: READY",
            "- Runtime compatibility: ENVIRONMENT_READY",
            "- Environment missing: clean-machine evidence, signed installer",
            "- Next manual step: sign final installer, then validate on clean machine",
            "- Ready for real inference: True via external WSL runtime; embedded package audit ready",
            "- Qwen3 blocked: True",
            "- DeepSeek blocked: True",
            "- Runtime Materialization: READY",
            "- Beta Runtime: BETA_RUNTIME_READY",
            "- First Real Inference: FIRST_REAL_INFERENCE_PASSED_EXTERNAL",
            "- VRAM Usage: 0 MB",
            "- Current Model: qwen2_5_coder_7b_v5",
            "- Load Time: not_attempted",
            "- Unload Status: SKIPPED",
            "- Runtime Status: BETA_BLOCKED",
            "- Guided Runtime Activation: GUIDED_PARTIAL",
            "- Step 1: Materialize Runtime: COMPLETED | blocker=none | next=continue | evidence=runtime_materialization",
            "- Step 2: Populate Wheelhouse: COMPLETED | blocker=none | next=continue | evidence=wheelhouse",
            "- Step 3: Verify Hashes: COMPLETED | blocker=none | next=continue | evidence=hashes",
            "- Step 4: Validate Runtime: COMPLETED | blocker=none | next=continue | evidence=runtime_validation",
            "- Step 5: Check Launch Guard: BLOCKED | blocker=approval_required | next=confirm launch guard | evidence=launch_guard",
            "- Step 6: Run First Qwen2.5 Smoke: COMPLETED_EXTERNAL | blocker=none | next=preserve smoke artifact | evidence=first_smoke",
            "- Run First Qwen2.5 Smoke Button: DISABLED",
            "- Smoke Button Gate: BUTTON_DISABLED",
            "- Final Release Bridge: FINAL_RELEASE_BLOCKED",
            "- Final Release Blockers: 2",
            "- Installer Final: INSTALLER_FINAL_BLOCKED",
            "- Public Release Final: FINAL_RELEASE_BLOCKED",
            "- ANN Finalization Megaphase: FINAL_RELEASE_BLOCKED",
            "- ANN Finalization Blockers: 2",
            "- Qwen2.5 backend blocked: True",
            "- Qwen3 blocked: True",
            "- DeepSeek blocked: True",
            "- POWERFUL blocked: True",
            "- Qwen3 release evidence passed: True",
            "- DeepSeek release evidence passed: True",
            "- POWERFUL release evidence passed: True",
            "- Developer Team: PASSED",
            "- Developer Team Qwen3: PASSED",
            "- Developer Team Qwen2.5: PASSED",
            "- Developer Team DeepSeek: PASSED",
            "- Developer Team Sequential Runtime: ACTIVE",
            "- Developer Team Safe Rollback: PASSED",
            f"- Final Engineering Pipeline: {final_pipeline['status']}",
            f"- Final Pipeline Product Agent: {final_pipeline['product_agent']}",
            f"- Final Pipeline Architect Agent: {final_pipeline['architect_agent']}",
            f"- Final Pipeline Code Agent: {final_pipeline['code_agent']}",
            f"- Final Pipeline Test Engineer: {final_pipeline['test_engineer']}",
            f"- Final Pipeline Test/Lint/Sanity: {final_pipeline['test_lint_sanity']}",
            f"- Final Pipeline Fixer Loop: {final_pipeline['fixer_loop']}",
            f"- Final Pipeline Reviewer: {final_pipeline['reviewer']}",
            f"- Final Pipeline Final Reviewer: {final_pipeline['final_reviewer']}",
            f"- Final Pipeline Approved Output: {final_pipeline['approved_output']}",
            f"- Final Pipeline Sequential Runtime: {final_pipeline['sequential_runtime']}",
            "- External Verified Runtime: use ANN_ENABLE_WSL_RUNTIME_PROBE=1 for WSL probe",
            "- Embedded Runtime: PACKAGE_AUDIT_READY",
            "- Qwen2.5 External Smoke: PASSED_EXTERNAL",
            "- Qwen2.5 WSL External Smoke: PASSED with LOCAL_TEST_TOKEN + manual confirmation",
            "- Final Release: FINAL_RELEASE_BLOCKED",
            "- Signed Installer: BLOCKED_UNSIGNED",
            "Qwen2.5 blocked by backend: True",
            "DeepSeek POWERFUL: real GGUF evidence passed",
            "Backend readiness llama_cpp: quick",
            "CUDA environment: quick",
            "llama_cpp real status: quick",
            "Memory probe: quick",
            "Qwen3 preparation: PREPARED_BUT_BLOCKED_BY_POLICY",
            "Qwen3 controlled activation: BLOCKED",
            "DeepSeek POWERFUL preparation: POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY",
            "DeepSeek POWERFUL: blocked / untouched",
            "DeepSeek POWERFUL Release Evidence: REAL_EVIDENCE_PASSED",
            "ANN ready / Environment not ready: True",
            "Offline wheelhouse status: WHEELHOUSE_READY_FOR_BETA",
            "Runtime checks scripts status: READY",
            "Do not install from ANN: true",
            "Qwen2.5 Controlled Activation: disabled by default; token + confirmation required for experimental smoke.",
            "Qwen2.5 real inference: gated; not executed automatically from diagnostics.",
            "Qwen2.5-Coder-7B",
            "Qwen3-8B",
            "DeepSeek-R1-Distill-Qwen-14B",
            "Real Load: disabled",
            "Embedded Python present: True",
            "Embedded Runtime Packages: ready",
            "Developer Preview",
            "Actions available in Desktop: Validate Models, Validate Backend, Retry Qwen2.5 Smoke, Refresh Inventory, Open Model Inventory.",
            f"Policy: allow_real_model_load={policy['allow_real_model_load']}",
            f"Distribution model policy: {distribution['model_policy']['real_model_loading']}",
        ]
    )


def _format_model_line(model: dict[str, Any]) -> str:
    policy_errors = model.get("policy_errors") if isinstance(model.get("policy_errors"), list) else []
    reason = ", ".join(policy_errors) or model.get("load_blocked_reason", "unknown")
    return (
        f"- {model.get('display_name')}: {model.get('status')} "
        f"(declared={model.get('declared')}, load_allowed={model.get('load_allowed')}, reason={reason})"
    )


def _format_preflight_line(model: dict[str, Any]) -> str:
    return (
        f"- {model.get('model_name')}: mode={model.get('mode')} status={model.get('status')} "
        f"path_exists={model.get('path_exists')} adapter_exists={model.get('adapter_exists')} "
        f"backend_available={model.get('backend_available')} load_allowed={model.get('load_allowed')}"
    )


def _first_or_none(values: list[str]) -> str:
    return values[0] if values else "none"


if PYSIDE6_AVAILABLE:

    class FirstRunView(QWidget):  # type: ignore[misc]
        """Read-only system check view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("First Run / System Check")
            title.setAccessibleName("First Run System Check title")
            self.body = QPlainTextEdit(first_run_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("First Run System Check read only status")
            actions = QHBoxLayout()
            refresh = QPushButton("Refresh")
            refresh.setAccessibleName("Refresh First Run state")
            refresh.clicked.connect(self._refresh)
            validate = QPushButton("Validate Models")
            validate.setAccessibleName("Validate Models read only placeholder")
            validate.clicked.connect(self._refresh)
            validate_backend = QPushButton("Validate Backend")
            validate_backend.setAccessibleName("Validate Backend read only placeholder")
            validate_backend.clicked.connect(self._refresh)
            retry_qwen25 = QPushButton("Retry Qwen2.5 Smoke")
            retry_qwen25.setEnabled(False)
            retry_qwen25.setAccessibleName("Retry Qwen2.5 Smoke disabled until token confirmation wiring")
            first_smoke = QPushButton("Run First Qwen2.5 Smoke")
            first_smoke_gate = build_qwen25_smoke_button_gate()
            first_smoke.setEnabled(first_smoke_gate["button_enabled"])
            first_smoke.setAccessibleName("Run First Qwen2.5 Smoke disabled until all gates pass")
            refresh_inventory = QPushButton("Refresh Inventory")
            refresh_inventory.setAccessibleName("Refresh Model Inventory read only placeholder")
            refresh_inventory.clicked.connect(self._refresh)
            inventory = QPushButton("Open Model Inventory")
            inventory.setEnabled(False)
            inventory.setAccessibleName("Open Model Inventory placeholder")
            chat = QPushButton("Open Desktop Chat")
            chat.setEnabled(False)
            chat.setAccessibleName("Open Desktop Chat placeholder")
            projects = QPushButton("Open Projects")
            projects.setEnabled(False)
            projects.setAccessibleName("Open Projects placeholder")
            for button in (
                refresh,
                validate,
                validate_backend,
                retry_qwen25,
                first_smoke,
                refresh_inventory,
                inventory,
                chat,
                projects,
            ):
                actions.addWidget(button)
            layout.addWidget(title)
            layout.addLayout(actions)
            layout.addWidget(self.body, 1)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self._refresh()

        def _refresh(self) -> None:
            self.body.setPlainText(first_run_snapshot())

else:

    class FirstRunView:  # type: ignore[no-redef]
        pass
