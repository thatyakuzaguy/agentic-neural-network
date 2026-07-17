from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from scripts.runtime import verify_release_candidate_bundle


def test_release_candidate_bundle_verifier_passes_on_materialized_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFIED"
    assert result["exit_code"] == 0
    assert result["files_checked"] >= 13
    assert result["protected_hits"] == []
    assert result["transfer_manifest_status"] == "PASS"
    assert set(result["installer_hashes"]) == {"ANN_Setup.exe", "ANN_Uninstall.exe"}
    assert all(result["installer_hashes"].values())
    assert result["no_model_load"] is True
    assert result["no_inference"] is True
    assert result["no_signing"] is True


def test_release_candidate_bundle_verifier_blocks_tampered_file(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "installer" / "README_INSTALLER.md").write_text("tampered", encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert result["exit_code"] == 2
    assert any(check["id"] == "file:installer/README_INSTALLER.md" for check in result["blockers"])


def test_release_candidate_bundle_verifier_blocks_tampered_declared_file_size(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["size_bytes"] = int(manifest["files"][0]["size_bytes"]) + 1
    changed_path = manifest["files"][0]["relative_path"]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == f"file_size:{changed_path}"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_missing_auxiliary_release_files(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "README_HANDOFF.md").unlink()
    (bundle / "FINAL_RELEASE_EXTERNAL_STEPS.md").unlink()
    (bundle / "clean_machine_external_validation.template.json").unlink()

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "auxiliary_file:README_HANDOFF.md" in blocker_ids
    assert "auxiliary_file:FINAL_RELEASE_EXTERNAL_STEPS.md" in blocker_ids
    assert "auxiliary_file:clean_machine_external_validation.template.json" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_tampered_auxiliary_file(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "README_HANDOFF.md").write_text("tampered handoff docs", encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "auxiliary_hash:README_HANDOFF.md" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_missing_auxiliary_hash_declaration(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    removed = manifest["auxiliary_files"].pop()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "auxiliary_manifest_declares_required_hashes"
        and f"missing:{removed['relative_path']}" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_duplicate_manifest_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(dict(manifest["files"][0]))
    duplicate_path = manifest["files"][0]["relative_path"]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "manifest_relative_paths_unique"
        and duplicate_path in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_incomplete_handoff_state(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "HANDOFF_INCOMPLETE"
    manifest["materialized"] = False
    manifest["missing"] = ["installer/ANN_Setup.exe"]
    manifest["copied"] = manifest["copied"][:-1]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "handoff_manifest_status" in blocker_ids
    assert "handoff_manifest_materialized" in blocker_ids
    assert "handoff_manifest_missing_empty" in blocker_ids
    assert "handoff_manifest_copied_count_matches" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_copied_path_outside_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["copied"][0] = str(tmp_path / "outside" / "ANN_Setup.exe")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "handoff_manifest_copied_paths_match"
        and "not_a_declared_bundle_file" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_copied_path_mismatch_inside_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unexpected = bundle / "unexpected.txt"
    unexpected.write_text("unexpected", encoding="utf-8")
    manifest["copied"][0] = str(unexpected)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "handoff_manifest_copied_paths_match"
        and "unexpected.txt" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_accepts_copied_bundle_with_original_copied_paths(tmp_path: Path) -> None:
    source_bundle = tmp_path / "source" / "ANN_RC_HANDOFF"
    copied_bundle = tmp_path / "copied" / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(source_bundle, materialize=True)
    shutil.copytree(source_bundle, copied_bundle)

    result = verify_release_candidate_bundle.verify_bundle(copied_bundle)

    assert result["status"] == "HANDOFF_VERIFIED"
    assert result["blockers"] == []


def test_release_candidate_bundle_verifier_blocks_missing_required_file_even_if_manifests_match(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    required_path = "scripts/runtime/verify_final_release.py"
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    manifest["files"] = [
        entry for entry in manifest["files"]
        if entry["relative_path"] != required_path
    ]
    transfer["files"] = [
        entry for entry in transfer["files"]
        if entry["relative_path"] != required_path
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "required_handoff_files_present"
        and required_path in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_protected_dirs(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "models").mkdir()
    (bundle / "datasets").mkdir()
    (bundle / "adapters").mkdir()

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert "models" in result["protected_hits"]
    assert "datasets" in result["protected_hits"]
    assert "adapters" in result["protected_hits"]
    assert any(check["id"] == "protected_directories_absent" for check in result["blockers"])


def test_release_candidate_bundle_verifier_blocks_case_variant_protected_dirs(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "Models").mkdir()
    (bundle / "Training").mkdir()
    (bundle / "DATASETS").mkdir()
    (bundle / "Adapters").mkdir()

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert {"Models", "Training", "DATASETS", "Adapters"}.issubset(set(result["protected_hits"]))
    assert any(check["id"] == "protected_directories_absent" for check in result["blockers"])


def test_release_candidate_bundle_verifier_blocks_dataset_adapter_manifest_flags(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_files_included"] = True
    manifest["adapter_files_included"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "no_datasets_in_manifest" in blocker_ids
    assert "no_adapters_in_manifest" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_manifest_release_requirement_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["signing_required_after_handoff"] = False
    manifest["clean_machine_validation_required_after_signing"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "manifest_requires_authenticode_signing" in blocker_ids
    assert "manifest_requires_clean_machine_validation" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_manifest_safety_flag_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["no_model_load"] = False
    manifest["no_inference"] = False
    manifest["no_download"] = False
    manifest["no_install"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "manifest_no_model_load" in blocker_ids
    assert "manifest_no_inference" in blocker_ids
    assert "manifest_no_download" in blocker_ids
    assert "manifest_no_install" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_sign_command_policy_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sign_command"] = manifest["sign_command"].replace(" -Execute", "")
    manifest["sign_command"] = manifest["sign_command"].replace('"<CERT_THUMBPRINT>"', "<CERT_THUMBPRINT>")
    manifest["sign_command"] = manifest["sign_command"].replace(" -TimestampUrl http://timestamp.digicert.com", "")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "sign_command_requires_execute" in blocker_ids
    assert "sign_command_requires_thumbprint_placeholder" in blocker_ids
    assert "sign_command_requires_timestamp_url" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_clean_machine_command_policy_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["clean_machine_command"] = manifest["clean_machine_command"].replace(" -EnvironmentType clean_machine", "")
    manifest["clean_machine_command"] = manifest["clean_machine_command"].replace(" -RequireSignedInstaller", "")
    manifest["clean_machine_command"] = manifest["clean_machine_command"].replace(
        " -ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json",
        "",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "clean_machine_command_requires_clean_machine_environment" in blocker_ids
    assert "clean_machine_command_requires_signed_installer" in blocker_ids
    assert "clean_machine_command_links_transfer_manifest" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_release_template_policy_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["release_commands_are_templates"] = False
    manifest["release_command_placeholders_must_be_replaced"] = False
    manifest["release_command_thumbprint_placeholder"] = "CERT_THUMBPRINT"
    manifest["release_command_thumbprint_regex"] = ".*"
    manifest["sign_release_blocks_placeholder"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "release_commands_are_templates" in blocker_ids
    assert "release_command_placeholders_must_be_replaced" in blocker_ids
    assert "release_command_thumbprint_placeholder" in blocker_ids
    assert "release_command_thumbprint_regex" in blocker_ids
    assert "sign_release_blocks_placeholder" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_final_verifier_command_policy_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["final_verifier_command"] = manifest["final_verifier_command"].replace(
        " --signing-evidence installer\\release_signing_evidence.json",
        "",
    )
    manifest["release_operator_environment_command"] = manifest[
        "release_operator_environment_command"
    ].replace('"<CERT_THUMBPRINT>"', "<CERT_THUMBPRINT>")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "final_verifier_command_requires_signing_evidence" in blocker_ids
    assert "operator_command_requires_certificate_thumbprint" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_wrong_handoff_command_scripts(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sign_command"] = manifest["sign_command"].replace(
        "installer\\sign_release.ps1",
        "installer\\install_ann.ps1",
    )
    manifest["clean_machine_command"] = manifest["clean_machine_command"].replace(
        "installer\\validate_clean_machine.ps1",
        "installer\\verify_install.ps1",
    )
    manifest["final_verifier_command"] = manifest["final_verifier_command"].replace(
        "scripts/runtime/verify_final_release.py",
        "scripts/runtime/verify_autonomous_capability.py",
    )
    manifest["external_release_evidence_command"] = manifest[
        "external_release_evidence_command"
    ].replace(
        "scripts/runtime/verify_external_release_evidence.py",
        "scripts/runtime/verify_autonomous_capability.py",
    )
    manifest["release_operator_environment_command"] = manifest[
        "release_operator_environment_command"
    ].replace(
        "scripts/runtime/verify_release_operator_environment.py",
        "scripts/runtime/verify_autonomous_capability.py",
    )
    manifest["bundle_verifier_command"] = manifest["bundle_verifier_command"].replace(
        "scripts/runtime/verify_release_candidate_bundle.py",
        "scripts/runtime/verify_autonomous_capability.py",
    )
    manifest["repo_root_final_verifier_command"] = manifest["repo_root_final_verifier_command"].replace(
        "scripts/runtime/verify_final_release.py",
        "scripts/runtime/verify_autonomous_capability.py",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "sign_command_targets_sign_release_script" in blocker_ids
    assert "clean_machine_command_targets_clean_machine_validator" in blocker_ids
    assert "final_verifier_command_targets_final_verifier" in blocker_ids
    assert "external_evidence_command_targets_external_evidence_verifier" in blocker_ids
    assert "operator_command_targets_operator_environment_verifier" in blocker_ids
    assert "bundle_verifier_command_targets_bundle_verifier" in blocker_ids
    assert "repo_root_final_verifier_command_targets_final_verifier" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_wrong_repo_root_final_bundle_path(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["repo_root_final_verifier_command"] = manifest["repo_root_final_verifier_command"].replace(
        "outputs/release_candidates/ANN_RC_HANDOFF",
        "outputs/release_candidates/OTHER",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "repo_root_final_verifier_command_targets_handoff_bundle" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_handoff_command_shell_chaining(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sign_command"] = f"{manifest['sign_command']} ; Remove-Item -Recurse D:\\ANN"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "sign_command_shell_safety"
        and check["detail"] == "statement_separator_blocked"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_handoff_command_pipeline(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle_verifier_command"] = f"{manifest['bundle_verifier_command']} | Out-File proof.txt"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "bundle_verifier_command_shell_safety"
        and check["detail"] == "pipeline_blocked"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_download_or_install_commands(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["external_release_evidence_command"] += " Invoke-WebRequest https://example.invalid/payload"
    manifest["release_operator_environment_command"] += " pip install unsafe-package"
    manifest["bundle_verifier_command"] += " Start-Process powershell"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocked = {check["id"]: check["detail"] for check in result["blockers"]}
    assert blocked["external_release_evidence_command_shell_safety"] == "download_command_blocked"
    assert blocked["release_operator_environment_command_shell_safety"] == "dependency_install_blocked"
    assert blocked["bundle_verifier_command_shell_safety"] == "process_spawn_blocked"


def test_release_candidate_bundle_verifier_blocks_opaque_handoff_commands(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sign_command"] += " -EncodedCommand SQBFAFgA"
    manifest["clean_machine_command"] += " Invoke-Expression Write-Host"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocked = {check["id"]: check["detail"] for check in result["blockers"]}
    assert blocked["sign_command_shell_safety"] == "encoded_command_blocked"
    assert blocked["clean_machine_command_shell_safety"] == "opaque_execution_blocked"


def test_release_candidate_bundle_verifier_blocks_tampered_transfer_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer.write_text('{"status": "TRANSFER_MANIFEST_READY", "aggregate_sha256": "bad"}', encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert result["transfer_manifest_status"] == "BLOCKED"
    assert any(check["id"] == "transfer_manifest_matches_handoff" for check in result["blockers"])


def test_release_candidate_bundle_verifier_blocks_tampered_transfer_command_contract(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["release_command_contract"]["command_sha256"]["repo_root_final_verifier_command"] = "0" * 64
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "transfer_release_command_contract_matches" in blocker_ids
    assert "transfer_file_digest_file_matches" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_missing_transfer_file_digest_sidecar(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "RELEASE_TRANSFER_MANIFEST.file.sha256").unlink()

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "auxiliary_file:RELEASE_TRANSFER_MANIFEST.file.sha256" in blocker_ids
    assert "transfer_file_digest_file_present" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_tampered_transfer_file_digest_sidecar(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    (bundle / "RELEASE_TRANSFER_MANIFEST.file.sha256").write_text(
        f"{'0' * 64}  RELEASE_TRANSFER_MANIFEST.json\n",
        encoding="utf-8",
    )

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_file_digest_file_matches"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_manifest_path_traversal(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    manifest_path = bundle / "release_candidate_handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(
        {
            "relative_path": "../outside.txt",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "file_path_safe:../outside.txt"
        and check["detail"] == "parent_traversal_blocked"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_absolute_path(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["files"].append(
        {
            "relative_path": "C:/Windows/System32/drivers/etc/hosts",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }
    )
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_paths_safe"
        and "absolute_path_blocked" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_missing_file_entry(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    removed = transfer["files"].pop()
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_file_list_matches_handoff"
        and f"missing:{removed['relative_path']}" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_changed_file_hash(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["files"][0]["sha256"] = "0" * 64
    changed_path = transfer["files"][0]["relative_path"]
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_file_list_matches_handoff"
        and f"changed:{changed_path}" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_changed_auxiliary_hash(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["auxiliary_files"][0]["sha256"] = "0" * 64
    changed_path = transfer["auxiliary_files"][0]["relative_path"]
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_auxiliary_list_matches_handoff"
        and f"changed:{changed_path}" in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_duplicate_transfer_file_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["files"].append(dict(transfer["files"][0]))
    duplicate_path = transfer["files"][0]["relative_path"]
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_file_paths_unique"
        and duplicate_path in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_duplicate_transfer_auxiliary_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["auxiliary_files"].append(dict(transfer["auxiliary_files"][0]))
    duplicate_path = transfer["auxiliary_files"][0]["relative_path"]
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_manifest_auxiliary_paths_unique"
        and duplicate_path in check["detail"]
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_file_count_mismatch(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["file_count"] = int(transfer["file_count"]) + 1
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_file_count_matches"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_auxiliary_count_mismatch(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["auxiliary_file_count"] = int(transfer["auxiliary_file_count"]) + 1
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    assert any(
        check["id"] == "transfer_auxiliary_file_count_matches"
        for check in result["blockers"]
    )


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_safety_flag_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["no_models"] = False
    transfer["no_training"] = False
    transfer["no_datasets"] = False
    transfer["no_adapters"] = False
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "transfer_no_models" in blocker_ids
    assert "transfer_no_training" in blocker_ids
    assert "transfer_no_datasets" in blocker_ids
    assert "transfer_no_adapters" in blocker_ids


def test_release_candidate_bundle_verifier_blocks_transfer_manifest_release_requirement_downgrade(tmp_path: Path) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)
    transfer_path = bundle / "RELEASE_TRANSFER_MANIFEST.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    transfer["requires_trusted_authenticode_signing"] = False
    transfer["requires_external_clean_machine_validation"] = False
    transfer["no_model_load"] = False
    transfer["no_inference"] = False
    transfer["no_download"] = False
    transfer["no_install"] = False
    transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")

    result = verify_release_candidate_bundle.verify_bundle(bundle)

    assert result["status"] == "HANDOFF_VERIFICATION_FAILED"
    blocker_ids = {check["id"] for check in result["blockers"]}
    assert "transfer_requires_authenticode_signing" in blocker_ids
    assert "transfer_requires_clean_machine_validation" in blocker_ids
    assert "transfer_no_model_load" in blocker_ids
    assert "transfer_no_inference" in blocker_ids
    assert "transfer_no_download" in blocker_ids
    assert "transfer_no_install" in blocker_ids


def test_release_candidate_bundle_verifier_cli(tmp_path: Path, capsys) -> None:
    bundle = tmp_path / "ANN_RC_HANDOFF"
    activation.build_release_candidate_handoff_manifest(bundle, materialize=True)

    exit_code = verify_release_candidate_bundle.main(["--bundle-root", str(bundle)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "HANDOFF_VERIFIED" in output
    assert "Transfer Manifest: PASS" in output
