from __future__ import annotations

import json
import hashlib
from pathlib import Path

from scripts.runtime import verify_external_release_evidence


VALID_THUMBPRINT = "A" * 40


def _thumbprint_hash(value: str = VALID_THUMBPRINT) -> str:
    return hashlib.sha256("".join(value.split()).upper().encode("utf-8")).hexdigest()


def _timestamp_policy() -> dict[str, object]:
    return {
        "timestamp_url": "http://timestamp.digicert.com",
        "planned_commands": [
            {
                "target": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                "command": [
                    "signtool.exe",
                    "sign",
                    "/sha1",
                    VALID_THUMBPRINT,
                    "/fd",
                    "SHA256",
                    "/tr",
                    "http://timestamp.digicert.com",
                    "/td",
                    "SHA256",
                    "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                ]
            },
            {
                "target": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                "command": [
                    "signtool.exe",
                    "sign",
                    "/sha1",
                    VALID_THUMBPRINT,
                    "/fd",
                    "SHA256",
                    "/tr",
                    "http://timestamp.digicert.com",
                    "/td",
                    "SHA256",
                    "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                ]
            },
        ],
    }


def _certificate_preflight() -> dict[str, object]:
    return {
        "certificate_preflight_required_for_execute": True,
        "certificate_evidence": {
            "found": True,
            "thumbprint_sha256": _thumbprint_hash(),
            "subject": "CN=ANN Release",
            "not_self_signed": True,
            "not_expired": True,
            "has_private_key": True,
            "code_signing_eku": True,
        },
    }


def _release_command_contract() -> dict[str, object]:
    return {
        "version": "18.9.17",
        "commands_are_templates": True,
        "placeholder_must_be_replaced": True,
        "thumbprint_placeholder": "<CERT_THUMBPRINT>",
        "thumbprint_regex": "^[0-9A-Fa-f]{40}$",
        "repo_root_final_verifier_required": True,
        "command_sha256": {
            "bundle_verifier_command": "1" * 64,
            "release_operator_environment_command": "2" * 64,
            "sign_command": "3" * 64,
            "clean_machine_command": "4" * 64,
            "external_release_evidence_command": "5" * 64,
            "final_verifier_command": "6" * 64,
            "repo_root_final_verifier_command": "7" * 64,
        },
    }


def _signing_safety_policy() -> dict[str, object]:
    return {
        "no_download": True,
        "no_install": True,
        "no_shell": True,
        "no_self_signed_certificate": True,
    }


def _patch_external_evidence(monkeypatch, *, ready: bool) -> None:
    setup_hash = "a" * 64
    uninstall_hash = "b" * 64
    signing_evidence_hash = "e" * 64
    transfer_manifest_file_hash = "f" * 64
    transfer_manifest_aggregate_hash = "9" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED" if ready else "HANDOFF_VERIFICATION_FAILED",
            "transfer_manifest": {
                "aggregate_sha256": transfer_manifest_aggregate_hash,
                "release_command_contract": _release_command_contract() if ready else {},
            },
            "transfer_manifest_file_sha256": transfer_manifest_file_hash,
            "installer_hashes": {
                "ANN_Setup.exe": setup_hash if ready else "",
                "ANN_Uninstall.exe": uninstall_hash if ready else "",
            },
        },
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_code_signing_readiness",
        lambda _installer_root: {
            "status": "SIGNING_READY" if ready else "SIGNING_BLOCKED_UNSIGNED",
            "signed_installer": ready,
            "binary_sha256": {
                "ANN_Setup.exe": setup_hash,
                "ANN_Uninstall.exe": uninstall_hash,
            },
        },
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED" if ready else "LOCAL_INSTALL_SMOKE_PASSED",
            "external_marker_path": str(external_marker_path or ""),
            "sufficient_for_final_release": ready,
            "external_installer_hashes": {
                "ANN_Setup.exe": setup_hash if ready else "",
                "ANN_Uninstall.exe": uninstall_hash if ready else "",
            },
            "external_validation_payload": {
                "setup_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash() if ready else "",
                },
                "uninstall_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash() if ready else "",
                },
                "signing_evidence_sha256": signing_evidence_hash if ready else "",
                "release_transfer_manifest_sha256": transfer_manifest_file_hash if ready else "",
                "release_transfer_manifest_aggregate_sha256": transfer_manifest_aggregate_hash if ready else "",
            },
            "external_validation": {
                "status": "EXTERNAL_VALIDATION_ACCEPTED" if ready else "EXTERNAL_VALIDATION_REJECTED"
            },
        },
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_sha256_file",
        lambda _path: signing_evidence_hash,
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": ready,
            **(_signing_safety_policy() if ready else {}),
            **_timestamp_policy(),
            **(_certificate_preflight() if ready else {}),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": setup_hash,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": uninstall_hash,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid" if ready else "NotSigned",
                    "signer": "CN=ANN Release" if ready else "",
                    "signer_thumbprint_sha256": _thumbprint_hash() if ready else "",
                    "timestamp_signer": "CN=Timestamp" if ready else "",
                    "sha256": setup_hash,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid" if ready else "NotSigned",
                    "signer": "CN=ANN Release" if ready else "",
                    "signer_thumbprint_sha256": _thumbprint_hash() if ready else "",
                    "timestamp_signer": "CN=Timestamp" if ready else "",
                    "sha256": uninstall_hash,
                },
            ],
        },
    )


