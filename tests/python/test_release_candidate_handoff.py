from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from scripts.runtime import prepare_release_candidate_bundle


def test_release_candidate_handoff_manifest_declares_safe_minimal_bundle() -> None:
    manifest = activation.build_release_candidate_handoff_manifest(materialize=False)
    relatives = {entry["relative_path"] for entry in manifest["files"]}

    assert manifest["status"] == "HANDOFF_READY"
    assert "installer/ANN_Setup.exe" in relatives
    assert "installer/ANN_Uninstall.exe" in relatives
    assert "installer/sign_release.ps1" in relatives
    assert "installer/validate_clean_machine.ps1" in relatives
    assert "scripts/runtime/verify_final_release.py" in relatives
    assert "scripts/runtime/verify_autonomous_capability.py" in relatives
    assert "scripts/runtime/plan_autonomous_capability_evidence.py" in relatives
    assert "scripts/runtime/run_autonomous_capability_scenarios.py" in relatives
    assert "scripts/runtime/verify_external_release_evidence.py" in relatives
    assert "scripts/runtime/verify_release_operator_environment.py" in relatives
    assert manifest["model_files_included"] is False
    assert manifest["training_files_included"] is False
    assert manifest["dataset_files_included"] is False
    assert manifest["adapter_files_included"] is False
    assert manifest["historical_outputs_included"] is False
    assert manifest["signing_required_after_handoff"] is True
    assert manifest["clean_machine_validation_required_after_signing"] is True
    assert manifest["external_evidence_marker_name"] == "clean_machine_external_validation.json"
    assert "release_machine_requirements" in manifest
    assert any("trusted" in item.lower() for item in manifest["release_machine_requirements"])
    assert "verify_external_release_evidence.py" in manifest["external_release_evidence_command"]
    assert "--signing-evidence installer\\release_signing_evidence.json" in manifest["external_release_evidence_command"]
    assert "verify_release_operator_environment.py" in manifest["release_operator_environment_command"]
    assert '--certificate-thumbprint "<CERT_THUMBPRINT>"' in manifest["release_operator_environment_command"]
    assert "--bundle-root ." in manifest["final_verifier_command"]
    assert "--clean-machine-marker" in manifest["final_verifier_command"]
    assert "--signing-evidence installer\\release_signing_evidence.json" in manifest["final_verifier_command"]
    assert '--certificate-thumbprint "<CERT_THUMBPRINT>"' in manifest["final_verifier_command"]
    assert "repo_root_final_verifier_command" in manifest
    assert "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF" in manifest["repo_root_final_verifier_command"]
    assert "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json" in manifest["repo_root_final_verifier_command"]
    assert "--signing-evidence installer\\release_signing_evidence.json" in manifest["repo_root_final_verifier_command"]
    assert '--certificate-thumbprint "<CERT_THUMBPRINT>"' in manifest["repo_root_final_verifier_command"]
    assert "-OutputPath installer\\release_signing_evidence.json" in manifest["sign_command"]
    assert "-TimestampUrl http://timestamp.digicert.com" in manifest["sign_command"]
    assert "-SigningEvidencePath installer\\release_signing_evidence.json" in manifest["clean_machine_command"]
    assert "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json" in manifest["clean_machine_command"]
    assert manifest["release_commands_are_templates"] is True
    assert manifest["release_command_placeholders_must_be_replaced"] is True
    assert manifest["release_command_thumbprint_placeholder"] == "<CERT_THUMBPRINT>"
    assert manifest["release_command_thumbprint_regex"] == "^[0-9A-Fa-f]{40}$"
    assert manifest["sign_release_blocks_placeholder"] is True
    assert all(entry["sha256"] for entry in manifest["files"])


