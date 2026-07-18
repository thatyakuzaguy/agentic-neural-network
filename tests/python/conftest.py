from __future__ import annotations

from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_RELEASE_MANIFEST = REPOSITORY_ROOT / "PUBLIC_RELEASE_MANIFEST.json"

# These tests verify machine-local release evidence that is intentionally not
# distributed: launcher binaries, wheelhouse/runtime payloads, model evidence,
# signing evidence, and historical release bundles. They continue to run in the
# development repository and are visibly skipped only in the clean public tree.
PRIVATE_RELEASE_EVIDENCE_TESTS = frozenset(
    {
        "tests/python/test_ann_finalization_megaphase.py::test_installer_and_public_release_final_remain_blocked_until_real_evidence",
        "tests/python/test_beta_readiness_gate.py::test_beta_readiness_gate_blocks_on_backend_and_first_inference_after_wheelhouse_ready",
        "tests/python/test_beta_runtime_payload_readiness.py::test_beta_runtime_payload_readiness_blocked_until_backend_and_first_inference",
        "tests/python/test_code_signing_readiness.py::test_code_signing_readiness_detects_real_launcher_binaries",
        "tests/python/test_embedded_runtime_beta_candidate.py::test_embedded_runtime_beta_candidate_ready_after_verified_runtime",
        "tests/python/test_embedded_runtime_verification.py::test_embedded_runtime_verification_ready_after_wheelhouse_materialization",
        "tests/python/test_final_release_verifier.py::test_verify_final_release_cli_blocks_when_external_evidence_fails",
        "tests/python/test_final_release_verifier.py::test_verify_final_release_cli_ready_requires_external_evidence",
        "tests/python/test_final_release_verifier.py::test_verify_final_release_cli_blocks_when_required_contract_item_is_not_pass",
        "tests/python/test_final_release_verifier.py::test_verify_final_release_cli_blocks_when_operator_environment_fails",
        "tests/python/test_final_release_verifier.py::test_verify_final_release_cli_blocks_when_operator_and_signing_thumbprint_differ",
        "tests/python/test_release_candidate_bundle_verifier.py::test_release_candidate_bundle_verifier_passes_on_materialized_bundle",
        "tests/python/test_release_candidate_bundle_verifier.py::test_release_candidate_bundle_verifier_accepts_copied_bundle_with_original_copied_paths",
        "tests/python/test_release_candidate_bundle_verifier.py::test_release_candidate_bundle_verifier_cli",
        "tests/python/test_release_candidate_handoff.py::test_release_candidate_handoff_manifest_declares_safe_minimal_bundle",
        "tests/python/test_release_candidate_handoff.py::test_release_candidate_handoff_materializes_only_declared_files",
        "tests/python/test_release_candidate_handoff.py::test_prepare_release_candidate_bundle_check_only_does_not_copy",
        "tests/python/test_release_candidate_handoff.py::test_prepare_release_candidate_bundle_materializes",
        "tests/python/test_release_model_evidence_runtime.py::test_qwen25_release_evidence_reads_real_inference_without_loading_model",
        "tests/python/test_release_model_evidence_runtime.py::test_qwen3_release_evidence_reads_real_inference_without_requiring_live_gate",
        "tests/python/test_release_model_evidence_runtime.py::test_deepseek_powerful_release_evidence_reads_real_gguf_review",
    }
)

