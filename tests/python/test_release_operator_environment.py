from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.runtime import verify_release_operator_environment as verifier


VALID_THUMBPRINT = "A" * 40


def _certificate_payload(
    *,
    issuer: str = "CN=Trusted CA",
    not_after_utc: str = "2030-01-01T00:00:00+00:00",
    has_private_key: bool = True,
    enhanced_key_usage: list[str] | None = None,
    enhanced_key_usage_oids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "Store": "Cert:\\CurrentUser\\My",
        "Subject": "CN=ANN Release",
        "Issuer": issuer,
        "NotAfterUtc": not_after_utc,
        "HasPrivateKey": has_private_key,
        "EnhancedKeyUsageList": enhanced_key_usage or ["Code Signing"],
        "EnhancedKeyUsageOidList": enhanced_key_usage_oids or ["1.3.6.1.5.5.7.3.3"],
        "Thumbprint": VALID_THUMBPRINT,
    }


def _patch_release_operator_dependencies(monkeypatch, tmp_path: Path, *, ready: bool) -> None:
    for name in ("ANN_Setup.exe", "ANN_Uninstall.exe", "sign_release.ps1"):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "build_code_signing_readiness",
        lambda _root, execute_signature_check=False: {
            "status": "SIGNING_READY_FOR_EXTERNAL_TOOLING" if ready else "SIGNING_BLOCKED_UNSIGNED",
            "missing_binaries": [],
            "powershell_detected": True,
            "powershell_path": "powershell.exe",
            "signtool_detected": ready,
            "signtool_path": "signtool.exe" if ready else "",
        },
    )
    monkeypatch.setattr(
        verifier,
        "build_release_signing_plan",
        lambda _root: {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    "-CertificateThumbprint <CERT_THUMBPRINT> "
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute"
                ),
            ],
        },
    )


def test_release_operator_environment_blocks_without_certificate_thumbprint(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)

    report = verifier.build_release_operator_environment_report(installer_root=tmp_path)

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert report["exit_code"] == 2
    assert "certificate_thumbprint_provided" in {blocker["id"] for blocker in report["blockers"]}
    assert report["no_signing"] is True
    assert report["no_install"] is True
    assert report["no_download"] is True
    assert report["no_model_load"] is True
    assert report["no_inference"] is True
    assert report["no_shell"] is True


def test_release_operator_environment_ready_with_trusted_certificate(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")
    calls: list[dict[str, object]] = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        payload = _certificate_payload()
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=" ".join([VALID_THUMBPRINT[:20], VALID_THUMBPRINT[20:]]),
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_READY"
    assert report["exit_code"] == 0
    assert report["blockers"] == []
    assert report["certificate_thumbprint"] == "AAAA...AAAA"
    assert report["certificate_thumbprint_sha256"] == verifier._thumbprint_sha256(VALID_THUMBPRINT)
    assert calls
    assert all(call["kwargs"].get("shell") is None for call in calls)
    assert calls[0]["kwargs"]["check"] is False


def test_release_operator_environment_blocks_self_signed_certificate(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")

    def fake_run(*args, **kwargs):
        payload = _certificate_payload(issuer="CN=ANN Release")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "certificate_not_self_signed" in {blocker["id"] for blocker in report["blockers"]}


def test_release_operator_environment_blocks_expired_certificate(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")

    def fake_run(*args, **kwargs):
        payload = _certificate_payload(not_after_utc="2020-01-01T00:00:00+00:00")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "certificate_not_expired" in {blocker["id"] for blocker in report["blockers"]}


def test_release_operator_environment_blocks_certificate_without_private_key(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")

    def fake_run(*args, **kwargs):
        payload = _certificate_payload(has_private_key=False)
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "certificate_has_private_key" in {blocker["id"] for blocker in report["blockers"]}


def test_release_operator_environment_blocks_certificate_without_code_signing_eku(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")

    def fake_run(*args, **kwargs):
        payload = _certificate_payload(
            enhanced_key_usage=["Client Authentication"],
            enhanced_key_usage_oids=["1.3.6.1.5.5.7.3.2"],
        )
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "certificate_code_signing_eku" in {blocker["id"] for blocker in report["blockers"]}


def test_release_operator_environment_blocks_missing_timestamp_url_in_signing_plan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(
        verifier,
        "build_release_signing_plan",
        lambda _root: {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    "-CertificateThumbprint <CERT_THUMBPRINT> "
                    "-OutputPath installer\\release_signing_evidence.json -Execute"
                ),
            ],
        },
    )

    def fake_run(*args, **kwargs):
        payload = _certificate_payload()
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "timestamp_url_configured" in {blocker["id"] for blocker in report["blockers"]}


def test_release_operator_environment_blocks_unsafe_signing_plan_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(
        verifier,
        "build_release_signing_plan",
        lambda _root: {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    "-CertificateThumbprint <CERT_THUMBPRINT> "
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute "
                    "Invoke-WebRequest https://example.invalid/payload"
                ),
            ],
        },
    )

    def fake_run(*args, **kwargs):
        payload = _certificate_payload()
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    blocker = [item for item in report["blockers"] if item["id"] == "signing_plan_command_safety"][0]
    assert blocker["detail"] == "download_command_blocked"
    assert report["next_step"] == "Restore the release signing plan to the safe local-only command template."


def test_release_operator_environment_blocks_chained_signing_plan_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(
        verifier,
        "build_release_signing_plan",
        lambda _root: {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    "-CertificateThumbprint <CERT_THUMBPRINT> "
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute ; Remove-Item D:\\ANN"
                ),
            ],
        },
    )

    def fake_run(*args, **kwargs):
        payload = _certificate_payload()
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    blocker = [item for item in report["blockers"] if item["id"] == "signing_plan_command_safety"][0]
    assert blocker["detail"] == "statement_separator_blocked"