def test_external_release_evidence_blocks_without_external_proof(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=False)

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["exit_code"] == 2
    assert {blocker["id"] for blocker in report["blockers"]} == {
        "handoff_bundle",
        "handoff_installer_hash_match",
        "signed_installer",
        "release_signing_evidence",
        "clean_machine_signing_evidence_hash_match",
        "clean_machine_transfer_manifest_hash_match",
        "clean_machine_transfer_manifest_aggregate_hash_match",
        "release_command_contract",
        "external_clean_machine",
        "external_marker_strong",
        "clean_machine_installer_hash_match",
        "clean_machine_signer_thumbprint_match",
    }
    assert report["no_model_load"] is True
    assert report["no_inference"] is True
    assert report["no_signing"] is True


def test_external_release_evidence_ready_when_all_external_checks_pass(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_READY"
    assert report["exit_code"] == 0
    assert report["blockers"] == []
    assert report["release_command_contract_ready"] is True
    assert report["release_command_contract"]["version"] == "18.9.17"


def test_external_release_evidence_blocks_missing_release_command_contract(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED",
            "transfer_manifest": {"aggregate_sha256": "9" * 64},
            "transfer_manifest_file_sha256": "f" * 64,
            "installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()
    checks = {check["id"]: check["detail"] for check in report["checks"]}

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "release_command_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_command_contract_ready"] is False
    assert checks["release_command_contract"] == "release_command_contract_missing"


def test_external_release_evidence_blocks_invalid_release_command_contract(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    contract = _release_command_contract()
    contract["command_sha256"]["repo_root_final_verifier_command"] = "z" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED",
            "transfer_manifest": {
                "aggregate_sha256": "9" * 64,
                "release_command_contract": contract,
            },
            "transfer_manifest_file_sha256": "f" * 64,
            "installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()
    checks = {check["id"]: check["detail"] for check in report["checks"]}

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "release_command_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_command_contract_ready"] is False
    assert "command_sha256:repo_root_final_verifier_command" in checks["release_command_contract"]


def test_external_release_evidence_cli_returns_exit_code(monkeypatch, capsys) -> None:
    _patch_external_evidence(monkeypatch, ready=False)

    exit_code = verify_external_release_evidence.main([])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "EXTERNAL_RELEASE_EVIDENCE_BLOCKED" in output
    assert "signed_installer" in output
    assert "Handoff Installer Hash Match: BLOCKED" in output
    assert "Clean-Machine Installer Hash Match: BLOCKED" in output
    assert "Authenticode Timestamp: BLOCKED" in output
    assert "Release Signing Evidence: BLOCKED" in output
    assert "Release Command Contract: BLOCKED" in output


def test_external_release_evidence_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    exit_code = verify_external_release_evidence.main(["--output-dir", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads((tmp_path / "370_external_release_evidence_verification.json").read_text(encoding="utf-8"))
    assert payload["status"] == "EXTERNAL_RELEASE_EVIDENCE_READY"
    assert (tmp_path / "371_external_release_evidence_verification.md").is_file()
    markdown = (tmp_path / "371_external_release_evidence_verification.md").read_text(encoding="utf-8")
    assert "Handoff Installer Hash Match: `PASS`" in markdown
    assert "Clean-Machine Installer Hash Match: `PASS`" in markdown
    assert "Authenticode Timestamp: `PASS`" in markdown
    assert "Release Signing Evidence: `PASS`" in markdown
    assert "Clean-Machine Signing Evidence Hash Match: `PASS`" in markdown
    assert "Clean-Machine Transfer Manifest Hash Match: `PASS`" in markdown
    assert "Clean-Machine Transfer Manifest Aggregate Match: `PASS`" in markdown
    assert "Release Command Contract: `PASS`" in markdown


def test_external_release_evidence_accepts_explicit_clean_machine_marker(monkeypatch, tmp_path: Path) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text("{}", encoding="utf-8")

    report = verify_external_release_evidence.build_external_release_evidence_report(
        clean_machine_marker=marker,
    )

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_READY"
    assert report["clean_machine_marker"] == str(marker)
    assert report["clean_machine"]["external_marker_path"] == str(marker)


def test_external_release_evidence_blocks_hash_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "c" * 64,
                "ANN_Uninstall.exe": "d" * 64,
            },
            "external_validation_payload": {
                "setup_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                },
                "uninstall_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                },
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "clean_machine_installer_hash_match" in {blocker["id"] for blocker in report["blockers"]}
    assert report["installer_hashes_match_clean_machine"] is False


def test_external_release_evidence_blocks_handoff_installer_hash_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED",
            "transfer_manifest": {
                "aggregate_sha256": "9" * 64,
                "release_command_contract": _release_command_contract(),
            },
            "transfer_manifest_file_sha256": "f" * 64,
            "installer_hashes": {
                "ANN_Setup.exe": "c" * 64,
                "ANN_Uninstall.exe": "d" * 64,
            },
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "handoff_installer_hash_match" in {blocker["id"] for blocker in report["blockers"]}
    assert report["installer_hashes_match_handoff"] is False


def test_external_release_evidence_blocks_dry_run_signing_evidence(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": False,
            **_timestamp_policy(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "release_signing_evidence" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_signing_evidence_valid"] is False


def test_external_release_evidence_blocks_missing_timestamp_policy(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **_certificate_preflight(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "release_signing_evidence" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_signing_evidence_valid"] is False
    assert "timestamp_policy_missing" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_missing_signing_safety_policy(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence.pop("no_shell", None)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "safety_policy_failed:no_shell" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_duplicate_pre_sign_target(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["pre_sign_evidence"].append({**evidence["pre_sign_evidence"][0]})
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "pre_sign_evidence:duplicate_target:ANN_Setup.exe" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_duplicate_target_evidence(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["target_evidence"].append({**evidence["target_evidence"][0]})
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "target_evidence:duplicate_target:ANN_Setup.exe" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_missing_certificate_preflight(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **_timestamp_policy(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "certificate_preflight_required_missing" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_signer_certificate_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **_timestamp_policy(),
            **_certificate_preflight(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=Different Certificate",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:signer_mismatch" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_signer_thumbprint_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["target_evidence"][0]["signer_thumbprint_sha256"] = _thumbprint_hash("BEEF")
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:signer_thumbprint_mismatch" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_hex_certificate_thumbprint_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["certificate_evidence"]["thumbprint_sha256"] = "z" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "certificate_thumbprint_hash_missing" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_hex_target_signer_thumbprint_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["target_evidence"][0]["signer_thumbprint_sha256"] = "z" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:signer_thumbprint_mismatch" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_hex_pre_sign_sha256(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["pre_sign_evidence"][0]["sha256"] = "z" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:pre_sign_sha256_invalid" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_hex_target_sha256(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["target_evidence"][0]["sha256"] = "z" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:sha256_invalid" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_hex_current_binary_sha256(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_code_signing_readiness",
        lambda _installer_root: {
            "status": "SIGNING_READY",
            "signed_installer": True,
            "binary_sha256": {
                "ANN_Setup.exe": "z" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "ANN_Setup.exe:current_sha256_invalid" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_clean_machine_signer_thumbprint_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "setup_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash("BEEF"),
                },
                "uninstall_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                },
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["clean_machine_signer_thumbprint_match"] is False
    assert "clean_machine_signer_thumbprint_match" in {
        blocker["id"] for blocker in report["blockers"]
    }
    assert "ANN_Setup.exe:signer_thumbprint_sha256_mismatch" in report["checks"][-1]["detail"]


def test_external_release_evidence_blocks_missing_planned_command_target(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"] = policy["planned_commands"][:1]
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "missing_planned_command:ANN_Uninstall.exe" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_signtool_planned_command(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0]["command"][0] = "powershell.exe"
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "signtool_executable_required" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_sign_signtool_subcommand(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0]["command"][1] = "verify"
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "signtool_sign_subcommand_required" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_planned_command_target_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0] = {
        "target": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
        "command": [
            "signtool.exe",
            "sign",
            "/sha1",
            VALID_THUMBPRINT,
            "/fd",
            "SHA256",
            "/tr",
            "http://timestamp.digicert.com",
            "/td",
            "SHA256",
            "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
        ],
    }
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "unexpected_or_missing_target:ANN_Setup.exe!=ANN_Uninstall.exe" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_c_drive_target_evidence_path(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    evidence["target_evidence"][0]["path"] = "C:/Temp/ANN_Setup.exe"
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: evidence,
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "path_policy_failed" in report["checks"][3]["detail"]
    assert "target_evidence:ANN_Setup.exe:path_c_drive_blocked" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_traversal_in_planned_command_target(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0] = {
        "target": "D:/AgenticEngineeringNetwork/installer/../ANN_Setup.exe",
        "command": [
            "signtool.exe",
            "sign",
            "/sha1",
            VALID_THUMBPRINT,
            "/fd",
            "SHA256",
            "/tr",
            "http://timestamp.digicert.com",
            "/td",
            "SHA256",
            "D:/AgenticEngineeringNetwork/installer/../ANN_Setup.exe",
        ],
    }
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "path_traversal_blocked" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_planned_command_thumbprint_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0]["command"][3] = "B" * 40
    policy["planned_commands"][1]["command"][3] = "B" * 40
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "certificate_thumbprint_mismatch" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_invalid_planned_command_thumbprint(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][0]["command"][3] = "ABCD"
    policy["planned_commands"][1]["command"][3] = "ABCD"
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "certificate_thumbprint_flag_invalid" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_inconsistent_planned_thumbprints(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    evidence = verify_external_release_evidence._load_release_signing_evidence(Path("unused"))
    policy = _timestamp_policy()
    policy["planned_commands"][1]["command"][3] = "B" * 40
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            **evidence,
            **policy,
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "certificate_thumbprint_mismatch" in report["checks"][3]["detail"]
    assert "inconsistent_certificate_thumbprints" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_timestamp_url_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    policy = _timestamp_policy()
    policy["planned_commands"] = [
        {
            "target": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
            "command": [
                "signtool.exe",
                "sign",
                "/sha1",
                VALID_THUMBPRINT,
                "/fd",
                "SHA256",
                "/tr",
                "http://example.invalid",
                "/td",
                "SHA256",
                "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
            ],
        },
        {
            "target": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
            "command": [
                "signtool.exe",
                "sign",
                "/sha1",
                VALID_THUMBPRINT,
                "/fd",
                "SHA256",
                "/tr",
                "http://example.invalid",
                "/td",
                "SHA256",
                "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
            ],
        },
    ]
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **policy,
            **_certificate_preflight(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "timestamp_url_mismatch" in report["checks"][3]["detail"]


def test_external_release_evidence_blocks_non_sha256_timestamp_digest(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    policy = _timestamp_policy()
    policy["planned_commands"] = [
        {
            "target": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
            "command": [
                "signtool.exe",
                "sign",
                "/sha1",
                VALID_THUMBPRINT,
                "/fd",
                "SHA256",
                "/tr",
                "http://timestamp.digicert.com",
                "/td",
                "SHA1",
                "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
            ]
        },
        {
            "target": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
            "command": [
                "signtool.exe",
                "sign",
                "/sha1",
                VALID_THUMBPRINT,
                "/fd",
                "SHA256",
                "/tr",
                "http://timestamp.digicert.com",
                "/td",
                "SHA1",
                "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
            ]
        },
    ]
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **policy,
            **_certificate_preflight(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": "b" * 64,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "a" * 64,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": "b" * 64,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["release_signing_evidence_valid"] is False
    assert "timestamp_digest_not_sha256" in report["checks"][3]["detail"]


def test_release_signing_evidence_loader_accepts_utf8_bom(tmp_path: Path) -> None:
    evidence = tmp_path / "release_signing_evidence.json"
    evidence.write_text('{"execute": false}', encoding="utf-8-sig")

    payload = verify_external_release_evidence._load_release_signing_evidence(evidence)

    assert payload["execute"] is False
    assert payload["path"] == str(evidence)


def test_external_release_evidence_allows_signed_hash_to_differ_from_handoff(monkeypatch) -> None:
    setup_pre_hash = "a" * 64
    uninstall_pre_hash = "b" * 64
    setup_signed_hash = "c" * 64
    uninstall_signed_hash = "d" * 64
    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED",
            "transfer_manifest": {
                "aggregate_sha256": "9" * 64,
                "release_command_contract": _release_command_contract(),
            },
            "transfer_manifest_file_sha256": "f" * 64,
            "installer_hashes": {
                "ANN_Setup.exe": setup_pre_hash,
                "ANN_Uninstall.exe": uninstall_pre_hash,
            },
        },
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_code_signing_readiness",
        lambda _installer_root: {
            "status": "SIGNING_READY",
            "signed_installer": True,
            "binary_sha256": {
                "ANN_Setup.exe": setup_signed_hash,
                "ANN_Uninstall.exe": uninstall_signed_hash,
            },
        },
    )
    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": setup_signed_hash,
                "ANN_Uninstall.exe": uninstall_signed_hash,
            },
            "external_validation_payload": {
                "setup_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                },
                "uninstall_signature": {
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                },
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )
    monkeypatch.setattr(verify_external_release_evidence, "_sha256_file", lambda _path: "e" * 64)
    monkeypatch.setattr(
        verify_external_release_evidence,
        "_load_release_signing_evidence",
        lambda _path: {
            "execute": True,
            **_signing_safety_policy(),
            **_timestamp_policy(),
            **_certificate_preflight(),
            "pre_sign_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": setup_pre_hash,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "NotSigned",
                    "timestamp_signer": "",
                    "sha256": uninstall_pre_hash,
                },
            ],
            "target_evidence": [
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Setup.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": setup_signed_hash,
                },
                {
                    "path": "D:/AgenticEngineeringNetwork/installer/ANN_Uninstall.exe",
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": _thumbprint_hash(),
                    "timestamp_signer": "CN=Timestamp",
                    "sha256": uninstall_signed_hash,
                },
            ],
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_READY"
    assert report["installer_hashes_match_handoff"] is True
    assert report["release_signing_evidence_valid"] is True
    assert report["installer_hashes_match_clean_machine"] is True


def test_external_release_evidence_blocks_clean_machine_transfer_manifest_hash_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "0" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "clean_machine_transfer_manifest_hash_match" in {blocker["id"] for blocker in report["blockers"]}
    assert report["clean_machine_transfer_manifest_hash_match"] is False


def test_external_release_evidence_blocks_non_hex_clean_machine_transfer_manifest_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "setup_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "uninstall_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "z" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()
    checks = {check["id"]: check["detail"] for check in report["checks"]}

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["clean_machine_transfer_manifest_hash_match"] is False
    assert checks["clean_machine_transfer_manifest_hash_match"] == (
        "clean_machine_marker_invalid_release_transfer_manifest_sha256"
    )


def test_external_release_evidence_blocks_clean_machine_transfer_manifest_aggregate_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "0" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "clean_machine_transfer_manifest_aggregate_hash_match" in {
        blocker["id"] for blocker in report["blockers"]
    }
    assert report["clean_machine_transfer_manifest_aggregate_hash_match"] is False


def test_external_release_evidence_blocks_non_hex_clean_machine_signing_evidence_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "a" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "setup_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "uninstall_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "signing_evidence_sha256": "z" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()
    checks = {check["id"]: check["detail"] for check in report["checks"]}

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["clean_machine_signing_evidence_hash_match"] is False
    assert checks["clean_machine_signing_evidence_hash_match"] == (
        "clean_machine_marker_invalid_signing_evidence_sha256"
    )


def test_external_release_evidence_blocks_clean_machine_signing_evidence_hash_mismatch(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)
    monkeypatch.setattr(verify_external_release_evidence, "_sha256_file", lambda _path: "f" * 64)

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert "clean_machine_signing_evidence_hash_match" in {blocker["id"] for blocker in report["blockers"]}
    assert report["clean_machine_signing_evidence_hash_match"] is False


def test_external_release_evidence_blocks_non_hex_clean_machine_installer_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "build_clean_machine_evidence",
        lambda _install_root, *, external_marker_path=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED",
            "sufficient_for_final_release": True,
            "external_installer_hashes": {
                "ANN_Setup.exe": "z" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
            "external_validation_payload": {
                "setup_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "uninstall_signature": {"signer_thumbprint_sha256": _thumbprint_hash()},
                "signing_evidence_sha256": "e" * 64,
                "release_transfer_manifest_sha256": "f" * 64,
                "release_transfer_manifest_aggregate_sha256": "9" * 64,
            },
            "external_validation": {"status": "EXTERNAL_VALIDATION_ACCEPTED"},
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["installer_hashes_match_clean_machine"] is False
    assert "clean_machine_installer_hash_match" in {blocker["id"] for blocker in report["blockers"]}


def test_external_release_evidence_blocks_non_hex_handoff_installer_hash(monkeypatch) -> None:
    _patch_external_evidence(monkeypatch, ready=True)

    monkeypatch.setattr(
        verify_external_release_evidence,
        "verify_bundle",
        lambda _bundle_root: {
            "status": "HANDOFF_VERIFIED",
            "transfer_manifest": {
                "aggregate_sha256": "9" * 64,
                "release_command_contract": _release_command_contract(),
            },
            "transfer_manifest_file_sha256": "f" * 64,
            "installer_hashes": {
                "ANN_Setup.exe": "z" * 64,
                "ANN_Uninstall.exe": "b" * 64,
            },
        },
    )

    report = verify_external_release_evidence.build_external_release_evidence_report()

    assert report["status"] == "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    assert report["installer_hashes_match_handoff"] is False
    assert "handoff_installer_hash_match" in {blocker["id"] for blocker in report["blockers"]}
