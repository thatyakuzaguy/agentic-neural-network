from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from scripts.runtime import verify_final_release


VALID_THUMBPRINT = "A" * 40
DIFFERENT_THUMBPRINT = "B" * 40


def _external_safety() -> dict[str, bool]:
    return {
        "no_install": True,
        "no_download": True,
        "no_signing": True,
        "no_model_load": True,
        "no_inference": True,
    }


def _release_command_contract_ready() -> dict[str, bool]:
    return {"release_command_contract_ready": True}


def _release_command_contract_check() -> dict[str, str]:
    return {"id": "release_command_contract", "status": "PASS"}


def _operator_safety() -> dict[str, bool]:
    return {
        "no_signing": True,
        "no_install": True,
        "no_download": True,
        "no_model_load": True,
        "no_inference": True,
        "no_shell": True,
    }


def _signing_plan_safety() -> dict[str, bool]:
    return {
        "commands_are_templates": True,
        "placeholder_must_be_replaced": True,
        "sign_release_blocks_placeholder": True,
        "no_signing_performed": True,
        "no_download": True,
        "no_install": True,
        "no_self_signed_certificate": True,
    }


def _patch_release_dependencies(monkeypatch, *, ready: bool) -> None:
    monkeypatch.setattr(
        activation,
        "build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        activation,
        "validate_wheelhouse_integrity",
        lambda _root=None: {"status": "HASH_VERIFIED"},
    )
    monkeypatch.setattr(
        activation,
        "build_embedded_runtime_package_audit",
        lambda _root=None: {"status": "PACKAGE_AUDIT_READY"},
    )
    monkeypatch.setattr(
        activation,
        "build_installer_rc_readiness",
        lambda: {"status": "RC_READY"},
    )
    monkeypatch.setattr(
        activation,
        "build_clean_machine_evidence",
        lambda _root=None: {
            "status": "CLEAN_MACHINE_EXTERNAL_PASSED" if ready else "LOCAL_INSTALL_SMOKE_PASSED",
            "local_install_smoke_passed": True,
            "external_clean_machine_passed": ready,
            "sufficient_for_final_release": ready,
        },
    )
    monkeypatch.setattr(
        activation,
        "build_code_signing_readiness",
        lambda: {
            "status": "SIGNING_READY" if ready else "SIGNING_BLOCKED_UNSIGNED",
            "signed_installer": ready,
        },
    )
    monkeypatch.setattr(
        activation,
        "build_installer_final_readiness",
        lambda _root=None: {"status": "INSTALLER_FINAL_READY" if ready else "INSTALLER_FINAL_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_final_release_readiness_bridge",
        lambda _root=None: {"status": "FINAL_RELEASE_READY" if ready else "FINAL_RELEASE_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_public_release_bridge_final",
        lambda _root=None: {"status": "FINAL_RELEASE_READY" if ready else "FINAL_RELEASE_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_ann_finalization_megaphase",
        lambda _root=None: {"status": "FINAL_RELEASE_READY" if ready else "FINAL_RELEASE_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_autonomous_complex_capability_gate",
        lambda: {
            "status": "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED"
            if ready
            else "AUTONOMOUS_COMPLEX_CAPABILITY_BLOCKED",
            "passed": ready,
            "required_scenarios": 7,
            "passed_scenarios": 7 if ready else 0,
        },
    )


def test_final_release_verification_report_blocks_without_external_evidence(monkeypatch) -> None:
    _patch_release_dependencies(monkeypatch, ready=False)

    report = activation.build_final_release_verification_report()

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["exit_code"] == 2
    assert report["no_model_load"] is True
    assert report["no_inference"] is True
    assert report["no_downloads"] is True
    assert report["no_installs"] is True
    assert {blocker["id"] for blocker in report["blockers"]} >= {
        "autonomous_complex_capability",
        "external_clean_machine_evidence",
        "signed_installer",
    }


def test_final_release_verification_report_ready_when_all_gates_pass(monkeypatch) -> None:
    _patch_release_dependencies(monkeypatch, ready=True)

    report = activation.build_final_release_verification_report()

    assert report["status"] == "FINAL_RELEASE_READY"
    assert report["exit_code"] == 0
    assert report["blockers"] == []


def test_final_release_verification_artifacts(monkeypatch, tmp_path: Path) -> None:
    _patch_release_dependencies(monkeypatch, ready=False)

    artifacts = activation.write_final_release_verification_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "362_final_release_verification.json",
        "363_final_release_verification.md",
    }
    payload = json.loads((tmp_path / "362_final_release_verification.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.10"
    assert payload["status"] == "FINAL_RELEASE_BLOCKED"


def test_verify_final_release_cli_returns_report_exit_code(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_BLOCKED",
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": False,
            "release_signing_evidence_valid": False,
            "clean_machine_signing_evidence_hash_match": False,
            "clean_machine_transfer_manifest_hash_match": False,
            "clean_machine_transfer_manifest_aggregate_hash_match": False,
            "clean_machine_signer_thumbprint_match": False,
            "signing": {"status": "SIGNING_BLOCKED_UNSIGNED"},
            "clean_machine": {"status": "LOCAL_INSTALL_SMOKE_PASSED"},
            "blockers": [{"id": "signed_installer"}],
            "next_step": "sign installer",
        },
    )

    exit_code = verify_final_release.main([])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "Status: FINAL_RELEASE_BLOCKED" in output
    assert "signed_installer" in output
    assert "certificate_thumbprint_format" in output
    assert "External Release Evidence: EXTERNAL_RELEASE_EVIDENCE_BLOCKED" in output
    assert "External Handoff Hash Match: PASS" in output
    assert "External Clean-Machine Hash Match: BLOCKED" in output
    assert "External Release Signing Evidence: BLOCKED" in output
    assert "External Clean-Machine Signing Evidence Hash Match: BLOCKED" in output
    assert "External Clean-Machine Transfer Manifest Hash Match: BLOCKED" in output
    assert "External Clean-Machine Transfer Manifest Aggregate Match: BLOCKED" in output
    assert "External Release Command Contract: BLOCKED" in output
    assert "External Clean-Machine Signer Thumbprint Match: BLOCKED" in output
    assert "External Signing: SIGNING_BLOCKED_UNSIGNED" in output
    assert "Release Evidence Contract: BLOCKED" in output
    assert "Final Release Path Contract: PASS" in output
    assert "Release Signing Plan Safety: PASS" in output
    assert "External Evidence Safety: BLOCKED" in output
    assert "Operator Environment Safety: PASS" in output


def test_verify_final_release_cli_blocks_when_external_evidence_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_BLOCKED",
            "installer_hashes_match_handoff": False,
            "installer_hashes_match_clean_machine": False,
            "release_signing_evidence_valid": False,
            "clean_machine_signing_evidence_hash_match": False,
            "clean_machine_transfer_manifest_hash_match": False,
            "clean_machine_transfer_manifest_aggregate_hash_match": False,
            "clean_machine_signer_thumbprint_match": False,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "BLOCKED"},
                {"id": "release_signing_evidence", "status": "BLOCKED"},
                {"id": "external_clean_machine", "status": "BLOCKED"},
                {"id": "clean_machine_installer_hash_match", "status": "BLOCKED"},
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "LOCAL_INSTALL_SMOKE_PASSED"},
            "blockers": [{"id": "handoff_installer_hash_match"}],
            "next_step": "use exact handoff installers",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_BLOCKED",
            "blockers": [{"id": "signtool_available"}],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["exit_code"] == 2
    assert "external_release_evidence" in {blocker["id"] for blocker in report["blockers"]}
    assert report["next_step"] == "use exact handoff installers"
    assert report["release_operator_environment_status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "signtool_available" in {
        blocker["id"] for blocker in report["release_operator_environment_blockers"]
    }
    assert "verify_release_operator_environment.py" in report["release_operator_environment_command"]
    contract = report["release_operator_evidence_contract"]
    assert [item["id"] for item in contract] == [
        "release_candidate_handoff_bundle",
        "release_operator_environment",
        "trusted_authenticode_signatures",
        "release_signing_evidence",
        "operator_signing_thumbprint_lineage",
        "external_clean_machine_validation",
        "clean_machine_installer_hash_lineage",
        "clean_machine_signing_evidence_hash_lineage",
        "clean_machine_transfer_manifest_hash_lineage",
            "clean_machine_transfer_manifest_aggregate_lineage",
            "release_command_contract",
            "clean_machine_signer_thumbprint_lineage",
        ]
    assert contract[0]["status"] == "PASS"
    assert contract[1]["status"] == "BLOCKED"
    assert contract[1]["required_for_final_release"] is True
    assert contract[2]["status"] == "BLOCKED"
    assert "-Execute" in contract[2]["producer_command"]


def test_verify_final_release_cli_ready_requires_external_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_READY"
    assert report["exit_code"] == 0
    assert report["blockers"] == []
    assert report["release_operator_environment_status"] == "RELEASE_OPERATOR_ENV_READY"
    assert report["release_operator_signing_thumbprint_match"] is True
    assert report["release_evidence_contract_ready"] is True
    assert f'--certificate-thumbprint "{VALID_THUMBPRINT}"' in report["release_operator_environment_command"]
    assert f'--certificate-thumbprint "{VALID_THUMBPRINT}"' in report["release_operator_evidence_contract"][-1]["verifier_command"]
    required_items = [
        item for item in report["release_operator_evidence_contract"] if item["required_for_final_release"] is True
    ]
    assert all(item["status"] == "PASS" for item in required_items)


def test_verify_final_release_cli_blocks_inconsistent_external_transfer_hash_lineage(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": False,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signing_evidence_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_hash_match", "status": "BLOCKED"},
                {"id": "clean_machine_transfer_manifest_aggregate_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["release_evidence_contract_ready"] is False
    assert "release_evidence_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_evidence_contract_blocker_detail"] == "clean_machine_transfer_manifest_hash_lineage"
    transfer_lineage = [
        item
        for item in report["release_operator_evidence_contract"]
        if item["id"] == "clean_machine_transfer_manifest_hash_lineage"
    ][0]
    assert transfer_lineage["status"] == "BLOCKED"


def test_verify_final_release_cli_blocks_when_required_contract_item_is_not_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["release_evidence_contract_ready"] is False
    assert "release_evidence_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_evidence_contract_blocker_detail"] == "clean_machine_signer_thumbprint_lineage"
    assert report["next_step"] == "Resolve release evidence contract blockers before final release."


def test_verify_final_release_cli_blocks_placeholder_certificate_thumbprint(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [{"id": "handoff_bundle", "status": "PASS"}, _release_command_contract_check()],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_BLOCKED",
            "certificate_thumbprint_sha256": "",
            "blockers": [{"id": "certificate_thumbprint_format"}],
        },
    )

    report = verify_final_release.build_cli_final_release_report(
        certificate_thumbprint="<CERT_THUMBPRINT>",
    )

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert "certificate_thumbprint_format" in {blocker["id"] for blocker in report["blockers"]}
    assert report["certificate_thumbprint_format_detail"] == "thumbprint_placeholder_blocked"
    assert report["next_step"] == (
        "Pass the real 40-character hexadecimal SHA1 Authenticode certificate thumbprint to the final verifier."
    )