def test_release_operator_environment_blocks_opaque_signing_plan_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(
        verifier,
        "build_release_signing_plan",
        lambda _root: {
            "status": "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
            "commands": [
                (
                    "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
                    "-CertificateThumbprint <CERT_THUMBPRINT> "
                    "-TimestampUrl http://timestamp.digicert.com "
                    "-OutputPath installer\\release_signing_evidence.json -Execute "
                    "-EncodedCommand SQBFAFgA"
                ),
            ],
        },
    )

    def fake_run(*args, **kwargs):
        payload = _certificate_payload()
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    blocker = [item for item in report["blockers"] if item["id"] == "signing_plan_command_safety"][0]
    assert blocker["detail"] == "encoded_command_blocked"


def test_release_operator_environment_accepts_code_signing_oid_with_localized_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "powershell.exe")

    def fake_run(*args, **kwargs):
        payload = _certificate_payload(
            enhanced_key_usage=["Firma de codigo"],
            enhanced_key_usage_oids=["1.3.6.1.5.5.7.3.3"],
        )
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint=VALID_THUMBPRINT,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_READY"
    assert report["certificate"]["enhanced_key_usage_oids"] == ["1.3.6.1.5.5.7.3.3"]


def test_release_operator_environment_blocks_placeholder_thumbprint_without_shell(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    calls: list[object] = []
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: calls.append(args) or None)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint="<CERT_THUMBPRINT>",
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    blocker_ids = {blocker["id"] for blocker in report["blockers"]}
    assert "certificate_thumbprint_format" in blocker_ids
    assert "certificate_found" in blocker_ids
    assert report["certificate"]["detail"] == "thumbprint_placeholder_blocked"
    assert report["certificate_thumbprint_sha256"] == ""
    assert report["next_step"] == "Pass the real 40-character hexadecimal SHA1 Authenticode certificate thumbprint, not a placeholder."
    assert calls == []


def test_release_operator_environment_blocks_non_hex_thumbprint_without_shell(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=True)
    calls: list[object] = []
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: calls.append(args) or None)

    report = verifier.build_release_operator_environment_report(
        installer_root=tmp_path,
        certificate_thumbprint="Z" * 40,
    )

    assert report["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    blocker_ids = {blocker["id"] for blocker in report["blockers"]}
    assert "certificate_thumbprint_format" in blocker_ids
    assert report["certificate"]["detail"] == "thumbprint_non_hex_chars"
    assert report["certificate_thumbprint_sha256"] == ""
    assert calls == []


def test_release_operator_environment_artifacts(monkeypatch, tmp_path: Path) -> None:
    _patch_release_operator_dependencies(monkeypatch, tmp_path, ready=False)

    exit_code = verifier.main(["--installer-root", str(tmp_path), "--output-dir", str(tmp_path), "--json"])

    assert exit_code == 2
    payload = json.loads((tmp_path / "374_release_operator_environment.json").read_text(encoding="utf-8"))
    assert payload["status"] == "RELEASE_OPERATOR_ENV_BLOCKED"
    assert "certificate_thumbprint_sha256" in payload
    assert (tmp_path / "375_release_operator_environment.md").is_file()
