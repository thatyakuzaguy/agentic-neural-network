"""Verify external ANN release evidence without mutating the host.

This verifier is intended for the final release handoff path. It aggregates:

- release-candidate handoff bundle integrity,
- Authenticode status for installer binaries,
- clean-machine validation evidence.

It never signs binaries, installs ANN, downloads dependencies, loads models, or
runs inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.local_model_activation import (
    build_clean_machine_evidence,
    build_code_signing_readiness,
)
from scripts.runtime.verify_release_candidate_bundle import verify_bundle

_RELEASE_COMMAND_CONTRACT_HASH_KEYS = (
    "bundle_verifier_command",
    "release_operator_environment_command",
    "sign_command",
    "clean_machine_command",
    "external_release_evidence_command",
    "final_verifier_command",
    "repo_root_final_verifier_command",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN external release evidence.")
    parser.add_argument("--install-root", default="D:/ANN", help="Installed ANN root containing clean-machine marker.")
    parser.add_argument("--installer-root", default="installer", help="Directory containing ANN_Setup.exe and ANN_Uninstall.exe.")
    parser.add_argument(
        "--clean-machine-marker",
        default=None,
        help="Optional copied clean_machine_external_validation.json from the external Windows 11 validation machine.",
    )
    parser.add_argument(
        "--bundle-root",
        default="outputs/release_candidates/ANN_RC_HANDOFF",
        help="Release-candidate handoff bundle to verify.",
    )
    parser.add_argument(
        "--signing-evidence",
        default=None,
        help="Optional release_signing_evidence.json written by installer/sign_release.ps1 on the signing machine.",
    )
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print full verification JSON.")
    return parser


def build_external_release_evidence_report(
    *,
    install_root: str | Path = "D:/ANN",
    installer_root: str | Path = "installer",
    bundle_root: str | Path = "outputs/release_candidates/ANN_RC_HANDOFF",
    clean_machine_marker: str | Path | None = None,
    signing_evidence: str | Path | None = None,
) -> dict[str, Any]:
    bundle = verify_bundle(bundle_root)
    signing = build_code_signing_readiness(installer_root)
    clean_machine = build_clean_machine_evidence(install_root, external_marker_path=clean_machine_marker)
    signing_evidence_path = Path(signing_evidence) if signing_evidence is not None else Path(installer_root) / "release_signing_evidence.json"
    release_signing_evidence = _load_release_signing_evidence(signing_evidence_path)
    installer_hashes_match_handoff = _installer_hashes_match_handoff(signing, bundle, release_signing_evidence)
    installer_hashes_match = _installer_hashes_match(signing, clean_machine)
    release_signing_evidence_valid = _release_signing_evidence_valid(signing, release_signing_evidence)
    signing_evidence_clean_machine_hash_match = _signing_evidence_clean_machine_hash_match(
        signing_evidence_path,
        clean_machine,
    )
    clean_machine_transfer_manifest_hash_match = _clean_machine_transfer_manifest_hash_match(bundle, clean_machine)
    clean_machine_transfer_manifest_aggregate_hash_match = (
        _clean_machine_transfer_manifest_aggregate_hash_match(bundle, clean_machine)
    )
    release_command_contract_ready = _bundle_release_command_contract_ready(bundle)
    clean_machine_signer_thumbprint_match = _clean_machine_signer_thumbprints_match(
        release_signing_evidence,
        clean_machine,
    )
    checks = [
        _check("handoff_bundle", bundle["status"] == "HANDOFF_VERIFIED", bundle["status"]),
        _check(
            "handoff_installer_hash_match",
            installer_hashes_match_handoff,
            _handoff_installer_hash_match_detail(signing, bundle, release_signing_evidence),
        ),
        _check("signed_installer", signing["signed_installer"] is True, signing["status"]),
        _check(
            "release_signing_evidence",
            release_signing_evidence_valid,
            _release_signing_evidence_detail(signing, release_signing_evidence, signing_evidence_path),
        ),
        _check(
            "clean_machine_signing_evidence_hash_match",
            signing_evidence_clean_machine_hash_match,
            _signing_evidence_clean_machine_hash_detail(signing_evidence_path, clean_machine),
        ),
        _check(
            "clean_machine_transfer_manifest_hash_match",
            clean_machine_transfer_manifest_hash_match,
            _clean_machine_transfer_manifest_hash_detail(bundle, clean_machine),
        ),
        _check(
            "clean_machine_transfer_manifest_aggregate_hash_match",
            clean_machine_transfer_manifest_aggregate_hash_match,
            _clean_machine_transfer_manifest_aggregate_hash_detail(bundle, clean_machine),
        ),
        _check(
            "release_command_contract",
            release_command_contract_ready,
            _bundle_release_command_contract_detail(bundle),
        ),
        _check(
            "external_clean_machine",
            clean_machine["sufficient_for_final_release"] is True,
            clean_machine["status"],
        ),
        _check(
            "external_marker_strong",
            clean_machine.get("external_validation", {}).get("status") == "EXTERNAL_VALIDATION_ACCEPTED",
            clean_machine.get("external_validation", {}).get("status", "missing"),
        ),
        _check(
            "clean_machine_installer_hash_match",
            installer_hashes_match,
            _installer_hash_match_detail(signing, clean_machine),
        ),
        _check(
            "clean_machine_signer_thumbprint_match",
            clean_machine_signer_thumbprint_match,
            _clean_machine_signer_thumbprint_detail(release_signing_evidence, clean_machine),
        ),
    ]
    blockers = [check for check in checks if not check["passed"]]
    status = "EXTERNAL_RELEASE_EVIDENCE_READY" if not blockers else "EXTERNAL_RELEASE_EVIDENCE_BLOCKED"
    return {
        "version": "19.5",
        "status": status,
        "exit_code": 0 if status == "EXTERNAL_RELEASE_EVIDENCE_READY" else 2,
        "install_root": str(install_root),
        "installer_root": str(installer_root),
        "bundle_root": str(bundle_root),
        "clean_machine_marker": str(clean_machine_marker) if clean_machine_marker is not None else "",
        "signing_evidence_path": str(signing_evidence_path),
        "installer_hashes_match_handoff": installer_hashes_match_handoff,
        "installer_hashes_match_clean_machine": installer_hashes_match,
        "release_signing_evidence_valid": release_signing_evidence_valid,
        "clean_machine_signing_evidence_hash_match": signing_evidence_clean_machine_hash_match,
        "clean_machine_transfer_manifest_hash_match": clean_machine_transfer_manifest_hash_match,
        "clean_machine_transfer_manifest_aggregate_hash_match": clean_machine_transfer_manifest_aggregate_hash_match,
        "release_command_contract_ready": release_command_contract_ready,
        "release_command_contract": _bundle_release_command_contract(bundle),
        "clean_machine_signer_thumbprint_match": clean_machine_signer_thumbprint_match,
        "checks": checks,
        "blockers": blockers,
        "bundle": bundle,
        "signing": signing,
        "release_signing_evidence": release_signing_evidence,
        "clean_machine": clean_machine,
        "no_install": True,
        "no_download": True,
        "no_signing": True,
        "no_model_load": True,
        "no_inference": True,
        "next_step": _next_step(blockers),
    }


def write_external_release_evidence_artifacts(report: dict[str, Any], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "370_external_release_evidence_verification.json"
    md_path = target / "371_external_release_evidence_verification.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_external_release_evidence_report(
        install_root=args.install_root,
        installer_root=args.installer_root,
        bundle_root=args.bundle_root,
        clean_machine_marker=args.clean_machine_marker,
        signing_evidence=args.signing_evidence,
    )
    if args.output_dir:
        write_external_release_evidence_artifacts(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_summary(report))
    return int(report["exit_code"])


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


def _installer_hashes_match(signing: dict[str, Any], clean_machine: dict[str, Any]) -> bool:
    current = signing.get("binary_sha256") if isinstance(signing.get("binary_sha256"), dict) else {}
    external = (
        clean_machine.get("external_installer_hashes")
        if isinstance(clean_machine.get("external_installer_hashes"), dict)
        else {}
    )
    required = ("ANN_Setup.exe", "ANN_Uninstall.exe")
    return all(
        isinstance(current.get(name), str)
        and isinstance(external.get(name), str)
        and _is_sha256_hex(str(current.get(name)))
        and _is_sha256_hex(str(external.get(name)))
        and str(current.get(name)).lower() == str(external.get(name)).lower()
        for name in required
    )


def _installer_hashes_match_handoff(
    signing: dict[str, Any],
    bundle: dict[str, Any],
    release_signing_evidence: dict[str, Any],
) -> bool:
    current = _handoff_lineage_hashes(signing, release_signing_evidence)
    handoff = bundle.get("installer_hashes") if isinstance(bundle.get("installer_hashes"), dict) else {}
    required = ("ANN_Setup.exe", "ANN_Uninstall.exe")
    return all(
        isinstance(current.get(name), str)
        and isinstance(handoff.get(name), str)
        and _is_sha256_hex(str(current.get(name)))
        and _is_sha256_hex(str(handoff.get(name)))
        and str(current.get(name)).lower() == str(handoff.get(name)).lower()
        for name in required
    )


def _handoff_installer_hash_match_detail(
    signing: dict[str, Any],
    bundle: dict[str, Any],
    release_signing_evidence: dict[str, Any],
) -> str:
    current = _handoff_lineage_hashes(signing, release_signing_evidence)
    handoff = bundle.get("installer_hashes") if isinstance(bundle.get("installer_hashes"), dict) else {}
    mismatches = [
        name
        for name in ("ANN_Setup.exe", "ANN_Uninstall.exe")
        if not _hashes_match(current.get(name), handoff.get(name))
    ]
    return "match" if not mismatches else ", ".join(mismatches)


def _handoff_lineage_hashes(signing: dict[str, Any], release_signing_evidence: dict[str, Any]) -> dict[str, str]:
    pre_sign = _release_signing_evidence_by_name(release_signing_evidence, key="pre_sign_evidence")
    if pre_sign:
        return {
            name: str(item.get("sha256", ""))
            for name, item in pre_sign.items()
            if isinstance(item.get("sha256"), str)
        }
    current = signing.get("binary_sha256") if isinstance(signing.get("binary_sha256"), dict) else {}
    return {str(name): str(value) for name, value in current.items() if isinstance(value, str)}


def _installer_hash_match_detail(signing: dict[str, Any], clean_machine: dict[str, Any]) -> str:
    current = signing.get("binary_sha256") if isinstance(signing.get("binary_sha256"), dict) else {}
    external = (
        clean_machine.get("external_installer_hashes")
        if isinstance(clean_machine.get("external_installer_hashes"), dict)
        else {}
    )
    mismatches = [
        name
        for name in ("ANN_Setup.exe", "ANN_Uninstall.exe")
        if not _hashes_match(current.get(name), external.get(name))
    ]
    return "match" if not mismatches else ", ".join(mismatches)


def _clean_machine_signer_thumbprints_match(
    release_signing_evidence: dict[str, Any],
    clean_machine: dict[str, Any],
) -> bool:
    return _clean_machine_signer_thumbprint_detail(
        release_signing_evidence,
        clean_machine,
    ) == "match"


def _clean_machine_signer_thumbprint_detail(
    release_signing_evidence: dict[str, Any],
    clean_machine: dict[str, Any],
) -> str:
    certificate_hash = _release_signing_certificate_thumbprint_hash(release_signing_evidence)
    if not certificate_hash:
        return "signing_evidence_thumbprint_sha256_missing"
    payload = clean_machine.get("external_validation_payload")
    if not isinstance(payload, dict):
        return "clean_machine_payload_missing"
    mismatches: list[str] = []
    for field, name in (
        ("setup_signature", "ANN_Setup.exe"),
        ("uninstall_signature", "ANN_Uninstall.exe"),
    ):
        signature = payload.get(field)
        if not isinstance(signature, dict):
            mismatches.append(f"{name}:signature_missing")
            continue
        marker_hash = str(signature.get("signer_thumbprint_sha256") or "").strip().lower()
        if not marker_hash:
            mismatches.append(f"{name}:signer_thumbprint_sha256_missing")
        elif marker_hash != certificate_hash:
            mismatches.append(f"{name}:signer_thumbprint_sha256_mismatch")
    return "match" if not mismatches else ", ".join(mismatches)


def _load_release_signing_evidence(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        return {"status": "MISSING", "path": str(path)}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"status": "INVALID", "path": str(path), "error": str(exc)}
    if not isinstance(payload, dict):
        return {"status": "INVALID", "path": str(path)}
    payload.setdefault("path", str(path))
    return payload


def _release_signing_evidence_valid(signing: dict[str, Any], evidence: dict[str, Any]) -> bool:
    if evidence.get("execute") is not True:
        return False
    if _release_signing_evidence_safety_policy_detail(evidence) != "safety_policy_passed":
        return False
    if not _release_signing_evidence_has_certificate_preflight(evidence):
        return False
    if _release_signing_evidence_command_policy_detail(evidence) != "command_policy_passed":
        return False
    if _release_signing_evidence_path_policy_detail(evidence) != "path_policy_passed":
        return False
    current = signing.get("binary_sha256") if isinstance(signing.get("binary_sha256"), dict) else {}
    pre_sign = _release_signing_evidence_by_name(evidence, key="pre_sign_evidence")
    by_name = _release_signing_evidence_by_name(evidence)
    certificate_subject = _release_signing_certificate_subject(evidence)
    for name in ("ANN_Setup.exe", "ANN_Uninstall.exe"):
        pre_item = pre_sign.get(name)
        if not pre_item or not _is_sha256_hex(str(pre_item.get("sha256") or "")):
            return False
        item = by_name.get(name)
        if not item:
            return False
        if item.get("status") != "Valid":
            return False
        if not _target_signer_matches_certificate(item, certificate_subject):
            return False
        if not _target_signer_thumbprint_matches_certificate(item, evidence):
            return False
        if not item.get("timestamp_signer"):
            return False
        if not _hashes_match(item.get("sha256"), current.get(name)):
            return False
    return True


def _release_signing_evidence_by_name(
    evidence: dict[str, Any],
    *,
    key: str = "target_evidence",
) -> dict[str, dict[str, Any]]:
    items = evidence.get(key)
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        name = Path(path).name
        if name:
            result[name] = item
    return result


def _release_signing_evidence_detail(signing: dict[str, Any], evidence: dict[str, Any], path: Path) -> str:
    if evidence.get("status") in {"MISSING", "INVALID"}:
        return f"{evidence.get('status')}:{path}"
    if evidence.get("execute") is not True:
        return "dry_run_or_not_executed"
    safety_detail = _release_signing_evidence_safety_policy_detail(evidence)
    if safety_detail != "safety_policy_passed":
        return safety_detail
    certificate_detail = _release_signing_evidence_certificate_preflight_detail(evidence)
    if certificate_detail != "certificate_preflight_passed":
        return certificate_detail
    command_policy_detail = _release_signing_evidence_command_policy_detail(evidence)
    if command_policy_detail != "command_policy_passed":
        return command_policy_detail
    path_policy_detail = _release_signing_evidence_path_policy_detail(evidence)
    if path_policy_detail != "path_policy_passed":
        return path_policy_detail
    current = signing.get("binary_sha256") if isinstance(signing.get("binary_sha256"), dict) else {}
    pre_sign = _release_signing_evidence_by_name(evidence, key="pre_sign_evidence")
    by_name = _release_signing_evidence_by_name(evidence)
    certificate_subject = _release_signing_certificate_subject(evidence)
    failures = []
    for name in ("ANN_Setup.exe", "ANN_Uninstall.exe"):
        pre_item = pre_sign.get(name)
        if not pre_item or not pre_item.get("sha256"):
            failures.append(f"{name}:pre_sign_sha256_missing")
        elif not _is_sha256_hex(str(pre_item.get("sha256"))):
            failures.append(f"{name}:pre_sign_sha256_invalid")
        item = by_name.get(name)
        if not item:
            failures.append(f"{name}:missing")
            continue
        if item.get("status") != "Valid":
            failures.append(f"{name}:status={item.get('status')}")
        if not _target_signer_matches_certificate(item, certificate_subject):
            failures.append(f"{name}:signer_mismatch")
        if not _target_signer_thumbprint_matches_certificate(item, evidence):
            failures.append(f"{name}:signer_thumbprint_mismatch")
        if not item.get("timestamp_signer"):
            failures.append(f"{name}:timestamp_missing")
        if not _is_sha256_hex(str(item.get("sha256") or "")):
            failures.append(f"{name}:sha256_invalid")
        elif not _is_sha256_hex(str(current.get(name) or "")):
            failures.append(f"{name}:current_sha256_invalid")
        elif str(item.get("sha256")).lower() != str(current.get(name)).lower():
            failures.append(f"{name}:sha256_mismatch")
    return "match" if not failures else ", ".join(failures)


def _release_signing_evidence_has_timestamp_policy(evidence: dict[str, Any]) -> bool:
    return _release_signing_evidence_command_policy_detail(evidence) == "command_policy_passed"


def _release_signing_evidence_safety_policy_detail(evidence: dict[str, Any]) -> str:
    required = {
        "no_download": True,
        "no_install": True,
        "no_shell": True,
        "no_self_signed_certificate": True,
    }
    failures = [key for key, expected in required.items() if evidence.get(key) is not expected]
    return "safety_policy_passed" if not failures else "safety_policy_failed:" + ", ".join(failures)


def _release_signing_evidence_path_policy_detail(evidence: dict[str, Any]) -> str:
    failures: list[str] = []
    expected = {"ANN_Setup.exe", "ANN_Uninstall.exe"}
    for key in ("pre_sign_evidence", "target_evidence"):
        items = evidence.get(key)
        if not isinstance(items, list) or not items:
            failures.append(f"{key}_missing")
            continue
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                failures.append(f"{key}:entry_invalid")
                continue
            path = str(item.get("path") or "").strip()
            name = Path(path).name
            if not path:
                failures.append(f"{key}:path_missing")
                continue
            if name not in expected:
                failures.append(f"{key}:unexpected_target:{name or 'missing'}")
            elif name in seen:
                failures.append(f"{key}:duplicate_target:{name}")
            else:
                seen.add(name)
            path_detail = _signing_evidence_path_safety_detail(path)
            if path_detail != "path_safe":
                failures.append(f"{key}:{name or 'missing'}:{path_detail}")
        missing = sorted(expected - seen)
        failures.extend(f"{key}:missing_target:{name}" for name in missing)
    return "path_policy_passed" if not failures else "path_policy_failed:" + ", ".join(failures)


def _release_signing_evidence_command_policy_detail(evidence: dict[str, Any]) -> str:
    timestamp_url = evidence.get("timestamp_url")
    if not isinstance(timestamp_url, str) or not timestamp_url.strip():
        return "timestamp_policy_missing"
    certificate_thumbprint_hash = _release_signing_certificate_thumbprint_hash(evidence)
    if not certificate_thumbprint_hash:
        return "certificate_thumbprint_hash_missing"
    expected_timestamp_url = timestamp_url.strip().lower()
    commands = evidence.get("planned_commands")
    if not isinstance(commands, list) or not commands:
        return "planned_commands_missing"
    covered_targets: set[str] = set()
    planned_thumbprint_hashes: set[str] = set()
    failures = []
    for item in commands:
        if not isinstance(item, dict):
            failures.append("command_entry_invalid")
            continue
        command = item.get("command")
        if not isinstance(command, list):
            failures.append("command_list_missing")
            continue
        tool_detail = _planned_command_tool_detail(command)
        if tool_detail != "signtool_sign":
            failures.append(tool_detail)
        normalized = [str(part).lower() for part in command]
        if _flag_value(normalized, "/tr") != expected_timestamp_url:
            failures.append("timestamp_url_mismatch")
        if _flag_value(normalized, "/td") != "sha256":
            failures.append("timestamp_digest_not_sha256")
        if _flag_value(normalized, "/fd") != "sha256":
            failures.append("file_digest_not_sha256")
        sha1_value = _flag_value(normalized, "/sha1")
        if not sha1_value:
            failures.append("certificate_thumbprint_flag_missing")
        elif not _is_sha1_thumbprint(_normalize_thumbprint(sha1_value)):
            failures.append("certificate_thumbprint_flag_invalid")
        else:
            thumbprint_hash = _sha256_text(_normalize_thumbprint(sha1_value))
            planned_thumbprint_hashes.add(thumbprint_hash)
            if thumbprint_hash != certificate_thumbprint_hash:
                failures.append("certificate_thumbprint_mismatch")
        target_name = _planned_command_target_name(item, command)
        if target_name in {"ANN_Setup.exe", "ANN_Uninstall.exe"}:
            covered_targets.add(target_name)
        else:
            failures.append(f"unexpected_or_missing_target:{target_name or 'missing'}")
    missing_targets = sorted({"ANN_Setup.exe", "ANN_Uninstall.exe"} - covered_targets)
    failures.extend(f"missing_planned_command:{name}" for name in missing_targets)
    if len(planned_thumbprint_hashes) > 1:
        failures.append("inconsistent_certificate_thumbprints")
    return "command_policy_passed" if not failures else "command_policy_failed:" + ", ".join(failures)


def _planned_command_tool_detail(command: list[Any]) -> str:
    if len(command) < 2:
        return "command_too_short"
    executable = Path(str(command[0]).replace("\\", "/")).name.lower()
    subcommand = str(command[1]).strip().lower()
    if executable != "signtool.exe":
        return "signtool_executable_required"
    if subcommand != "sign":
        return "signtool_sign_subcommand_required"
    return "signtool_sign"


def _planned_command_target_name(item: dict[str, Any], command: list[Any]) -> str:
    target = str(item.get("target") or "").strip()
    command_target = str(command[-1] if command else "").strip()
    target_detail = _signing_evidence_path_safety_detail(target) if target else "path_missing"
    command_target_detail = _signing_evidence_path_safety_detail(command_target) if command_target else "path_missing"
    if target_detail != "path_safe":
        return f"{Path(target).name or 'missing'}:{target_detail}"
    if command_target_detail != "path_safe":
        return f"{Path(command_target).name or 'missing'}:{command_target_detail}"
    target_name = Path(target).name if target else ""
    command_target_name = Path(command_target).name if command_target else ""
    if target_name and command_target_name and target_name != command_target_name:
        return f"{target_name}!={command_target_name}"
    return target_name or command_target_name


def _signing_evidence_path_safety_detail(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    lowered = normalized.lower()
    if not normalized:
        return "path_missing"
    if lowered.startswith("c:/") or lowered.startswith("/mnt/c/"):
        return "path_c_drive_blocked"
    if any(part == ".." for part in normalized.split("/")):
        return "path_traversal_blocked"
    return "path_safe"


def _release_signing_evidence_has_certificate_preflight(evidence: dict[str, Any]) -> bool:
    return _release_signing_evidence_certificate_preflight_detail(evidence) == "certificate_preflight_passed"


def _release_signing_evidence_certificate_preflight_detail(evidence: dict[str, Any]) -> str:
    if evidence.get("certificate_preflight_required_for_execute") is not True:
        return "certificate_preflight_required_missing"
    certificate = evidence.get("certificate_evidence")
    if not isinstance(certificate, dict):
        return "certificate_evidence_missing"
    required = {
        "found": True,
        "not_self_signed": True,
        "not_expired": True,
        "has_private_key": True,
        "code_signing_eku": True,
    }
    failures = [
        key
        for key, expected in required.items()
        if certificate.get(key) is not expected
    ]
    if not str(certificate.get("subject") or "").strip():
        failures.append("subject")
    return "certificate_preflight_passed" if not failures else "certificate_preflight_failed:" + ", ".join(failures)


def _release_signing_certificate_subject(evidence: dict[str, Any]) -> str:
    certificate = evidence.get("certificate_evidence")
    if not isinstance(certificate, dict):
        return ""
    return str(certificate.get("subject") or "").strip()


def _release_signing_certificate_thumbprint_hash(evidence: dict[str, Any]) -> str:
    certificate = evidence.get("certificate_evidence")
    if not isinstance(certificate, dict):
        return ""
    value = certificate.get("thumbprint_sha256")
    normalized = str(value).strip().lower() if isinstance(value, str) else ""
    return normalized if _is_sha256_hex(normalized) else ""


def _target_signer_matches_certificate(item: dict[str, Any], certificate_subject: str) -> bool:
    signer = str(item.get("signer") or "").strip()
    if not signer or not certificate_subject:
        return False
    return signer == certificate_subject


def _target_signer_thumbprint_matches_certificate(item: dict[str, Any], evidence: dict[str, Any]) -> bool:
    signer_thumbprint_hash = str(item.get("signer_thumbprint_sha256") or "").strip().lower()
    certificate_thumbprint_hash = _release_signing_certificate_thumbprint_hash(evidence)
    return (
        _is_sha256_hex(signer_thumbprint_hash)
        and bool(certificate_thumbprint_hash)
        and signer_thumbprint_hash == certificate_thumbprint_hash
    )


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _is_sha1_thumbprint(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdefABCDEF" for char in value)


def _hashes_match(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return _is_sha256_hex(left) and _is_sha256_hex(right) and left.lower() == right.lower()


def _flag_value(command: list[str], flag: str) -> str:
    try:
        index = command.index(flag)
    except ValueError:
        return ""
    next_index = index + 1
    if next_index >= len(command):
        return ""
    return command[next_index]


def _normalize_thumbprint(value: str) -> str:
    return "".join(value.split()).upper()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _signing_evidence_clean_machine_hash_match(path: Path, clean_machine: dict[str, Any]) -> bool:
    marker_hash = _clean_machine_signing_evidence_hash(clean_machine)
    actual_hash = _sha256_file(path)
    return _hashes_match(marker_hash, actual_hash)


def _signing_evidence_clean_machine_hash_detail(path: Path, clean_machine: dict[str, Any]) -> str:
    marker_hash = _clean_machine_signing_evidence_hash(clean_machine)
    actual_hash = _sha256_file(path)
    if not marker_hash:
        return "clean_machine_marker_missing_signing_evidence_sha256"
    if not actual_hash:
        return f"signing_evidence_missing:{path}"
    if not _is_sha256_hex(marker_hash):
        return "clean_machine_marker_invalid_signing_evidence_sha256"
    if not _is_sha256_hex(actual_hash):
        return "signing_evidence_invalid_sha256"
    return "match" if marker_hash.lower() == actual_hash.lower() else "sha256_mismatch"


def _clean_machine_signing_evidence_hash(clean_machine: dict[str, Any]) -> str:
    payload = clean_machine.get("external_validation_payload")
    if isinstance(payload, dict):
        value = payload.get("signing_evidence_sha256")
        return str(value) if isinstance(value, str) else ""
    return ""


def _clean_machine_transfer_manifest_hash_match(bundle: dict[str, Any], clean_machine: dict[str, Any]) -> bool:
    marker_hash = _clean_machine_transfer_manifest_hash(clean_machine)
    bundle_hash = _bundle_transfer_manifest_file_hash(bundle)
    return _hashes_match(marker_hash, bundle_hash)


def _clean_machine_transfer_manifest_hash_detail(bundle: dict[str, Any], clean_machine: dict[str, Any]) -> str:
    marker_hash = _clean_machine_transfer_manifest_hash(clean_machine)
    bundle_hash = _bundle_transfer_manifest_file_hash(bundle)
    if not marker_hash:
        return "clean_machine_marker_missing_release_transfer_manifest_sha256"
    if not bundle_hash:
        return "bundle_missing_release_transfer_manifest_sha256"
    if not _is_sha256_hex(marker_hash):
        return "clean_machine_marker_invalid_release_transfer_manifest_sha256"
    if not _is_sha256_hex(bundle_hash):
        return "bundle_invalid_release_transfer_manifest_sha256"
    return "match" if marker_hash.lower() == bundle_hash.lower() else "sha256_mismatch"


def _clean_machine_transfer_manifest_aggregate_hash_match(bundle: dict[str, Any], clean_machine: dict[str, Any]) -> bool:
    marker_hash = _clean_machine_transfer_manifest_aggregate_hash(clean_machine)
    bundle_hash = _bundle_transfer_manifest_aggregate_hash(bundle)
    return _hashes_match(marker_hash, bundle_hash)


def _clean_machine_transfer_manifest_aggregate_hash_detail(bundle: dict[str, Any], clean_machine: dict[str, Any]) -> str:
    marker_hash = _clean_machine_transfer_manifest_aggregate_hash(clean_machine)
    bundle_hash = _bundle_transfer_manifest_aggregate_hash(bundle)
    if not marker_hash:
        return "clean_machine_marker_missing_release_transfer_manifest_aggregate_sha256"
    if not bundle_hash:
        return "bundle_missing_release_transfer_manifest_aggregate_sha256"
    if not _is_sha256_hex(marker_hash):
        return "clean_machine_marker_invalid_release_transfer_manifest_aggregate_sha256"
    if not _is_sha256_hex(bundle_hash):
        return "bundle_invalid_release_transfer_manifest_aggregate_sha256"
    return "match" if marker_hash.lower() == bundle_hash.lower() else "sha256_mismatch"


def _clean_machine_transfer_manifest_hash(clean_machine: dict[str, Any]) -> str:
    payload = clean_machine.get("external_validation_payload")
    if isinstance(payload, dict):
        value = payload.get("release_transfer_manifest_sha256")
        return str(value) if isinstance(value, str) else ""
    return ""


def _clean_machine_transfer_manifest_aggregate_hash(clean_machine: dict[str, Any]) -> str:
    payload = clean_machine.get("external_validation_payload")
    if isinstance(payload, dict):
        value = payload.get("release_transfer_manifest_aggregate_sha256")
        return str(value) if isinstance(value, str) else ""
    return ""


def _bundle_transfer_manifest_file_hash(bundle: dict[str, Any]) -> str:
    value = bundle.get("transfer_manifest_file_sha256")
    return str(value) if isinstance(value, str) else ""


def _bundle_transfer_manifest_aggregate_hash(bundle: dict[str, Any]) -> str:
    transfer = bundle.get("transfer_manifest")
    if isinstance(transfer, dict):
        value = transfer.get("aggregate_sha256")
        return str(value) if isinstance(value, str) else ""
    return ""


def _bundle_release_command_contract(bundle: dict[str, Any]) -> dict[str, Any]:
    transfer = bundle.get("transfer_manifest")
    if not isinstance(transfer, dict):
        return {}
    contract = transfer.get("release_command_contract")
    return contract if isinstance(contract, dict) else {}


def _bundle_release_command_contract_ready(bundle: dict[str, Any]) -> bool:
    return _bundle_release_command_contract_detail(bundle) == "contract_ready"


def _bundle_release_command_contract_detail(bundle: dict[str, Any]) -> str:
    contract = _bundle_release_command_contract(bundle)
    if not contract:
        return "release_command_contract_missing"
    failures: list[str] = []
    if contract.get("version") != "18.9.17":
        failures.append("version")
    expected_flags = {
        "commands_are_templates": True,
        "placeholder_must_be_replaced": True,
        "repo_root_final_verifier_required": True,
    }
    failures.extend(key for key, expected in expected_flags.items() if contract.get(key) is not expected)
    if contract.get("thumbprint_placeholder") != "<CERT_THUMBPRINT>":
        failures.append("thumbprint_placeholder")
    if contract.get("thumbprint_regex") != "^[0-9A-Fa-f]{40}$":
        failures.append("thumbprint_regex")
    hashes = contract.get("command_sha256")
    if not isinstance(hashes, dict):
        failures.append("command_sha256")
    else:
        for key in _RELEASE_COMMAND_CONTRACT_HASH_KEYS:
            value = hashes.get(key)
            if not isinstance(value, str) or not _is_sha256_hex(value):
                failures.append(f"command_sha256:{key}")
    return "contract_ready" if not failures else "contract_invalid:" + ", ".join(failures)


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _next_step(blockers: list[dict[str, Any]]) -> str:
    ids = {blocker["id"] for blocker in blockers}
    if not blockers:
        return "Run scripts/runtime/verify_final_release.py and preserve final artifacts."
    if "handoff_bundle" in ids:
        return "Regenerate and verify outputs/release_candidates/ANN_RC_HANDOFF."
    if "handoff_installer_hash_match" in ids:
        return "Use the exact ANN_Setup.exe and ANN_Uninstall.exe from the verified handoff bundle as installer-root."
    if "signed_installer" in ids:
        return "Sign ANN_Setup.exe and ANN_Uninstall.exe with a trusted Authenticode certificate."
    if "release_signing_evidence" in ids:
        return "Run installer/sign_release.ps1 with -OutputPath installer/release_signing_evidence.json -Execute on the signing machine."
    if "clean_machine_signing_evidence_hash_match" in ids:
        return "Run validate_clean_machine.ps1 with -SigningEvidencePath pointing to the preserved release_signing_evidence.json."
    if "clean_machine_transfer_manifest_hash_match" in ids:
        return "Run validate_clean_machine.ps1 with -ReleaseTransferManifestPath pointing to RELEASE_TRANSFER_MANIFEST.json."
    if "release_command_contract" in ids:
        return "Regenerate and verify the release-candidate handoff bundle so RELEASE_TRANSFER_MANIFEST.json includes the command contract."
    if "external_clean_machine" in ids or "external_marker_strong" in ids:
        return "Run installer/validate_clean_machine.ps1 on a separate clean Windows 11 machine with -RequireSignedInstaller."
    if "clean_machine_installer_hash_match" in ids:
        return "Re-run clean-machine validation with the exact signed installer binaries from this handoff bundle."
    if "clean_machine_signer_thumbprint_match" in ids:
        return "Re-run clean-machine validation with the same signed binaries and release_signing_evidence.json certificate thumbprint."
    return f"Resolve external evidence blocker: {blockers[0]['id']}"


def _summary(report: dict[str, Any]) -> str:
    blocker_ids = ", ".join(str(blocker["id"]) for blocker in report["blockers"]) or "none"
    return "\n".join(
        [
            "ANN External Release Evidence Verification",
            f"Status: {report['status']}",
            f"Handoff Bundle: {report['bundle']['status']}",
            f"Handoff Installer Hash Match: {_pass_fail(report['installer_hashes_match_handoff'])}",
            f"Signing: {report['signing']['status']}",
            f"Signed Installer: {_pass_fail(report['signing'].get('signed_installer') is True)}",
            f"Authenticode Timestamp: {_timestamp_summary(report['signing'])}",
            f"Release Signing Evidence: {_pass_fail(report['release_signing_evidence_valid'])}",
            f"Clean-Machine Signing Evidence Hash Match: {_pass_fail(report['clean_machine_signing_evidence_hash_match'])}",
            f"Clean-Machine Transfer Manifest Hash Match: {_pass_fail(report['clean_machine_transfer_manifest_hash_match'])}",
            f"Clean-Machine Transfer Manifest Aggregate Match: {_pass_fail(report['clean_machine_transfer_manifest_aggregate_hash_match'])}",
            f"Release Command Contract: {_pass_fail(report['release_command_contract_ready'])}",
            f"Clean Machine: {report['clean_machine']['status']}",
            f"Clean-Machine Installer Hash Match: {_pass_fail(report['installer_hashes_match_clean_machine'])}",
            f"Clean-Machine Signer Thumbprint Match: {_pass_fail(report['clean_machine_signer_thumbprint_match'])}",
            f"Blockers: {blocker_ids}",
            f"Next Step: {report['next_step']}",
        ]
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ANN External Release Evidence Verification",
        "",
        f"- Status: `{report['status']}`",
        f"- Handoff Bundle: `{report['bundle']['status']}`",
        f"- Handoff Installer Hash Match: `{_pass_fail(report['installer_hashes_match_handoff'])}`",
        f"- Signing: `{report['signing']['status']}`",
        f"- Signed Installer: `{_pass_fail(report['signing'].get('signed_installer') is True)}`",
        f"- Authenticode Timestamp: `{_timestamp_summary(report['signing'])}`",
        f"- Release Signing Evidence: `{_pass_fail(report['release_signing_evidence_valid'])}`",
        f"- Clean-Machine Signing Evidence Hash Match: `{_pass_fail(report['clean_machine_signing_evidence_hash_match'])}`",
        f"- Clean-Machine Transfer Manifest Hash Match: `{_pass_fail(report['clean_machine_transfer_manifest_hash_match'])}`",
        f"- Clean-Machine Transfer Manifest Aggregate Match: `{_pass_fail(report['clean_machine_transfer_manifest_aggregate_hash_match'])}`",
        f"- Release Command Contract: `{_pass_fail(report['release_command_contract_ready'])}`",
        f"- Clean Machine: `{report['clean_machine']['status']}`",
        f"- Clean-Machine Installer Hash Match: `{_pass_fail(report['installer_hashes_match_clean_machine'])}`",
        f"- Clean-Machine Signer Thumbprint Match: `{_pass_fail(report['clean_machine_signer_thumbprint_match'])}`",
        f"- Next Step: {report['next_step']}",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"- `{check['id']}`: {check['status']} ({check['detail']})")
    lines.append("")
    return "\n".join(lines)


def _pass_fail(value: bool) -> str:
    return "PASS" if value else "BLOCKED"


def _timestamp_summary(signing: dict[str, Any]) -> str:
    missing = signing.get("untimestamped_binaries")
    if isinstance(missing, list) and missing:
        return "BLOCKED_MISSING_TIMESTAMP"
    if signing.get("signed_installer") is True:
        return "PASS"
    return "BLOCKED"


if __name__ == "__main__":
    sys.exit(main())