def test_verify_final_release_cli_blocks_when_operator_environment_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_BLOCKED",
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [{"id": "certificate_not_self_signed"}],
            "next_step": "Use a trusted Authenticode certificate.",
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["exit_code"] == 2
    assert "release_operator_environment" in {blocker["id"] for blocker in report["blockers"]}
    assert report["next_step"] == "Use a trusted Authenticode certificate."
    contract = report["release_operator_evidence_contract"]
    operator = [item for item in contract if item["id"] == "release_operator_environment"][0]
    assert operator["status"] == "BLOCKED"
    assert operator["required_for_final_release"] is True


def test_verify_final_release_cli_blocks_when_release_signing_plan_is_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signing_evidence_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_aggregate_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_signing_plan",
        lambda _installer_root="installer": {
            "status": "SIGNING_PLAN_BLOCKED",
            "commands": [],
            "blockers": ["signing_script_missing"],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["release_signing_plan_ready"] is False
    assert "release_signing_plan" in {blocker["id"] for blocker in report["blockers"]}
    assert report["next_step"] == "Restore the release signing plan before final release verification."


def test_verify_final_release_cli_blocks_ready_reports_without_safety_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signing_evidence_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_aggregate_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_signing_plan",
        lambda _installer_root="installer": {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    '-CertificateThumbprint "<CERT_THUMBPRINT>" '
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute"
                ),
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
                    "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
                    "-SigningEvidencePath installer\\release_signing_evidence.json "
                    "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
                ),
            ],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=VALID_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    blocker_ids = {blocker["id"] for blocker in report["blockers"]}
    assert "release_signing_plan_safety" in blocker_ids
    assert "external_release_evidence_safety" in blocker_ids
    assert "release_operator_environment_safety" in blocker_ids


