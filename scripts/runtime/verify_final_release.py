"""Read-only final release verifier for ANN.

This script aggregates existing ANN release gates and exits 0 only when the
product is genuinely FINAL_RELEASE_READY. It does not install packages,
download files, load models, run inference, or sign binaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_release_signing_plan,
    build_final_release_verification_report,
    write_release_signing_plan_artifacts,
    write_final_release_verification_artifacts,
)
from scripts.runtime.verify_external_release_evidence import (
    build_external_release_evidence_report,
    write_external_release_evidence_artifacts,
)
from scripts.runtime.verify_release_operator_environment import (
    build_release_operator_environment_report,
    write_release_operator_environment_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN final release readiness.")
    parser.add_argument("--runtime-root", default=None, help="Runtime root, defaults to D:/ANN/runtime.")
    parser.add_argument("--install-root", default="D:/ANN", help="Installed ANN root containing clean-machine evidence.")
    parser.add_argument("--installer-root", default="installer", help="Directory containing ANN_Setup.exe and ANN_Uninstall.exe.")
    parser.add_argument(
        "--bundle-root",
        default="outputs/release_candidates/ANN_RC_HANDOFF",
        help="Verified release-candidate handoff bundle.",
    )
    parser.add_argument(
        "--clean-machine-marker",
        default=None,
        help="Optional copied clean_machine_external_validation.json from the external Windows 11 validation machine.",
    )
    parser.add_argument(
        "--signing-evidence",
        default=None,
        help="Optional release_signing_evidence.json produced by installer/sign_release.ps1.",
    )
    parser.add_argument(
        "--certificate-thumbprint",
        default="",
        help="Optional trusted Authenticode certificate thumbprint for read-only release-operator preflight.",
    )
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def _summary(report: dict[str, object]) -> str:
    blockers = report.get("blockers")
    blocker_ids = []
    if isinstance(blockers, list):
        blocker_ids = [str(item.get("id", "unknown")) for item in blockers if isinstance(item, dict)]
    lines = [
        "ANN Final Release Verification",
        f"Status: {report.get('status')}",
        f"Runtime Materialization: {report.get('runtime_materialization')}",
        f"Wheelhouse Integrity: {report.get('wheelhouse_integrity')}",
        f"Embedded Package Audit: {report.get('embedded_package_audit')}",
        f"Installer RC: {report.get('installer_rc')}",
        f"Autonomous Complex Capability: {report.get('autonomous_complex_capability')}",
        f"Installer Final: {report.get('installer_final')}",
        f"Public Release: {report.get('public_release')}",
        f"ANN Finalization: {report.get('ann_finalization')}",
        f"Signed Installer: {report.get('signed_installer')}",
        f"External Clean Machine: {report.get('external_clean_machine_passed')}",
        f"External Release Evidence: {report.get('external_release_evidence')}",
        f"External Handoff Hash Match: {_external_pass_fail(report, 'installer_hashes_match_handoff')}",
        f"External Clean-Machine Hash Match: {_external_pass_fail(report, 'installer_hashes_match_clean_machine')}",
        f"External Release Signing Evidence: {_external_pass_fail(report, 'release_signing_evidence_valid')}",
        f"External Clean-Machine Signing Evidence Hash Match: {_external_pass_fail(report, 'clean_machine_signing_evidence_hash_match')}",
        f"External Clean-Machine Transfer Manifest Hash Match: {_external_pass_fail(report, 'clean_machine_transfer_manifest_hash_match')}",
        f"External Clean-Machine Transfer Manifest Aggregate Match: {_external_pass_fail(report, 'clean_machine_transfer_manifest_aggregate_hash_match')}",
        f"External Release Command Contract: {_external_pass_fail(report, 'release_command_contract_ready')}",
        f"External Clean-Machine Signer Thumbprint Match: {_external_pass_fail(report, 'clean_machine_signer_thumbprint_match')}",
        f"External Signing: {_external_nested_status(report, 'signing')}",
        f"External Clean-Machine Evidence: {_external_nested_status(report, 'clean_machine')}",
        f"Release Operator Environment: {_operator_nested_status(report)}",
        f"Operator/Signing Thumbprint Match: {_pass_fail(report.get('release_operator_signing_thumbprint_match') is True)}",
        f"Release Evidence Contract: {_pass_fail(report.get('release_evidence_contract_ready') is True)}",
        f"Final Release Path Contract: {_pass_fail(report.get('final_release_path_contract_ready') is True)}",
        f"Release Signing Plan: {_release_signing_plan_status(report)}",
        f"Release Signing Plan Safety: {_pass_fail(report.get('release_signing_plan_safety_ready') is True)}",
        f"External Evidence Safety: {_pass_fail(report.get('external_release_evidence_safety_ready') is True)}",
        f"Operator Environment Safety: {_pass_fail(report.get('release_operator_environment_safety_ready') is True)}",
        f"Blockers: {', '.join(blocker_ids) if blocker_ids else 'none'}",
        f"Next Step: {report.get('next_step')}",
    ]
    return "\n".join(lines)


def build_cli_final_release_report(
    *,
    runtime_root: str | Path | None = None,
    install_root: str | Path = "D:/ANN",
    installer_root: str | Path = "installer",
    bundle_root: str | Path = "outputs/release_candidates/ANN_RC_HANDOFF",
    clean_machine_marker: str | Path | None = None,
    signing_evidence: str | Path | None = None,
    certificate_thumbprint: str = "",
) -> dict[str, object]:
    base = build_final_release_verification_report(runtime_root)
    signing_plan = build_release_signing_plan(installer_root)
    external = build_external_release_evidence_report(
        install_root=install_root,
        installer_root=installer_root,
        bundle_root=bundle_root,
        clean_machine_marker=clean_machine_marker,
        signing_evidence=signing_evidence,
    )
    operator = build_release_operator_environment_report(
        installer_root=installer_root,
        certificate_thumbprint=certificate_thumbprint,
    )
    certificate_thumbprint_format_detail = _certificate_thumbprint_format_detail(certificate_thumbprint)
    path_contract = _final_release_path_contract(
        installer_root=installer_root,
        bundle_root=bundle_root,
        clean_machine_marker=clean_machine_marker,
        signing_evidence=signing_evidence,
    )
    path_contract_ready = _final_release_path_contract_ready(path_contract)
    operator_contract = _release_operator_evidence_contract(
        external=external,
        operator=operator,
        signing_plan=signing_plan,
        certificate_thumbprint=certificate_thumbprint,
    )
    external_ready = external["status"] == "EXTERNAL_RELEASE_EVIDENCE_READY"
    operator_ready = operator.get("status") == "RELEASE_OPERATOR_ENV_READY"
    signing_plan_ready = _release_signing_plan_ready(signing_plan)
    signing_plan_safety_ready = _release_signing_plan_safety_ready(signing_plan)
    external_safety_ready = _external_release_evidence_safety_ready(external)
    operator_safety_ready = _release_operator_environment_safety_ready(operator)
    operator_signing_thumbprint_match = _operator_signing_thumbprint_hash_match(external, operator)
    contract_ready = _release_evidence_contract_ready(operator_contract)
    blockers = list(base.get("blockers") or [])
    if not path_contract_ready:
        blockers.append(
            {
                "id": "final_release_path_contract",
                "status": "BLOCKED",
                "passed": False,
                "detail": _final_release_path_contract_detail(path_contract),
            }
        )
    if not signing_plan_ready:
        blockers.append(
            {
                "id": "release_signing_plan",
                "status": "BLOCKED",
                "passed": False,
                "detail": str(signing_plan.get("status", "UNKNOWN")),
            }
        )
    if not signing_plan_safety_ready:
        blockers.append(
            {
                "id": "release_signing_plan_safety",
                "status": "BLOCKED",
                "passed": False,
                "detail": _release_signing_plan_safety_detail(signing_plan),
            }
        )
    if not external_ready:
        blockers.append(
            {
                "id": "external_release_evidence",
                "status": "BLOCKED",
                "passed": False,
                "detail": external["status"],
            }
        )
    if not external_safety_ready:
        blockers.append(
            {
                "id": "external_release_evidence_safety",
                "status": "BLOCKED",
                "passed": False,
                "detail": _external_release_evidence_safety_detail(external),
            }
        )
    if not operator_ready:
        blockers.append(
            {
                "id": "release_operator_environment",
                "status": "BLOCKED",
                "passed": False,
                "detail": str(operator.get("status", "UNKNOWN")),
            }
        )
    if not operator_safety_ready:
        blockers.append(
            {
                "id": "release_operator_environment_safety",
                "status": "BLOCKED",
                "passed": False,
                "detail": _release_operator_environment_safety_detail(operator),
            }
        )
    if certificate_thumbprint_format_detail != "thumbprint_format_valid":
        blockers.append(
            {
                "id": "certificate_thumbprint_format",
                "status": "BLOCKED",
                "passed": False,
                "detail": certificate_thumbprint_format_detail,
            }
        )
    if external_ready and operator_ready and not operator_signing_thumbprint_match:
        blockers.append(
            {
                "id": "release_operator_signing_thumbprint_match",
                "status": "BLOCKED",
                "passed": False,
                "detail": _operator_signing_thumbprint_match_detail(external, operator),
            }
        )
    if external_ready and operator_ready and operator_signing_thumbprint_match and not contract_ready:
        blockers.append(
            {
                "id": "release_evidence_contract",
                "status": "BLOCKED",
                "passed": False,
                "detail": _release_evidence_contract_blocker_detail(operator_contract),
            }
        )
    status = (
        "FINAL_RELEASE_READY"
        if (
            base.get("status") == "FINAL_RELEASE_READY"
            and path_contract_ready
            and signing_plan_ready
            and signing_plan_safety_ready
            and external_ready
            and external_safety_ready
            and operator_ready
            and operator_safety_ready
            and operator_signing_thumbprint_match
            and contract_ready
        )
        else "FINAL_RELEASE_BLOCKED"
    )
    report = dict(base)
    report.update(
        {
            "status": status,
            "exit_code": 0 if status == "FINAL_RELEASE_READY" else 2,
            "blockers": blockers,
            "external_release_evidence": external["status"],
            "external_release_evidence_ready": external_ready,
            "external_release_evidence_blockers": external.get("blockers", []),
            "external_release_evidence_report": external,
            "final_release_path_contract": path_contract,
            "final_release_path_contract_ready": path_contract_ready,
            "release_signing_plan": signing_plan,
            "release_signing_plan_status": signing_plan.get("status"),
            "release_signing_plan_ready": signing_plan_ready,
            "release_signing_plan_safety_ready": signing_plan_safety_ready,
            "release_signing_commands": signing_plan.get("commands", []),
            "release_operator_environment": operator,
            "release_operator_environment_status": operator.get("status"),
            "release_operator_environment_safety_ready": operator_safety_ready,
            "release_operator_environment_blockers": operator.get("blockers", []),
            "external_release_evidence_safety_ready": external_safety_ready,
            "clean_machine_signer_thumbprint_match": external.get("clean_machine_signer_thumbprint_match"),
            "release_evidence_contract_ready": contract_ready,
            "release_evidence_contract_blocker_detail": _release_evidence_contract_blocker_detail(operator_contract),
            "release_operator_signing_thumbprint_match": operator_signing_thumbprint_match,
            "release_operator_signing_thumbprint_match_detail": _operator_signing_thumbprint_match_detail(
                external,
                operator,
            ),
            "certificate_thumbprint_format_detail": certificate_thumbprint_format_detail,
            "release_operator_environment_command": _release_operator_environment_command(certificate_thumbprint),
            "release_operator_evidence_contract": operator_contract,
            "no_external_signing": True,
            "no_external_install": True,
        }
    )
    if certificate_thumbprint_format_detail != "thumbprint_format_valid":
        report["next_step"] = "Pass the real 40-character hexadecimal SHA1 Authenticode certificate thumbprint to the final verifier."
    elif not path_contract_ready:
        report["next_step"] = "Use the canonical final release evidence paths before verification."
    elif not signing_plan_ready:
        report["next_step"] = "Restore the release signing plan before final release verification."
    elif not signing_plan_safety_ready:
        report["next_step"] = "Restore release signing plan safety flags before final release verification."
    elif not external_ready:
        report["next_step"] = external["next_step"]
    elif not external_safety_ready:
        report["next_step"] = "Restore external release evidence safety flags before final release verification."
    elif not operator_ready:
        report["next_step"] = operator.get("next_step", "Resolve release operator environment blockers.")
    elif not operator_safety_ready:
        report["next_step"] = "Restore release operator environment safety flags before final release verification."
    elif not operator_signing_thumbprint_match:
        report["next_step"] = "Run release signing and final verification with the same trusted certificate thumbprint."
    elif not contract_ready:
        report["next_step"] = "Resolve release evidence contract blockers before final release."
    return report


def write_cli_final_release_artifacts(report: dict[str, object], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "372_final_release_cli_verification.json"
    md_path = target / "373_final_release_cli_verification.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_cli_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_cli_final_release_report(
        runtime_root=args.runtime_root,
        install_root=args.install_root,
        installer_root=args.installer_root,
        bundle_root=args.bundle_root,
        clean_machine_marker=args.clean_machine_marker,
        signing_evidence=args.signing_evidence,
        certificate_thumbprint=args.certificate_thumbprint,
    )
    if args.output_dir:
        write_final_release_verification_artifacts(Path(args.output_dir))
        write_release_signing_plan_artifacts(Path(args.output_dir), args.installer_root)
        external_report = report.get("external_release_evidence_report")
        if isinstance(external_report, dict):
            write_external_release_evidence_artifacts(external_report, Path(args.output_dir))
        operator_report = report.get("release_operator_environment")
        if isinstance(operator_report, dict):
            write_release_operator_environment_artifacts(operator_report, Path(args.output_dir))
        write_cli_final_release_artifacts(report, Path(args.output_dir))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_summary(report))
    return int(report["exit_code"])


def _cli_markdown(report: dict[str, object]) -> str:
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    lines = [
        "# ANN Final Release CLI Verification",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Base Final Release: `{report.get('ann_finalization')}`",
        f"- External Release Evidence: `{report.get('external_release_evidence')}`",
        f"- External Handoff Hash Match: `{_external_pass_fail(report, 'installer_hashes_match_handoff')}`",
        f"- External Clean-Machine Hash Match: `{_external_pass_fail(report, 'installer_hashes_match_clean_machine')}`",
        f"- External Release Signing Evidence: `{_external_pass_fail(report, 'release_signing_evidence_valid')}`",
        f"- External Clean-Machine Signing Evidence Hash Match: `{_external_pass_fail(report, 'clean_machine_signing_evidence_hash_match')}`",
        f"- External Clean-Machine Transfer Manifest Hash Match: `{_external_pass_fail(report, 'clean_machine_transfer_manifest_hash_match')}`",
        f"- External Clean-Machine Transfer Manifest Aggregate Match: `{_external_pass_fail(report, 'clean_machine_transfer_manifest_aggregate_hash_match')}`",
        f"- External Release Command Contract: `{_external_pass_fail(report, 'release_command_contract_ready')}`",
        f"- External Clean-Machine Signer Thumbprint Match: `{_external_pass_fail(report, 'clean_machine_signer_thumbprint_match')}`",
        f"- External Signing: `{_external_nested_status(report, 'signing')}`",
        f"- External Clean-Machine Evidence: `{_external_nested_status(report, 'clean_machine')}`",
        f"- Release Operator Environment: `{_operator_nested_status(report)}`",
        f"- Operator/Signing Thumbprint Match: `{_pass_fail(report.get('release_operator_signing_thumbprint_match') is True)}`",
        f"- Release Evidence Contract: `{_pass_fail(report.get('release_evidence_contract_ready') is True)}`",
        f"- Final Release Path Contract: `{_pass_fail(report.get('final_release_path_contract_ready') is True)}`",
        f"- Release Signing Plan: `{_release_signing_plan_status(report)}`",
        f"- Release Signing Plan Safety: `{_pass_fail(report.get('release_signing_plan_safety_ready') is True)}`",
        f"- External Evidence Safety: `{_pass_fail(report.get('external_release_evidence_safety_ready') is True)}`",
        f"- Operator Environment Safety: `{_pass_fail(report.get('release_operator_environment_safety_ready') is True)}`",
        f"- Next Step: {report.get('next_step')}",
        "",
        "## Final Release Path Contract",
        "",
        "| Input | Status | Expected | Actual |",
        "| --- | --- | --- | --- |",
        *_final_release_path_contract_markdown_rows(report),
        "",
        "## Release Safety Invariants",
        "",
        "| Area | Status | Required invariants |",
        "| --- | --- | --- |",
        (
            "| `release_signing_plan` | "
            f"`{_pass_fail(report.get('release_signing_plan_safety_ready') is True)}` | "
            "`commands_are_templates`, `placeholder_must_be_replaced`, "
            "`sign_release_blocks_placeholder`, `no_signing_performed`, "
            "`no_download`, `no_install`, `no_self_signed_certificate` |"
        ),
        (
            "| `external_release_evidence` | "
            f"`{_pass_fail(report.get('external_release_evidence_safety_ready') is True)}` | "
            "`no_install`, `no_download`, `no_signing`, `no_model_load`, `no_inference` |"
        ),
        (
            "| `release_operator_environment` | "
            f"`{_pass_fail(report.get('release_operator_environment_safety_ready') is True)}` | "
            "`no_signing`, `no_install`, `no_download`, `no_model_load`, `no_inference`, `no_shell` |"
        ),
        "",
        "## Release Operator Commands",
        "",
    ]
    operator_command = report.get("release_operator_environment_command")
    if isinstance(operator_command, str) and operator_command:
        lines.append(f"- `{operator_command}`")
    commands = report.get("release_signing_commands")
    if isinstance(commands, list) and commands:
        for command in commands:
            lines.append(f"- `{command}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Release Evidence Contract",
            "",
            "| Evidence | Status | Producer | Verifier |",
            "| --- | --- | --- | --- |",
        ]
    )
    contract = report.get("release_operator_evidence_contract")
    if isinstance(contract, list) and contract:
        for item in contract:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('id')}` | "
                f"`{item.get('status')}` | "
                f"`{item.get('producer_command')}` | "
                f"`{item.get('verifier_command')}` |"
            )
    else:
        lines.append("| none | `UNKNOWN` | none | none |")
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    if blockers:
        for blocker in blockers:
            if isinstance(blocker, dict):
                lines.append(f"- `{blocker.get('id')}`: {blocker.get('detail')}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _external_report(report: dict[str, object]) -> dict[str, object]:
    external = report.get("external_release_evidence_report")
    return external if isinstance(external, dict) else {}


def _external_pass_fail(report: dict[str, object], key: str) -> str:
    value = _external_report(report).get(key)
    return "PASS" if value is True else "BLOCKED"


def _pass_fail(value: bool) -> str:
    return "PASS" if value else "BLOCKED"


def _external_nested_status(report: dict[str, object], key: str) -> str:
    nested = _external_report(report).get(key)
    if isinstance(nested, dict):
        return str(nested.get("status", "UNKNOWN"))
    return "UNKNOWN"


def _release_evidence_contract_ready(contract: list[dict[str, object]]) -> bool:
    required = [item for item in contract if item.get("required_for_final_release") is True]
    return bool(required) and all(item.get("status") == "PASS" for item in required)


def _release_evidence_contract_blocker_detail(contract: list[dict[str, object]]) -> str:
    blocked = [
        str(item.get("id", "unknown"))
        for item in contract
        if item.get("required_for_final_release") is True and item.get("status") != "PASS"
    ]
    return "match" if not blocked else ", ".join(blocked)


def _operator_signing_thumbprint_hash_match(
    external: dict[str, object],
    operator: dict[str, object],
) -> bool:
    operator_hash = _operator_thumbprint_hash(operator)
    signing_hash = _external_signing_thumbprint_hash(external)
    return bool(operator_hash) and bool(signing_hash) and operator_hash == signing_hash


def _operator_signing_thumbprint_match_detail(
    external: dict[str, object],
    operator: dict[str, object],
) -> str:
    operator_hash = _operator_thumbprint_hash(operator)
    signing_hash = _external_signing_thumbprint_hash(external)
    if not operator_hash:
        return "operator_thumbprint_sha256_missing"
    if not signing_hash:
        return "signing_evidence_thumbprint_sha256_missing"
    return "match" if operator_hash == signing_hash else "thumbprint_sha256_mismatch"


def _operator_thumbprint_hash(operator: dict[str, object]) -> str:
    value = operator.get("certificate_thumbprint_sha256")
    return str(value).strip().lower() if isinstance(value, str) else ""


def _external_signing_thumbprint_hash(external: dict[str, object]) -> str:
    evidence = external.get("release_signing_evidence")
    if not isinstance(evidence, dict):
        return ""
    certificate = evidence.get("certificate_evidence")
    if not isinstance(certificate, dict):
        return ""
    value = certificate.get("thumbprint_sha256")
    return str(value).strip().lower() if isinstance(value, str) else ""


def _thumbprint_sha256(value: str) -> str:
    normalized = "".join(str(value).split()).upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _certificate_thumbprint_format_detail(value: str) -> str:
    normalized = "".join(str(value).split()).upper()
    if not normalized:
        return "thumbprint_missing"
    if normalized in {"<CERT_THUMBPRINT>", "CERT_THUMBPRINT"}:
        return "thumbprint_placeholder_blocked"
    if len(normalized) != 40:
        return "thumbprint_must_be_40_hex_chars"
    if any(char not in "0123456789ABCDEF" for char in normalized):
        return "thumbprint_non_hex_chars"
    return "thumbprint_format_valid"


def _release_signing_plan_status(report: dict[str, object]) -> str:
    plan = report.get("release_signing_plan")
    if isinstance(plan, dict):
        return str(plan.get("status", "UNKNOWN"))
    return str(report.get("release_signing_plan_status", "UNKNOWN"))


def _final_release_path_contract(
    *,
    installer_root: str | Path,
    bundle_root: str | Path,
    clean_machine_marker: str | Path | None,
    signing_evidence: str | Path | None,
) -> list[dict[str, object]]:
    checks = [
        _path_contract_item("installer_root", "installer", str(installer_root), allow_default=False),
        _path_contract_item(
            "bundle_root",
            "outputs/release_candidates/ANN_RC_HANDOFF",
            str(bundle_root),
            allow_default=False,
        ),
        _path_contract_item(
            "signing_evidence",
            "installer/release_signing_evidence.json",
            str(signing_evidence) if signing_evidence is not None else "",
            allow_default=True,
        ),
        _path_contract_item(
            "clean_machine_marker",
            "D:/ANN/clean_machine_external_validation.json",
            str(clean_machine_marker) if clean_machine_marker is not None else "",
            allow_default=True,
        ),
    ]
    return checks


def _path_contract_item(
    name: str,
    expected: str,
    actual: str,
    *,
    allow_default: bool,
) -> dict[str, object]:
    normalized_actual = _normalize_release_path(actual)
    normalized_expected = _normalize_release_path(expected)
    defaulted = allow_default and not normalized_actual
    passed = defaulted or normalized_actual == normalized_expected
    return {
        "id": name,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "expected": expected,
        "actual": actual or "<default>",
        "defaulted": defaulted,
    }


def _normalize_release_path(path: str) -> str:
    normalized = str(path).strip().replace("\\", "/").rstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized.lower()


def _final_release_path_contract_ready(contract: list[dict[str, object]]) -> bool:
    return bool(contract) and all(item.get("passed") is True for item in contract)


def _final_release_path_contract_detail(contract: list[dict[str, object]]) -> str:
    blocked = [
        f"{item.get('id')}:{item.get('actual')}"
        for item in contract
        if item.get("passed") is not True
    ]
    return "match" if not blocked else ", ".join(blocked)


def _final_release_path_contract_markdown_rows(report: dict[str, object]) -> list[str]:
    contract = report.get("final_release_path_contract")
    if not isinstance(contract, list) or not contract:
        return ["| none | `UNKNOWN` | none | none |"]
    rows = []
    for item in contract:
        if not isinstance(item, dict):
            continue
        rows.append(
            "| "
            f"`{item.get('id')}` | "
            f"`{item.get('status')}` | "
            f"`{item.get('expected')}` | "
            f"`{item.get('actual')}` |"
        )
    return rows or ["| none | `UNKNOWN` | none | none |"]


def _release_signing_plan_ready(signing_plan: dict[str, object]) -> bool:
    if signing_plan.get("status") != "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE":
        return False
    commands = signing_plan.get("commands")
    if not isinstance(commands, list):
        return False
    command_text = "\n".join(str(command) for command in commands)
    required_fragments = (
        "installer\\sign_release.ps1",
        "-CertificateThumbprint",
        "-TimestampUrl",
        "-OutputPath installer\\release_signing_evidence.json",
        "-Execute",
        "installer\\validate_clean_machine.ps1",
        "-EnvironmentType clean_machine",
        "-RequireSignedInstaller",
        "-SigningEvidencePath installer\\release_signing_evidence.json",
        "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json",
    )
    return all(fragment in command_text for fragment in required_fragments)


def _release_signing_plan_safety_ready(signing_plan: dict[str, object]) -> bool:
    required = {
        "commands_are_templates": True,
        "placeholder_must_be_replaced": True,
        "sign_release_blocks_placeholder": True,
        "no_signing_performed": True,
        "no_download": True,
        "no_install": True,
        "no_self_signed_certificate": True,
    }
    return all(signing_plan.get(key) is expected for key, expected in required.items())


def _release_signing_plan_safety_detail(signing_plan: dict[str, object]) -> str:
    required = (
        "commands_are_templates",
        "placeholder_must_be_replaced",
        "sign_release_blocks_placeholder",
        "no_signing_performed",
        "no_download",
        "no_install",
        "no_self_signed_certificate",
    )
    missing = [key for key in required if signing_plan.get(key) is not True]
    return "match" if not missing else ", ".join(missing)


def _external_release_evidence_safety_ready(external: dict[str, object]) -> bool:
    required = {
        "no_install": True,
        "no_download": True,
        "no_signing": True,
        "no_model_load": True,
        "no_inference": True,
    }
    return all(external.get(key) is expected for key, expected in required.items())


def _external_release_evidence_safety_detail(external: dict[str, object]) -> str:
    required = ("no_install", "no_download", "no_signing", "no_model_load", "no_inference")
    missing = [key for key in required if external.get(key) is not True]
    return "match" if not missing else ", ".join(missing)


def _release_operator_environment_safety_ready(operator: dict[str, object]) -> bool:
    required = {
        "no_signing": True,
        "no_install": True,
        "no_download": True,
        "no_model_load": True,
        "no_inference": True,
        "no_shell": True,
    }
    return all(operator.get(key) is expected for key, expected in required.items())


def _release_operator_environment_safety_detail(operator: dict[str, object]) -> str:
    required = ("no_signing", "no_install", "no_download", "no_model_load", "no_inference", "no_shell")
    missing = [key for key in required if operator.get(key) is not True]
    return "match" if not missing else ", ".join(missing)


def _release_operator_evidence_contract(
    *,
    external: dict[str, object],
    operator: dict[str, object],
    signing_plan: dict[str, object],
    certificate_thumbprint: str = "",
) -> list[dict[str, object]]:
    commands = signing_plan.get("commands")
    command_list = [str(command) for command in commands] if isinstance(commands, list) else []
    sign_command = _first_command_containing(
        command_list,
        "sign_release.ps1",
        required="-Execute",
        fallback=(
            "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
            "-CertificateThumbprint <CERT_THUMBPRINT> "
            "-TimestampUrl http://timestamp.digicert.com "
            "-OutputPath installer\\release_signing_evidence.json -Execute"
        ),
    )
    clean_machine_command = _first_command_containing(
        command_list,
        "validate_clean_machine.ps1",
        fallback=(
            "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
            "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
            "-SigningEvidencePath installer\\release_signing_evidence.json "
            "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
        ),
    )
    final_verifier_command = (
        "PYTHONPATH=. python scripts/runtime/verify_final_release.py "
        "--install-root D:\\ANN --installer-root installer "
        "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF "
        "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
        "--signing-evidence installer\\release_signing_evidence.json "
        f"--certificate-thumbprint {_quote_cli_value(certificate_thumbprint.strip() or '<CERT_THUMBPRINT>')} "
        "--output-dir outputs/runtime_finalization_20260707"
    )
    external_verifier_command = (
        "PYTHONPATH=. python scripts/runtime/verify_external_release_evidence.py "
        "--install-root D:\\ANN --installer-root installer "
        "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF "
        "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
        "--signing-evidence installer\\release_signing_evidence.json"
    )
    operator_command = _release_operator_environment_command(certificate_thumbprint)
    return [
        {
            "id": "release_candidate_handoff_bundle",
            "status": _external_check_status(external, "handoff_bundle"),
            "artifact": "outputs/release_candidates/ANN_RC_HANDOFF/RELEASE_TRANSFER_MANIFEST.json",
            "producer_command": (
                "PYTHONPATH=. python scripts/runtime/prepare_release_candidate_bundle.py "
                "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF"
            ),
            "verifier_command": (
                "PYTHONPATH=. python scripts/runtime/verify_release_candidate_bundle.py "
                "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF"
            ),
            "required_for_final_release": True,
        },
        {
            "id": "release_operator_environment",
            "status": "PASS" if operator.get("status") == "RELEASE_OPERATOR_ENV_READY" else "BLOCKED",
            "artifact": "outputs/runtime_finalization_20260707/374_release_operator_environment.json",
            "producer_command": operator_command,
            "verifier_command": operator_command,
            "required_for_final_release": True,
        },
        {
            "id": "trusted_authenticode_signatures",
            "status": _external_check_status(external, "signed_installer"),
            "artifact": "installer/ANN_Setup.exe, installer/ANN_Uninstall.exe",
            "producer_command": sign_command,
            "verifier_command": "Get-AuthenticodeSignature installer\\ANN_Setup.exe, installer\\ANN_Uninstall.exe",
            "required_for_final_release": True,
        },
        {
            "id": "release_signing_evidence",
            "status": _external_check_status(external, "release_signing_evidence"),
            "artifact": "installer/release_signing_evidence.json",
            "producer_command": sign_command,
            "verifier_command": external_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "operator_signing_thumbprint_lineage",
            "status": "PASS" if _operator_signing_thumbprint_hash_match(external, operator) else "BLOCKED",
            "artifact": (
                "outputs/runtime_finalization_20260707/374_release_operator_environment.json "
                "+ installer/release_signing_evidence.json"
            ),
            "producer_command": sign_command,
            "verifier_command": final_verifier_command,
            "detail": _operator_signing_thumbprint_match_detail(external, operator),
            "required_for_final_release": True,
        },
        {
            "id": "external_clean_machine_validation",
            "status": _external_check_status(external, "external_clean_machine"),
            "artifact": "D:/ANN/clean_machine_external_validation.json",
            "producer_command": clean_machine_command,
            "verifier_command": external_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "clean_machine_installer_hash_lineage",
            "status": _external_check_status(external, "clean_machine_installer_hash_match"),
            "artifact": "D:/ANN/clean_machine_external_validation.json",
            "producer_command": clean_machine_command,
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "clean_machine_signing_evidence_hash_lineage",
            "status": _external_check_or_bool_status(
                external,
                "clean_machine_signing_evidence_hash_match",
                "clean_machine_signing_evidence_hash_match",
            ),
            "artifact": "D:/ANN/clean_machine_external_validation.json + installer/release_signing_evidence.json",
            "producer_command": clean_machine_command,
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "clean_machine_transfer_manifest_hash_lineage",
            "status": _external_check_or_bool_status(
                external,
                "clean_machine_transfer_manifest_hash_match",
                "clean_machine_transfer_manifest_hash_match",
            ),
            "artifact": "D:/ANN/clean_machine_external_validation.json + RELEASE_TRANSFER_MANIFEST.json",
            "producer_command": clean_machine_command,
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "clean_machine_transfer_manifest_aggregate_lineage",
            "status": _external_check_or_bool_status(
                external,
                "clean_machine_transfer_manifest_aggregate_hash_match",
                "clean_machine_transfer_manifest_aggregate_hash_match",
            ),
            "artifact": "D:/ANN/clean_machine_external_validation.json + RELEASE_TRANSFER_MANIFEST.json",
            "producer_command": clean_machine_command,
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "release_command_contract",
            "status": _external_check_or_bool_status(
                external,
                "release_command_contract",
                "release_command_contract_ready",
            ),
            "artifact": "outputs/release_candidates/ANN_RC_HANDOFF/RELEASE_TRANSFER_MANIFEST.json",
            "producer_command": (
                "PYTHONPATH=. python scripts/runtime/prepare_release_candidate_bundle.py "
                "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF"
            ),
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
        {
            "id": "clean_machine_signer_thumbprint_lineage",
            "status": _external_check_status(external, "clean_machine_signer_thumbprint_match"),
            "artifact": "D:/ANN/clean_machine_external_validation.json + installer/release_signing_evidence.json",
            "producer_command": clean_machine_command,
            "verifier_command": final_verifier_command,
            "required_for_final_release": True,
        },
    ]


def _release_operator_environment_command(certificate_thumbprint: str = "") -> str:
    thumbprint = _quote_cli_value(certificate_thumbprint.strip() or "<CERT_THUMBPRINT>")
    return (
        "PYTHONPATH=. python scripts/runtime/verify_release_operator_environment.py "
        f"--installer-root installer --certificate-thumbprint {thumbprint} "
        "--output-dir outputs/runtime_finalization_20260707"
    )


def _operator_nested_status(report: dict[str, object]) -> str:
    operator = report.get("release_operator_environment")
    if isinstance(operator, dict):
        return str(operator.get("status", "UNKNOWN"))
    return str(report.get("release_operator_environment_status", "UNKNOWN"))


def _quote_cli_value(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _first_command_containing(
    commands: list[str],
    needle: str,
    *,
    required: str = "",
    fallback: str = "UNAVAILABLE",
) -> str:
    if required:
        for command in commands:
            if needle in command and required in command:
                return command
    for command in commands:
        if needle in command:
            return command
    return fallback


def _external_check_status(external: dict[str, object], check_id: str) -> str:
    checks = external.get("checks")
    if not isinstance(checks, list):
        return "UNKNOWN"
    for check in checks:
        if isinstance(check, dict) and check.get("id") == check_id:
            return str(check.get("status", "UNKNOWN"))
    return "UNKNOWN"


def _external_check_or_bool_status(
    external: dict[str, object],
    check_id: str,
    bool_key: str,
) -> str:
    status = _external_check_status(external, check_id)
    if status != "UNKNOWN":
        return status
    value = external.get(bool_key)
    if value is True:
        return "PASS"
    if value is False:
        return "BLOCKED"
    return "UNKNOWN"


if __name__ == "__main__":
    sys.exit(main())