# These contracts intentionally inspect the operator's embedded runtime,
# wheelhouse, model files, or private release notes at their canonical Windows
# locations. A source-only GitHub runner cannot satisfy them without fabricating
# release evidence, so they remain visible as explicit public-release skips.
MACHINE_LOCAL_CONTRACT_TESTS = frozenset(
    {
        "tests/python/test_alpha_release_notes.py::test_alpha_release_notes_cover_user_facing_topics",
        "tests/python/test_ann_faq.py::test_ann_faq_contains_required_questions",
        "tests/python/test_beta_candidate_final_gate.py::test_beta_candidate_final_gate_blocked_and_safe",
        "tests/python/test_clean_machine_evidence.py::test_clean_machine_evidence_reports_local_install_smoke_without_claiming_final_release",
        "tests/python/test_clean_machine_evidence.py::test_clean_machine_evidence_accepts_strong_external_marker",
        "tests/python/test_code_signing_readiness.py::test_installer_launchers_are_auditable_and_do_not_use_shell_execute",
        "tests/python/test_controlled_first_inference_gate.py::test_controlled_first_inference_gate_blocked_no_load_no_inference",
        "tests/python/test_final_release_readiness_bridge.py::test_final_release_readiness_bridge_blocked",
        "tests/python/test_first_real_inference_readiness.py::test_first_real_inference_readiness_not_ready_and_no_load",
        "tests/python/test_guided_runtime_activation_state.py::test_guided_runtime_activation_state_blocked_when_runtime_missing",
        "tests/python/test_manual_external_runtime_checklist.py::test_manual_external_runtime_checklist_verified_after_runtime_materialization",
        "tests/python/test_post_materialization_validator.py::test_post_materialization_validator_validated_after_hashes_and_runtime_ready",
        "tests/python/test_qwen25_activation_gate.py::test_qwen25_gate_blocks_without_token",
        "tests/python/test_qwen25_activation_gate.py::test_qwen25_gate_blocks_without_confirmation",
        "tests/python/test_qwen25_activation_gate.py::test_qwen25_gate_passes_only_for_confirmed_qwen25",
        "tests/python/test_qwen25_backend_smoke.py::test_qwen25_backend_unavailable_is_reported",
        "tests/python/test_qwen25_backend_smoke.py::test_qwen25_backend_success_path_unloads",
        "tests/python/test_qwen25_controlled_smoke.py::test_qwen25_smoke_blocks_without_token",
        "tests/python/test_qwen25_controlled_smoke.py::test_qwen25_smoke_blocks_without_confirmation",
        "tests/python/test_qwen25_controlled_smoke.py::test_qwen25_smoke_valid_token_attempts_only_qwen25",
        "tests/python/test_qwen25_retry_smoke.py::test_qwen25_retry_ready_backend_allows_smoke_and_unloads",
        "tests/python/test_qwen25_safe_rollback.py::test_qwen25_smoke_rolls_back_after_failed_generation",
        "tests/python/test_qwen25_safe_rollback.py::test_qwen25_smoke_blocks_if_model_already_active",
        "tests/python/test_qwen25_smoke_button_gate.py::test_smoke_button_disabled_on_backend_after_runtime_ready",
        "tests/python/test_qwen25_smoke_button_gate.py::test_smoke_button_ready_only_when_all_gates_pass",
        "tests/python/test_runtime_integrity_verification.py::test_runtime_integrity_verification_ready_after_wheelhouse_hashes_exist",
        "tests/python/test_runtime_materialization_watcher.py::test_runtime_materialization_watcher_reports_current_runtime_state",
        "tests/python/test_runtime_readiness_evidence.py::test_runtime_readiness_evidence_blocked",
        "tests/python/test_wheelhouse_external_validation.py::test_wheelhouse_external_validation_verified",
        "tests/python/test_wheelhouse_integrity_registry.py::test_wheelhouse_integrity_registry_reports_hash_verified",
        "tests/python/test_wheelhouse_materialization_plan.py::test_wheelhouse_materialization_plan_ready_after_wheels_and_hashes",
        "tests/python/test_wheelhouse_population_protocol.py::test_wheelhouse_population_protocol_verified",
    }
)

PUBLIC_RELEASE_SKIPS = PRIVATE_RELEASE_EVIDENCE_TESTS | MACHINE_LOCAL_CONTRACT_TESTS


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "private_release_evidence: requires machine-local artifacts excluded from the public repository",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if not PUBLIC_RELEASE_MANIFEST.is_file():
        return
    skip = pytest.mark.skip(
        reason="requires private machine-local release evidence excluded from public source"
    )
    for item in items:
        normalized_node_id = item.nodeid.replace("\\", "/")
        if normalized_node_id in PUBLIC_RELEASE_SKIPS:
            item.add_marker("private_release_evidence")
            item.add_marker(skip)