def test_verify_final_release_cli_blocks_noncanonical_evidence_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signing_evidence_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_hash_match", "status": "PASS"},
                {"id": "clean_machine_transfer_manifest_aggregate_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_signing_plan",
        lambda _installer_root="installer": {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            **_signing_plan_safety(),
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    '-CertificateThumbprint "<CERT_THUMBPRINT>" '
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute"
                ),
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
                    "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
                    "-SigningEvidencePath installer\\release_signing_evidence.json "
                    "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
                ),
            ],
        },
    )

    report = verify_final_release.build_cli_final_release_report(
        certificate_thumbprint=VALID_THUMBPRINT,
        signing_evidence="D:/Temp/release_signing_evidence.json",
        clean_machine_marker="D:/Temp/clean_machine_external_validation.json",
    )

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["final_release_path_contract_ready"] is False
    assert "final_release_path_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["next_step"] == "Use the canonical final release evidence paths before verification."
    blocked = [
        item
        for item in report["final_release_path_contract"]
        if item["status"] == "BLOCKED"
    ]
    assert {item["id"] for item in blocked} == {"signing_evidence", "clean_machine_marker"}


def test_verify_final_release_cli_blocks_when_operator_and_signing_thumbprint_differ(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "blockers": [],
            "ann_finalization": "FINAL_RELEASE_READY",
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
                _release_command_contract_check(),
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(DIFFERENT_THUMBPRINT),
            "blockers": [],
        },
    )

    report = verify_final_release.build_cli_final_release_report(certificate_thumbprint=DIFFERENT_THUMBPRINT)

    assert report["status"] == "FINAL_RELEASE_BLOCKED"
    assert report["release_operator_signing_thumbprint_match"] is False
    assert report["release_operator_signing_thumbprint_match_detail"] == "thumbprint_sha256_mismatch"
    assert "release_operator_signing_thumbprint_match" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_evidence_contract_ready"] is False
    contract = report["release_operator_evidence_contract"]
    lineage = [item for item in contract if item["id"] == "operator_signing_thumbprint_lineage"][0]
    assert lineage["status"] == "BLOCKED"
    assert lineage["detail"] == "thumbprint_sha256_mismatch"
    assert report["next_step"] == "Run release signing and final verification with the same trusted certificate thumbprint."


