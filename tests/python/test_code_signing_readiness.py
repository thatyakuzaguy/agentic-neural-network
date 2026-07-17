from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_code_signing_readiness_blocks_without_final_binaries(tmp_path: Path) -> None:
    (tmp_path / "ANN_Setup.bat").write_text("@echo off\n", encoding="utf-8")
    readiness = activation.build_code_signing_readiness(tmp_path, execute_signature_check=False)

    assert readiness["status"] == "SIGNING_BLOCKED_MISSING_BINARIES"
    assert readiness["signed_installer"] is False
    assert "final_installer_binaries_missing" in readiness["blockers"]
    assert readiness["setup_batch_present"] is True
    assert readiness["no_signing_performed"] is True
    assert readiness["no_shell"] is True


def test_code_signing_readiness_detects_real_launcher_binaries() -> None:
    readiness = activation.build_code_signing_readiness(execute_signature_check=False)

    assert readiness["binary_presence"]["ANN_Setup.exe"] is True
    assert readiness["binary_presence"]["ANN_Uninstall.exe"] is True
    assert "final_installer_binaries_missing" not in readiness["blockers"]
    assert readiness["status"] in {"SIGNING_BLOCKED_UNSIGNED", "SIGNING_READY_FOR_EXTERNAL_TOOLING"}
    assert readiness["signed_installer"] is False
    assert readiness["no_signing_performed"] is True


def test_installer_launchers_are_auditable_and_do_not_use_shell_execute() -> None:
    installer_root = Path("D:/AgenticEngineeringNetwork/installer")
    common_source = (installer_root / "AnnPowerShellLauncher.cs").read_text(encoding="utf-8")

    assert (installer_root / "ANN_Setup.exe").is_file()
    assert (installer_root / "ANN_Uninstall.exe").is_file()
    assert (installer_root / "AnnSetupLauncher.cs").is_file()
    assert (installer_root / "AnnUninstallLauncher.cs").is_file()
    assert "UseShellExecute = false" in common_source
    assert "install_ann.ps1" in (installer_root / "AnnSetupLauncher.cs").read_text(encoding="utf-8")
    assert "uninstall_ann.ps1" in (installer_root / "AnnUninstallLauncher.cs").read_text(encoding="utf-8")


def test_code_signing_readiness_checks_authenticode_without_shell(monkeypatch, tmp_path: Path) -> None:
    for name in ("ANN_Setup.exe", "ANN_Uninstall.exe"):
        (tmp_path / name).write_bytes(b"placeholder")
    calls: list[dict[str, object]] = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        payload = {"Status": "Valid", "Signer": "CN=ANN Test", "TimestampSigner": "CN=Timestamp"}
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(activation.shutil, "which", lambda name: "powershell.exe" if name.startswith("powershell") else "signtool.exe")
    monkeypatch.setattr(activation.subprocess, "run", fake_run)

    readiness = activation.build_code_signing_readiness(tmp_path)

    assert readiness["status"] == "SIGNING_READY"
    assert readiness["signed_installer"] is True
    assert len(calls) == 2
    assert all(call["kwargs"].get("shell") is None for call in calls)
    assert all(call["kwargs"]["check"] is False for call in calls)


def test_code_signing_readiness_blocks_valid_signature_without_timestamp(monkeypatch, tmp_path: Path) -> None:
    for name in ("ANN_Setup.exe", "ANN_Uninstall.exe"):
        (tmp_path / name).write_bytes(b"placeholder")

    def fake_run(*args, **kwargs):
        payload = {"Status": "Valid", "Signer": "CN=ANN Test", "TimestampSigner": ""}
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(activation.shutil, "which", lambda name: "powershell.exe" if name.startswith("powershell") else "signtool.exe")
    monkeypatch.setattr(activation.subprocess, "run", fake_run)

    readiness = activation.build_code_signing_readiness(tmp_path)

    assert readiness["status"] == "SIGNING_BLOCKED_MISSING_TIMESTAMP"
    assert readiness["signed_installer"] is False
    assert "authenticode_timestamp_missing" in readiness["blockers"]
    assert readiness["untimestamped_binaries"] == ["ANN_Setup.exe", "ANN_Uninstall.exe"]


def test_code_signing_readiness_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_code_signing_readiness",
        lambda *_args, **_kwargs: {"status": "SIGNING_BLOCKED_MISSING_BINARIES"},
    )

    artifacts = activation.write_code_signing_readiness_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "354_code_signing_readiness.json",
        "355_code_signing_readiness.md",
    }


def test_release_signing_plan_is_non_mutating() -> None:
    plan = activation.build_release_signing_plan()

    assert plan["status"] in {
        "SIGNING_PLAN_BLOCKED",
        "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE",
    }
    assert plan["requires_trusted_code_signing_certificate"] is True
    assert plan["requires_signtool"] is True
    assert plan["requires_external_release_machine_review"] is True
    assert plan["commands_are_templates"] is True
    assert plan["placeholder_must_be_replaced"] is True
    assert plan["certificate_thumbprint_placeholder"] == "<CERT_THUMBPRINT>"
    assert plan["certificate_thumbprint_regex"] == "^[0-9A-Fa-f]{40}$"
    assert plan["sign_release_blocks_placeholder"] is True
    assert "signtool_missing_on_current_host" not in plan["blockers"]
    assert isinstance(plan["current_host_warnings"], list)
    assert plan["no_signing_performed"] is True
    assert plan["no_download"] is True
    assert plan["no_install"] is True
    assert plan["no_self_signed_certificate"] is True
    assert any("-Execute" in command for command in plan["commands"])
    assert any('-CertificateThumbprint "<CERT_THUMBPRINT>"' in command for command in plan["commands"])
    assert any("-TimestampUrl http://timestamp.digicert.com" in command for command in plan["commands"])
    assert any("-OutputPath installer\\release_signing_evidence.json" in command for command in plan["commands"])
    assert any("validate_clean_machine.ps1" in command for command in plan["commands"])
    assert any("-SigningEvidencePath installer\\release_signing_evidence.json" in command for command in plan["commands"])
    assert any("-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json" in command for command in plan["commands"])


def test_release_signing_plan_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_release_signing_plan_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "360_release_signing_plan.json",
        "361_release_signing_plan.md",
    }
    payload = json.loads((tmp_path / "360_release_signing_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.8"
    assert payload["no_signing_performed"] is True
