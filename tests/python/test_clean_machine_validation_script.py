from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path("D:/AgenticEngineeringNetwork")


def test_clean_machine_validation_script_exists_and_is_non_executing() -> None:
    script = REPO_ROOT / "installer" / "validate_clean_machine.ps1"
    source = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "No_model_load" not in source
    assert "no_model_load" in source
    assert "no_inference" in source
    assert "no_download" in source
    assert "no_training" in source
    assert "clean_machine_external_validation.json" in source
    assert 'ValidateSet("local_smoke", "clean_machine")' in source
    assert "Test-BlockedRoot" in source
    assert "C:\\ install roots are blocked by default." in source
    forbidden = ("pip install", "npm install", "Invoke-WebRequest", "curl ", "Start-BitsTransfer")
    assert not any(token in source for token in forbidden)


def test_clean_machine_validation_script_can_require_signed_installer() -> None:
    source = (REPO_ROOT / "installer" / "validate_clean_machine.ps1").read_text(encoding="utf-8")

    assert "$RequireSignedInstaller" in source
    assert "setup_signature_valid" in source
    assert "uninstall_signature_valid" in source
    assert "setup_timestamp_present" in source
    assert "uninstall_timestamp_present" in source
    assert "signer_thumbprint_sha256" in source
    assert "setup_signer_thumbprint_sha256_present" in source
    assert "uninstall_signer_thumbprint_sha256_present" in source
    assert "setup_sha256_present" in source
    assert "uninstall_sha256_present" in source
    assert "[string]$SigningEvidencePath" in source
    assert "signing_evidence_path_required" in source
    assert "signing_evidence_sha256" in source
    assert "signing_evidence_sha256_present" in source
    assert "[string]$ReleaseTransferManifestPath" in source
    assert "release_transfer_manifest_path_required" in source
    assert "release_transfer_manifest_sha256" in source
    assert "release_transfer_manifest_sha256_present" in source
    assert "release_transfer_manifest_aggregate_sha256" in source
    assert "release_transfer_manifest_aggregate_sha256_present" in source
    assert "Get-ReleaseTransferManifestAggregateSha256" in source
    assert "function Test-IsSha256" in source
    assert "^[0-9a-fA-F]{64}$" in source
    assert "Test-IsSha256 $setupSha256" in source
    assert "Test-IsSha256 $releaseTransferManifestAggregateSha256" in source
    assert "Get-MachineIdentityEvidence" in source
    assert "machine_identity" in source
    assert "machine_identity_present" in source
    assert "machine_fingerprint_present" in source
    assert "machine_fingerprint_sha256" in source
    assert "computer_name_sha256" in source
    assert "Get-FileHash -Algorithm SHA256" in source
    assert "Get-AuthenticodeSignature" in source


def test_release_signing_script_is_dry_run_by_default() -> None:
    script = REPO_ROOT / "installer" / "sign_release.ps1"
    source = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "[switch]$Execute" in source
    assert "[string]$OutputPath" in source
    assert "Dry run only" in source
    assert "release_signing_evidence.json" in source
    assert "Signing evidence written" in source
    assert "pre_sign_evidence" in source
    assert "target_evidence" in source
    assert "timestamp_signer" in source
    assert "signer_thumbprint_sha256" in source
    assert "no_shell" in source
    assert "TimestampUrl is required" in source
    assert '"/tr"' in source
    assert '"/td"' in source
    assert "Get-FileHash -Algorithm SHA256" in source
    assert "signtool.exe" in source
    assert "CertificateThumbprint is required" in source
    assert "no_self_signed_certificate" in source
    assert "Get-CodeSigningCertificateEvidence" in source
    assert "Assert-CodeSigningCertificateReady" in source
    assert "Assert-SignatureMatchesCertificate" in source
    assert "Signature thumbprint validation failed" in source
    assert "Signature thumbprint evidence missing" in source
    assert "Get-StringSha256" in source
    assert "certificate_evidence" in source
    assert "thumbprint_sha256" in source
    assert "CertificateThumbprint placeholder is not allowed" in source
    assert "40-character hexadecimal SHA1 thumbprint" in source
    assert "^[0-9A-F]{40}$" in source
    assert "certificate_preflight_required_for_execute" in source
    assert "Release signing refuses self-signed certificates" in source
    assert "Release signing refuses expired certificates" in source
    assert "Release signing requires the certificate private key" in source
    assert "Release signing requires Code Signing Enhanced Key Usage" in source
    assert "Get-AuthenticodeSignature" in source
    forbidden = ("pip install", "npm install", "Invoke-WebRequest", "curl ", "Start-BitsTransfer")
    assert not any(token in source for token in forbidden)


def test_installer_readme_documents_release_operator_preflight() -> None:
    source = (REPO_ROOT / "installer" / "README_INSTALLER.md").read_text(encoding="utf-8")

    assert "verify_release_operator_environment.py" in source
    assert "verify_final_release.py --install-root D:\\ANN --installer-root installer" in source
    assert "--bundle-root outputs\\release_candidates\\ANN_RC_HANDOFF" in source
    assert "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json" in source
    assert '--signing-evidence installer\\release_signing_evidence.json --certificate-thumbprint "<CERT_THUMBPRINT>"' in source
    assert "canonical final release path contract" in source
    assert '--certificate-thumbprint "<CERT_THUMBPRINT>"' in source
    assert "-TimestampUrl http://timestamp.digicert.com" in source
    assert "signtool.exe" in source
    assert "private key" in source
    assert "Code Signing Enhanced Key Usage" in source
    assert "release_transfer_manifest_sha256" in source
    assert "release_transfer_manifest_aggregate_sha256" in source
    assert "Final release verification requires both values" in source
    assert "RELEASE_TRANSFER_MANIFEST.file.sha256" in source
    assert "RELEASE_TRANSFER_MANIFEST.sha256" in source
    assert "All commands that show `<CERT_THUMBPRINT>` are templates" in source
    assert "refuses placeholders and malformed thumbprints" in source