def test_verify_final_release_cli_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        verify_final_release,
        "build_final_release_verification_report",
        lambda _root=None: {
            "status": "FINAL_RELEASE_READY",
            "exit_code": 0,
            "runtime_materialization": "READY",
            "wheelhouse_integrity": "HASH_VERIFIED",
            "embedded_package_audit": "PACKAGE_AUDIT_READY",
            "installer_rc": "RC_READY",
            "autonomous_complex_capability": "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED",
            "installer_final": "INSTALLER_FINAL_READY",
            "public_release": "FINAL_RELEASE_READY",
            "ann_finalization": "FINAL_RELEASE_READY",
            "signed_installer": True,
            "external_clean_machine_passed": True,
            "blockers": [],
            "next_step": "release",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_external_release_evidence_report",
        lambda **_kwargs: {
            "status": "EXTERNAL_RELEASE_EVIDENCE_READY",
            **_external_safety(),
            **_release_command_contract_ready(),
            "installer_hashes_match_handoff": True,
            "installer_hashes_match_clean_machine": True,
            "release_signing_evidence_valid": True,
            "clean_machine_signing_evidence_hash_match": True,
            "clean_machine_transfer_manifest_hash_match": True,
            "clean_machine_transfer_manifest_aggregate_hash_match": True,
            "clean_machine_signer_thumbprint_match": True,
            "checks": [
                {"id": "handoff_bundle", "status": "PASS"},
                {"id": "signed_installer", "status": "PASS"},
                {"id": "release_signing_evidence", "status": "PASS"},
                {"id": "external_clean_machine", "status": "PASS"},
                {"id": "clean_machine_installer_hash_match", "status": "PASS"},
                {"id": "clean_machine_signer_thumbprint_match", "status": "PASS"},
            ],
            "signing": {"status": "SIGNING_READY"},
            "clean_machine": {"status": "CLEAN_MACHINE_EXTERNAL_PASSED"},
            "release_signing_evidence": {
                "certificate_evidence": {
                    "thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
                },
            },
            "blockers": [],
            "next_step": "final",
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_operator_environment_report",
        lambda **_kwargs: {
            "status": "RELEASE_OPERATOR_ENV_READY",
            **_operator_safety(),
            "certificate_thumbprint_sha256": verify_final_release._thumbprint_sha256(VALID_THUMBPRINT),
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        verify_final_release,
        "build_release_signing_plan",
        lambda _installer_root="installer": {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            **_signing_plan_safety(),
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    '-CertificateThumbprint "<CERT_THUMBPRINT>" '
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute"
                ),
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
                    "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
                    "-SigningEvidencePath installer\\release_signing_evidence.json "
                    "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
                ),
            ],
        },
    )
    calls: list[Path] = []
    monkeypatch.setattr(
        verify_final_release,
        "write_final_release_verification_artifacts",
        lambda output_dir: calls.append(Path(output_dir)) or [],
    )
    signing_calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        verify_final_release,
        "write_release_signing_plan_artifacts",
        lambda output_dir, installer_root=None: signing_calls.append((Path(output_dir), str(installer_root))) or [],
    )
    external_calls: list[Path] = []
    monkeypatch.setattr(
        verify_final_release,
        "write_external_release_evidence_artifacts",
        lambda _report, output_dir: external_calls.append(Path(output_dir)) or [],
    )
    operator_calls: list[Path] = []
    monkeypatch.setattr(
        verify_final_release,
        "write_release_operator_environment_artifacts",
        lambda _report, output_dir: operator_calls.append(Path(output_dir)) or [],
    )

    exit_code = verify_final_release.main(
        [
            "--output-dir",
            str(tmp_path),
            "--certificate-thumbprint",
            VALID_THUMBPRINT,
            "--json",
        ]
    )

    assert exit_code == 0
    assert calls == [tmp_path]
    assert signing_calls == [(tmp_path, "installer")]
    assert external_calls == [tmp_path]
    assert operator_calls == [tmp_path]
    assert (tmp_path / "372_final_release_cli_verification.json").is_file()
    assert (tmp_path / "373_final_release_cli_verification.md").is_file()
    markdown = (tmp_path / "373_final_release_cli_verification.md").read_text(encoding="utf-8")
    assert "External Handoff Hash Match: `PASS`" in markdown
    assert "External Clean-Machine Hash Match: `PASS`" in markdown
    assert "External Release Signing Evidence: `PASS`" in markdown
    assert "External Clean-Machine Signing Evidence Hash Match: `PASS`" in markdown
    assert "External Clean-Machine Transfer Manifest Aggregate Match: `PASS`" in markdown
    assert "External Clean-Machine Transfer Manifest Hash Match: `PASS`" in markdown
    assert "External Clean-Machine Signer Thumbprint Match: `PASS`" in markdown
    assert "External Signing: `SIGNING_READY`" in markdown
    assert "Release Operator Environment: `RELEASE_OPERATOR_ENV_READY`" in markdown
    assert "Operator/Signing Thumbprint Match: `PASS`" in markdown
    assert "Release Evidence Contract: `PASS`" in markdown
    assert "Final Release Path Contract: `PASS`" in markdown
    assert "Release Signing Plan: `SIGNING_PLAN_READY_FOR_RELEASE_MACHINE`" in markdown
    assert "Release Signing Plan Safety: `PASS`" in markdown
    assert "External Evidence Safety: `PASS`" in markdown
    assert "Operator Environment Safety: `PASS`" in markdown
    assert "## Release Safety Invariants" in markdown
    assert "## Final Release Path Contract" in markdown
    assert "`signing_evidence` | `PASS` | `installer/release_signing_evidence.json`" in markdown
    assert "`clean_machine_marker` | `PASS` | `D:/ANN/clean_machine_external_validation.json`" in markdown
    assert "`release_signing_plan` | `PASS`" in markdown
    assert "`external_release_evidence` | `PASS`" in markdown
    assert "`release_operator_environment` | `PASS`" in markdown
    assert "`no_model_load`" in markdown
    assert "`no_inference`" in markdown
    assert "`no_shell`" in markdown
    assert "## Release Evidence Contract" in markdown
    assert "`release_candidate_handoff_bundle`" in markdown
    assert "`release_operator_environment`" in markdown
    assert "`operator_signing_thumbprint_lineage`" in markdown
    assert "`external_clean_machine_validation`" in markdown
    assert "`clean_machine_signer_thumbprint_lineage`" in markdown
    assert "-Execute" in markdown
    assert "verify_final_release.py" in markdown
    assert "verify_release_operator_environment.py" in markdown
    assert "UNAVAILABLE" not in markdown
    assert "sign_release.ps1" in markdown
    assert "validate_clean_machine.ps1" in markdown


