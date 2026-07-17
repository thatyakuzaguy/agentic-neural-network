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
        if normalized_node_id in PRIVATE_RELEASE_EVIDENCE_TESTS:
            item.add_marker("private_release_evidence")
            item.add_marker(skip)
