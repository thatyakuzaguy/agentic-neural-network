"""Read-only release-operator environment verifier for ANN.

This script checks whether the machine used to sign/release ANN has the
minimum external tooling needed for the final release evidence path. It never
signs binaries, installs ANN, downloads dependencies, loads models, or runs
inference.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.local_model_activation import (
    build_code_signing_readiness,
    build_release_signing_plan,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN release operator environment.")
    parser.add_argument("--installer-root", default="installer", help="Directory containing ANN_Setup.exe and ANN_Uninstall.exe.")
    parser.add_argument(
        "--certificate-thumbprint",
        default="",
        help="Trusted Authenticode certificate thumbprint expected on this release machine.",
    )
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print full verification JSON.")
    return parser


def build_release_operator_environment_report(
    *,
    installer_root: str | Path = "installer",
    certificate_thumbprint: str = "",
) -> dict[str, Any]:
    readiness = build_code_signing_readiness(installer_root, execute_signature_check=False)
    signing_plan = build_release_signing_plan(installer_root)
    thumbprint = _normalize_thumbprint(certificate_thumbprint)
    thumbprint_format_detail = _thumbprint_format_detail(thumbprint)
    certificate = (
        _detect_certificate(thumbprint)
        if thumbprint_format_detail == "thumbprint_format_valid"
        else _invalid_thumbprint_certificate_result(thumbprint_format_detail)
    )
    signing_plan_commands = signing_plan.get("commands", [])
    signing_plan_safety_detail = _signing_plan_command_safety_detail(signing_plan_commands)
    checks = [
        _check(
            "installer_binaries_present",
            not readiness.get("missing_binaries"),
            ", ".join(readiness.get("missing_binaries", [])) or "present",
        ),
        _check(
            "signing_script_present",
            Path(installer_root, "sign_release.ps1").is_file(),
            str(Path(installer_root, "sign_release.ps1")),
        ),
        _check("powershell_available", bool(readiness.get("powershell_detected")), str(readiness.get("powershell_path", ""))),
        _check("signtool_available", bool(readiness.get("signtool_detected")), str(readiness.get("signtool_path", ""))),
        _check("certificate_thumbprint_provided", bool(thumbprint), "provided" if thumbprint else "missing"),
        _check(
            "certificate_thumbprint_format",
            thumbprint_format_detail == "thumbprint_format_valid",
            thumbprint_format_detail,
        ),
        _check("certificate_found", certificate["found"], certificate["detail"]),
        _check("certificate_not_self_signed", certificate["not_self_signed"], certificate["self_signed_detail"]),
        _check("certificate_not_expired", certificate["not_expired"], certificate["expiry_detail"]),
        _check("certificate_has_private_key", certificate["has_private_key"], certificate["private_key_detail"]),
        _check("certificate_code_signing_eku", certificate["code_signing_eku"], certificate["eku_detail"]),
        _check(
            "sign_command_execute_mode",
            any("sign_release.ps1" in command and "-Execute" in command for command in signing_plan.get("commands", [])),
            "sign_release.ps1 -Execute",
        ),
        _check(
            "signing_evidence_output_configured",
            any("-OutputPath installer\\release_signing_evidence.json" in command for command in signing_plan.get("commands", [])),
            "installer\\release_signing_evidence.json",
        ),
        _check(
            "timestamp_url_configured",
            any("-TimestampUrl " in command for command in signing_plan_commands),
            "TimestampUrl required for RFC3161 timestamp evidence",
        ),
        _check(
            "signing_plan_command_safety",
            signing_plan_safety_detail == "command_string_safe",
            signing_plan_safety_detail,
        ),
    ]
    blockers = [check for check in checks if not check["passed"]]
    status = "RELEASE_OPERATOR_ENV_READY" if not blockers else "RELEASE_OPERATOR_ENV_BLOCKED"
    return {
        "version": "19.4",
        "status": status,
        "exit_code": 0 if status == "RELEASE_OPERATOR_ENV_READY" else 2,
        "installer_root": str(installer_root),
        "certificate_thumbprint_provided": bool(thumbprint),
        "certificate_thumbprint": _redact_thumbprint(thumbprint),
        "certificate_thumbprint_sha256": (
            _thumbprint_sha256(thumbprint)
            if thumbprint_format_detail == "thumbprint_format_valid"
            else ""
        ),
        "checks": checks,
        "blockers": blockers,
        "code_signing_readiness": readiness,
        "release_signing_plan_status": signing_plan.get("status"),
        "release_signing_commands": signing_plan.get("commands", []),
        "certificate": certificate,
        "next_step": _next_step(blockers),
        "no_signing": True,
        "no_install": True,
        "no_download": True,
        "no_model_load": True,
        "no_inference": True,
        "no_shell": True,
    }


def write_release_operator_environment_artifacts(report: dict[str, Any], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "374_release_operator_environment.json"
    md_path = target / "375_release_operator_environment.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_release_operator_environment_report(
        installer_root=args.installer_root,
        certificate_thumbprint=args.certificate_thumbprint,
    )
    if args.output_dir:
        write_release_operator_environment_artifacts(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_summary(report))
    return int(report["exit_code"])


def _detect_certificate(thumbprint: str) -> dict[str, Any]:
    if not thumbprint:
        return {
            "found": False,
            "not_self_signed": False,
            "not_expired": False,
            "has_private_key": False,
            "code_signing_eku": False,
            "detail": "certificate_thumbprint_missing",
            "self_signed_detail": "certificate_thumbprint_missing",
            "expiry_detail": "certificate_thumbprint_missing",
            "private_key_detail": "certificate_thumbprint_missing",
            "eku_detail": "certificate_thumbprint_missing",
            "stores_checked": [],
        }
    powershell = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return {
            "found": False,
            "not_self_signed": False,
            "not_expired": False,
            "has_private_key": False,
            "code_signing_eku": False,
            "detail": "powershell_missing",
            "self_signed_detail": "powershell_missing",
            "expiry_detail": "powershell_missing",
            "private_key_detail": "powershell_missing",
            "eku_detail": "powershell_missing",
            "stores_checked": [],
        }
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "$thumb = $args[0].Replace(' ', '').ToUpperInvariant(); "
            "$stores = @('Cert:\\CurrentUser\\My','Cert:\\LocalMachine\\My'); "
            "$matches = foreach ($store in $stores) { "
            "Get-ChildItem $store -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Thumbprint.Replace(' ', '').ToUpperInvariant() -eq $thumb } | "
            "Select-Object @{Name='Store';Expression={$store}}, "
            "Subject, Issuer, Thumbprint, HasPrivateKey, "
            "@{Name='NotAfterUtc';Expression={$_.NotAfter.ToUniversalTime().ToString('o')}}, "
            "@{Name='EnhancedKeyUsageList';Expression={@($_.EnhancedKeyUsageList | ForEach-Object { $_.FriendlyName })}}, "
            "@{Name='EnhancedKeyUsageOidList';Expression={@($_.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value })}} "
            "}; "
            "$matches | ConvertTo-Json -Depth 4"
        ),
        thumbprint,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "found": False,
            "not_self_signed": False,
            "not_expired": False,
            "has_private_key": False,
            "code_signing_eku": False,
            "detail": f"certificate_lookup_failed:{exc}",
            "self_signed_detail": "certificate_lookup_failed",
            "expiry_detail": "certificate_lookup_failed",
            "private_key_detail": "certificate_lookup_failed",
            "eku_detail": "certificate_lookup_failed",
            "stores_checked": ["CurrentUser\\My", "LocalMachine\\My"],
        }
    if result.returncode != 0:
        return {
            "found": False,
            "not_self_signed": False,
            "not_expired": False,
            "has_private_key": False,
            "code_signing_eku": False,
            "detail": f"certificate_lookup_returncode:{result.returncode}",
            "self_signed_detail": "certificate_lookup_failed",
            "expiry_detail": "certificate_lookup_failed",
            "private_key_detail": "certificate_lookup_failed",
            "eku_detail": "certificate_lookup_failed",
            "stderr": result.stderr.strip(),
            "stores_checked": ["CurrentUser\\My", "LocalMachine\\My"],
        }
    matches = _load_certificate_matches(result.stdout)
    if not matches:
        return {
            "found": False,
            "not_self_signed": False,
            "not_expired": False,
            "has_private_key": False,
            "code_signing_eku": False,
            "detail": "certificate_not_found",
            "self_signed_detail": "certificate_not_found",
            "expiry_detail": "certificate_not_found",
            "private_key_detail": "certificate_not_found",
            "eku_detail": "certificate_not_found",
            "stores_checked": ["CurrentUser\\My", "LocalMachine\\My"],
        }
    first = matches[0]
    subject = str(first.get("Subject", ""))
    issuer = str(first.get("Issuer", ""))
    not_self_signed = bool(subject and issuer and subject != issuer)
    not_expired = _certificate_not_expired(first)
    has_private_key = first.get("HasPrivateKey") is True
    eku_names = _certificate_eku_names(first)
    eku_oids = _certificate_eku_oids(first)
    code_signing_eku = _has_code_signing_eku(eku_names, eku_oids)
    return {
        "found": True,
        "not_self_signed": not_self_signed,
        "not_expired": not_expired,
        "has_private_key": has_private_key,
        "code_signing_eku": code_signing_eku,
        "detail": f"certificate_found:{first.get('Store', 'unknown_store')}",
        "self_signed_detail": "not_self_signed" if not_self_signed else "subject_matches_issuer",
        "expiry_detail": "not_expired" if not_expired else f"expired_or_invalid:{first.get('NotAfterUtc', '')}",
        "private_key_detail": "private_key_available" if has_private_key else "private_key_missing",
        "eku_detail": "code_signing" if code_signing_eku else _missing_code_signing_detail(eku_names, eku_oids),
        "subject": subject,
        "issuer": issuer,
        "not_after_utc": str(first.get("NotAfterUtc", "")),
        "enhanced_key_usage": eku_names,
        "enhanced_key_usage_oids": eku_oids,
        "stores_checked": ["CurrentUser\\My", "LocalMachine\\My"],
    }


def _certificate_not_expired(certificate: dict[str, Any]) -> bool:
    value = certificate.get("NotAfterUtc")
    if not isinstance(value, str) or not value:
        return False
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires > datetime.now(UTC)


def _certificate_eku_names(certificate: dict[str, Any]) -> list[str]:
    raw = certificate.get("EnhancedKeyUsageList")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def _certificate_eku_oids(certificate: dict[str, Any]) -> list[str]:
    raw = certificate.get("EnhancedKeyUsageOidList")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def _has_code_signing_eku(names: list[str], oids: list[str]) -> bool:
    normalized_names = {name.lower() for name in names}
    normalized_oids = {oid.strip() for oid in oids}
    return "code signing" in normalized_names or "1.3.6.1.5.5.7.3.3" in normalized_oids


def _missing_code_signing_detail(names: list[str], oids: list[str]) -> str:
    values = [*names, *oids]
    return f"missing_code_signing:{', '.join(values) or 'none'}"


def _load_certificate_matches(stdout: str) -> list[dict[str, Any]]:
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


def _signing_plan_command_safety_detail(commands: object) -> str:
    if not isinstance(commands, list) or not commands:
        return "commands_missing"
    for command in commands:
        if not isinstance(command, str):
            return "command_entry_invalid"
        detail = _command_string_safety_detail(command)
        if detail != "command_string_safe":
            return detail
    return "command_string_safe"


def _command_string_safety_detail(command: str) -> str:
    if not command.strip():
        return "command_missing"
    normalized = command.replace("<CERT_THUMBPRINT>", "CERT_THUMBPRINT")
    lowered = normalized.lower()
    forbidden = {
        "&&": "command_chaining_blocked",
        "||": "command_chaining_blocked",
        ";": "statement_separator_blocked",
        "|": "pipeline_blocked",
        ">": "redirection_blocked",
        "<": "redirection_blocked",
        "`": "powershell_escape_blocked",
        "$(": "subexpression_blocked",
    }
    for token, reason in forbidden.items():
        if token in normalized:
            return reason
    blocked_terms = {
        "invoke-webrequest": "download_command_blocked",
        "invoke-restmethod": "download_command_blocked",
        "invoke-expression": "opaque_execution_blocked",
        "start-bitstransfer": "download_command_blocked",
        "start-process": "process_spawn_blocked",
        " -encodedcommand": "encoded_command_blocked",
        " -enc ": "encoded_command_blocked",
        "curl ": "download_command_blocked",
        "curl.exe": "download_command_blocked",
        "wget ": "download_command_blocked",
        "wget.exe": "download_command_blocked",
        " iwr ": "download_command_blocked",
        " irm ": "download_command_blocked",
        " iex ": "opaque_execution_blocked",
        "new-object net.webclient": "download_command_blocked",
        "pip install": "dependency_install_blocked",
        "npm install": "dependency_install_blocked",
    }
    padded = f" {lowered} "
    for token, reason in blocked_terms.items():
        if token in padded:
            return reason
    return "command_string_safe"


def _next_step(blockers: list[dict[str, Any]]) -> str:
    ids = {str(blocker.get("id")) for blocker in blockers}
    if not blockers:
        return "Run installer/sign_release.ps1 with -Execute, then validate on a clean Windows 11 machine."
    if "installer_binaries_present" in ids:
        return "Build ANN_Setup.exe and ANN_Uninstall.exe before release signing."
    if "signing_script_present" in ids:
        return "Restore installer/sign_release.ps1 in the release handoff bundle."
    if "powershell_available" in ids:
        return "Run this verifier from a Windows release machine with PowerShell available."
    if "certificate_thumbprint_provided" in ids:
        return "Pass --certificate-thumbprint <CERT_THUMBPRINT> for the trusted Authenticode certificate."
    if "certificate_thumbprint_format" in ids:
        return "Pass the real 40-character hexadecimal SHA1 Authenticode certificate thumbprint, not a placeholder."
    if "signtool_available" in ids:
        return "Install Windows SDK signing tools on the release machine so signtool.exe is available."
    if "certificate_found" in ids:
        return "Import the trusted Authenticode certificate into CurrentUser\\My or LocalMachine\\My."
    if "certificate_not_self_signed" in ids:
        return "Use a trusted public code-signing certificate; self-signed certificates are blocked for final release."
    if "certificate_not_expired" in ids:
        return "Use a non-expired trusted Authenticode certificate for final release signing."
    if "certificate_has_private_key" in ids:
        return "Import the code-signing certificate with its private key on the release machine."
    if "certificate_code_signing_eku" in ids:
        return "Use a certificate whose Enhanced Key Usage includes Code Signing."
    if "timestamp_url_configured" in ids:
        return "Configure sign_release.ps1 commands with -TimestampUrl for RFC3161 timestamp evidence."
    if "signing_plan_command_safety" in ids:
        return "Restore the release signing plan to the safe local-only command template."
    return f"Resolve release operator blocker: {blockers[0].get('id')}"


def _normalize_thumbprint(value: str) -> str:
    return "".join(str(value).split()).upper()


def _thumbprint_format_detail(value: str) -> str:
    if not value:
        return "thumbprint_missing"
    if value in {"<CERT_THUMBPRINT>", "CERT_THUMBPRINT"}:
        return "thumbprint_placeholder_blocked"
    if len(value) != 40:
        return "thumbprint_must_be_40_hex_chars"
    if any(char not in "0123456789ABCDEF" for char in value):
        return "thumbprint_non_hex_chars"
    return "thumbprint_format_valid"


def _invalid_thumbprint_certificate_result(detail: str) -> dict[str, Any]:
    return {
        "found": False,
        "not_self_signed": False,
        "not_expired": False,
        "has_private_key": False,
        "code_signing_eku": False,
        "detail": detail,
        "self_signed_detail": detail,
        "expiry_detail": detail,
        "private_key_detail": detail,
        "eku_detail": detail,
        "stores_checked": [],
    }


def _thumbprint_sha256(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_thumbprint(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _summary(report: dict[str, Any]) -> str:
    blocker_ids = ", ".join(str(blocker["id"]) for blocker in report["blockers"]) or "none"
    return "\n".join(
        [
            "ANN Release Operator Environment Verification",
            f"Status: {report['status']}",
            f"Installer Root: {report['installer_root']}",
            f"Certificate Thumbprint: {report['certificate_thumbprint'] or 'missing'}",
            f"Certificate Thumbprint SHA256: {report['certificate_thumbprint_sha256'] or 'missing'}",
            f"Code Signing Readiness: {report['code_signing_readiness'].get('status')}",
            f"Release Signing Plan: {report['release_signing_plan_status']}",
            f"Blockers: {blocker_ids}",
            f"Next Step: {report['next_step']}",
        ]
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ANN Release Operator Environment Verification",
        "",
        f"- Status: `{report['status']}`",
        f"- Installer Root: `{report['installer_root']}`",
        f"- Certificate Thumbprint: `{report['certificate_thumbprint'] or 'missing'}`",
        f"- Certificate Thumbprint SHA256: `{report['certificate_thumbprint_sha256'] or 'missing'}`",
        f"- Code Signing Readiness: `{report['code_signing_readiness'].get('status')}`",
        f"- Release Signing Plan: `{report['release_signing_plan_status']}`",
        f"- Next Step: {report['next_step']}",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"- `{check['id']}`: {check['status']} ({check['detail']})")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