def test_release_candidate_handoff_materializes_only_declared_files(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"

    manifest = activation.build_release_candidate_handoff_manifest(bundle, materialize=True)

    assert manifest["status"] == "HANDOFF_READY"
    assert (bundle / "release_candidate_handoff_manifest.json").is_file()
    assert (bundle / "README_HANDOFF.md").is_file()
    assert (bundle / "FINAL_RELEASE_EXTERNAL_STEPS.md").is_file()
    assert (bundle / "clean_machine_external_validation.template.json").is_file()
    assert (bundle / "RELEASE_TRANSFER_MANIFEST.json").is_file()
    assert (bundle / "RELEASE_TRANSFER_MANIFEST.sha256").is_file()
    assert (bundle / "RELEASE_TRANSFER_MANIFEST.file.sha256").is_file()
    assert (bundle / "installer" / "ANN_Setup.exe").is_file()
    assert (bundle / "scripts" / "runtime" / "verify_release_operator_environment.py").is_file()
    assert not (bundle / "models").exists()
    assert not (bundle / "training").exists()
    assert not (bundle / "outputs").exists()
    readme = (bundle / "README_HANDOFF.md").read_text(encoding="utf-8")
    assert "transfer manifest file SHA256" in readme
    assert "internal aggregate_sha256" in readme
    assert "RELEASE_TRANSFER_MANIFEST.file.sha256" in readme
    assert "Repo-root final verifier" in readme
    assert "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF" in readme
    external_steps = (bundle / "FINAL_RELEASE_EXTERNAL_STEPS.md").read_text(encoding="utf-8")
    assert "release_transfer_manifest_sha256" in external_steps
    assert "release_transfer_manifest_aggregate_sha256" in external_steps
    assert "canonical path-contract command" in external_steps
    assert "outputs/release_candidates/ANN_RC_HANDOFF" in external_steps
    payload = json.loads((bundle / "release_candidate_handoff_manifest.json").read_text(encoding="utf-8"))
    assert payload["model_files_included"] is False
    template = json.loads((bundle / "clean_machine_external_validation.template.json").read_text(encoding="utf-8"))
    assert template["status"] == "PASSED"
    assert template["environment_type"] == "clean_machine"
    assert template["require_signed_installer"] is True
    assert template["signing_evidence_sha256"] == "<sha256 of release_signing_evidence.json>"
    assert template["release_transfer_manifest_sha256"] == "<sha256 of RELEASE_TRANSFER_MANIFEST.json>"
    assert template["release_transfer_manifest_aggregate_sha256"] == "<aggregate_sha256 inside RELEASE_TRANSFER_MANIFEST.json>"
    template_check_ids = {item["id"] for item in template["checks"]}
    assert "signing_evidence_sha256_present" in template_check_ids
    assert "release_transfer_manifest_sha256_present" in template_check_ids
    assert "release_transfer_manifest_aggregate_sha256_present" in template_check_ids
    transfer = json.loads((bundle / "RELEASE_TRANSFER_MANIFEST.json").read_text(encoding="utf-8"))
    assert transfer["status"] == "TRANSFER_MANIFEST_READY"
    assert "release_command_contract" in transfer
    assert transfer["release_command_contract"]["version"] == "18.9.17"
    assert transfer["release_command_contract"]["repo_root_final_verifier_required"] is True
    assert "repo_root_final_verifier_command" in transfer["release_command_contract"]["command_sha256"]
    assert len(transfer["release_command_contract"]["command_sha256"]["repo_root_final_verifier_command"]) == 64
    assert transfer["no_absolute_paths_required"] is True
    assert transfer["aggregate_sha256"]
    assert "release_command_contract" in transfer["canonical_scope"]
    auxiliary_paths = {entry["relative_path"] for entry in transfer["auxiliary_files"]}
    assert auxiliary_paths == {
        "README_HANDOFF.md",
        "FINAL_RELEASE_EXTERNAL_STEPS.md",
        "clean_machine_external_validation.template.json",
    }
    assert transfer["auxiliary_file_count"] == 3
    assert all(entry["sha256"] for entry in transfer["auxiliary_files"])


def test_release_candidate_handoff_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_release_candidate_handoff_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "364_release_candidate_handoff_manifest.json",
        "365_release_candidate_handoff_manifest.md",
    }
    payload = json.loads((tmp_path / "364_release_candidate_handoff_manifest.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.16"


def test_prepare_release_candidate_bundle_check_only_does_not_copy(tmp_path: Path) -> None:
    bundle = tmp_path / "check_only_bundle"

    exit_code = prepare_release_candidate_bundle.main(["--bundle-root", str(bundle), "--check-only"])

    assert exit_code == 0
    assert not bundle.exists()


def test_prepare_release_candidate_bundle_materializes(tmp_path: Path) -> None:
    bundle = tmp_path / "materialized_bundle"

    exit_code = prepare_release_candidate_bundle.main(["--bundle-root", str(bundle)])

    assert exit_code == 0
    assert (bundle / "release_candidate_handoff_manifest.json").is_file()
    assert (bundle / "installer" / "validate_clean_machine.ps1").is_file()
