from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_clean_machine_evidence,
    write_clean_machine_evidence_artifacts,
)


SETUP_SHA256 = "a" * 64
UNINSTALL_SHA256 = "b" * 64
SIGNING_EVIDENCE_SHA256 = "c" * 64
RELEASE_TRANSFER_MANIFEST_SHA256 = "d" * 64
RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256 = "f" * 64
MACHINE_FINGERPRINT_SHA256 = "e" * 64
SIGNER_THUMBPRINT_SHA256 = "1" * 64
REQUIRED_CLEAN_MACHINE_CHECKS = [
    "install_root_not_c",
    "install_manifest",
    "app_package",
    "desktop_entrypoint",
    "runtime_python",
    "runtime_wheelhouse",
    "runtime_config",
    "model_policy",
    "projects_root",
    "models_root",
    "outputs_root",
    "data_root",
    "protected_training_not_copied",
    "protected_models_not_copied_to_app",
    "protected_memory_not_copied",
    "protected_knowledge_not_copied",
    "machine_identity_present",
    "machine_fingerprint_present",
    "machine_windows11_present",
    "setup_signature_valid",
    "uninstall_signature_valid",
    "setup_timestamp_present",
    "uninstall_timestamp_present",
    "setup_signer_thumbprint_sha256_present",
    "uninstall_signer_thumbprint_sha256_present",
    "setup_sha256_present",
    "uninstall_sha256_present",
    "signing_evidence_path_required",
    "signing_evidence_sha256_present",
    "release_transfer_manifest_path_required",
    "release_transfer_manifest_sha256_present",
    "release_transfer_manifest_aggregate_sha256_present",
]


def _passed_clean_machine_checks() -> list[dict[str, object]]:
    return [
        {"id": identifier, "status": "PASS", "passed": True}
        for identifier in REQUIRED_CLEAN_MACHINE_CHECKS
    ]


def _machine_identity() -> dict[str, object]:
    return {
        "computer_name_sha256": "f" * 64,
        "machine_fingerprint_sha256": MACHINE_FINGERPRINT_SHA256,
        "os_version": "Microsoft Windows 11",
        "os_product_name": "Microsoft Windows 11 Pro",
        "powershell_version": "5.1.0",
    }


def test_clean_machine_evidence_reports_local_install_smoke_without_claiming_final_release() -> None:
    evidence = build_clean_machine_evidence()

    assert evidence["status"] == "LOCAL_INSTALL_SMOKE_PASSED"
    assert evidence["evidence_level"] == "LOCAL_INSTALL_SMOKE"
    assert evidence["local_install_smoke_passed"] is True
    assert evidence["external_clean_machine_passed"] is False
    assert evidence["sufficient_for_final_release"] is False
    assert evidence["blockers"] == []
    assert evidence["no_model_load"] is True
    assert evidence["no_inference"] is True
    assert evidence["no_download"] is True


def test_clean_machine_evidence_blocks_incomplete_install(tmp_path: Path) -> None:
    root = tmp_path / "ANN"
    root.mkdir()

    evidence = build_clean_machine_evidence(root)

    assert evidence["status"] == "CLEAN_MACHINE_EVIDENCE_INCOMPLETE"
    assert evidence["local_install_smoke_passed"] is False
    assert evidence["sufficient_for_final_release"] is False
    assert evidence["blockers"]


def test_clean_machine_evidence_rejects_weak_external_marker() -> None:
    root = Path("D:/ANN")
    marker = root / "clean_machine_external_validation.json"
    original = marker.read_text(encoding="utf-8") if marker.is_file() else None
    marker.write_text(
        json.dumps({"status": "PASSED", "environment_type": "clean_machine"}),
        encoding="utf-8",
    )
    try:
        evidence = build_clean_machine_evidence(root)
    finally:
        if original is None:
            marker.unlink(missing_ok=True)
        else:
            marker.write_text(original, encoding="utf-8")

    assert evidence["external_clean_machine_passed"] is False
    assert evidence["sufficient_for_final_release"] is False
    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "require_signed_installer",
        "setup_signature_valid",
        "uninstall_signature_valid",
        "setup_timestamp_present",
        "uninstall_timestamp_present",
        "setup_sha256_present",
        "uninstall_sha256_present",
        "signing_evidence_sha256_present",
        "release_transfer_manifest_sha256_present",
        "release_transfer_manifest_aggregate_sha256_present",
    }


def test_clean_machine_evidence_accepts_strong_external_marker() -> None:
    root = Path("D:/ANN")
    marker = root / "clean_machine_external_validation.json"
    original = marker.read_text(encoding="utf-8") if marker.is_file() else None
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )
    try:
        evidence = build_clean_machine_evidence(root)
    finally:
        if original is None:
            marker.unlink(missing_ok=True)
        else:
            marker.write_text(original, encoding="utf-8")

    assert evidence["local_install_smoke_passed"] is True
    assert evidence["external_clean_machine_passed"] is True
    assert evidence["sufficient_for_final_release"] is True
    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_ACCEPTED"


def test_clean_machine_evidence_rejects_marker_without_required_external_artifact_path_checks(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": [
                    item
                    for item in _passed_clean_machine_checks()
                    if item["id"]
                    not in {
                        "signing_evidence_path_required",
                        "release_transfer_manifest_path_required",
                    }
                ],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "signed_validation_checks_present",
    }
    assert "signing_evidence_path_required" in evidence["external_validation"]["blockers"][0]["detail"]
    assert "release_transfer_manifest_path_required" in evidence["external_validation"]["blockers"][0]["detail"]


def test_clean_machine_evidence_rejects_non_hex_sha256_values(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": "z" * 64,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert "setup_sha256_present" in {
        item["id"] for item in evidence["external_validation"]["blockers"]
    }


def test_clean_machine_evidence_rejects_non_windows11_external_marker(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    machine_identity = _machine_identity()
    machine_identity["os_version"] = "Microsoft Windows 10"
    machine_identity["os_product_name"] = "Microsoft Windows 10 Pro"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": machine_identity,
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert "machine_windows11_present" in {
        item["id"] for item in evidence["external_validation"]["blockers"]
    }


def test_clean_machine_evidence_rejects_signed_marker_without_hashes(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "checks": [
                    {"id": "setup_signature_valid", "status": "PASS", "passed": True},
                    {"id": "uninstall_signature_valid", "status": "PASS", "passed": True},
                ],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "setup_sha256_present",
        "uninstall_sha256_present",
        "signing_evidence_sha256_present",
        "release_transfer_manifest_sha256_present",
        "release_transfer_manifest_aggregate_sha256_present",
        "signed_validation_checks_present",
    }


def test_clean_machine_evidence_rejects_marker_missing_install_checks(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": [
                    {"id": "setup_signature_valid", "status": "PASS", "passed": True},
                    {"id": "uninstall_signature_valid", "status": "PASS", "passed": True},
                    {"id": "setup_sha256_present", "status": "PASS", "passed": True},
                    {"id": "uninstall_sha256_present", "status": "PASS", "passed": True},
                ],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert any(
        item["id"] == "signed_validation_checks_present"
        for item in evidence["external_validation"]["blockers"]
    )


def test_clean_machine_evidence_accepts_explicit_external_marker_path(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation_marker"] == str(marker.resolve())
    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_ACCEPTED"


def test_clean_machine_evidence_rejects_marker_without_machine_identity(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "D:\\ANN",
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": [
                    item
                    for item in _passed_clean_machine_checks()
                    if item["id"] not in {"machine_identity_present", "machine_fingerprint_present"}
                ],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "machine_identity_present",
        "machine_fingerprint_present",
        "machine_os_version_present",
        "machine_powershell_version_present",
        "signed_validation_checks_present",
    }


def test_clean_machine_evidence_rejects_marker_missing_install_root(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "install_root_present",
        "install_root_not_c",
        "install_root_matches_expected",
    }


def test_clean_machine_evidence_rejects_marker_for_different_install_root(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "E:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "install_root_matches_expected",
    }


def test_clean_machine_evidence_rejects_marker_for_c_drive_install_root(tmp_path: Path) -> None:
    marker = tmp_path / "clean_machine_external_validation.json"
    marker.write_text(
        json.dumps(
            {
                "status": "PASSED",
                "environment_type": "clean_machine",
                "require_signed_installer": True,
                "install_root": "C:\\ANN",
                "machine_identity": _machine_identity(),
                "setup_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "uninstall_signature": {
                    "status": "Valid",
                    "signer": "CN=ANN Release",
                    "signer_thumbprint_sha256": SIGNER_THUMBPRINT_SHA256,
                    "timestamp_signer": "CN=Timestamp",
                },
                "setup_sha256": SETUP_SHA256,
                "uninstall_sha256": UNINSTALL_SHA256,
                "signing_evidence_sha256": SIGNING_EVIDENCE_SHA256,
                "release_transfer_manifest_sha256": RELEASE_TRANSFER_MANIFEST_SHA256,
                "release_transfer_manifest_aggregate_sha256": RELEASE_TRANSFER_MANIFEST_AGGREGATE_SHA256,
                "checks": _passed_clean_machine_checks(),
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_clean_machine_evidence("D:/ANN", external_marker_path=marker)

    assert evidence["external_validation"]["status"] == "EXTERNAL_VALIDATION_REJECTED"
    assert {item["id"] for item in evidence["external_validation"]["blockers"]} >= {
        "install_root_not_c",
        "install_root_matches_expected",
    }


def test_clean_machine_evidence_artifacts(tmp_path: Path) -> None:
    artifacts = write_clean_machine_evidence_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "358_clean_machine_evidence.json",
        "359_clean_machine_evidence.md",
    }
    payload = json.loads((tmp_path / "358_clean_machine_evidence.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.8"


