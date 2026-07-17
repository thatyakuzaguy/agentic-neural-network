"""Verify ANN Git/source release readiness without Authenticode requirements.

This channel is for source-first distribution through Git. It intentionally
does not claim Windows trusted-installer status: unsigned launcher artifacts are
allowed only with explicit user approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentic_network.runtime_engine.local_model_activation import (
    build_autonomous_complex_capability_gate,
    build_embedded_runtime_package_audit,
    build_installer_rc_readiness,
    build_runtime_materialization_watcher,
    validate_wheelhouse_integrity,
)
from scripts.runtime.verify_release_candidate_bundle import verify_bundle


REQUIRED_SOURCE_PATHS = (
    "README.md",
    "pyproject.toml",
    "agentic_network",
    "scripts/runtime",
    "tests/python",
    "installer",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN Git/source release readiness.")
    parser.add_argument("--repo-root", default=".", help="ANN repository root.")
    parser.add_argument("--runtime-root", default=None, help="Runtime root, defaults to D:/ANN/runtime.")
    parser.add_argument(
        "--bundle-root",
        default="outputs/release_candidates/ANN_RC_HANDOFF",
        help="Release-candidate handoff bundle to verify.",
    )
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print full verification JSON.")
    return parser


def build_git_source_release_report(
    *,
    repo_root: str | Path = ".",
    runtime_root: str | Path | None = None,
    bundle_root: str | Path = "outputs/release_candidates/ANN_RC_HANDOFF",
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    runtime = build_runtime_materialization_watcher(runtime_root)
    wheelhouse = validate_wheelhouse_integrity(runtime_root)
    package_audit = build_embedded_runtime_package_audit(runtime_root)
    installer_rc = build_installer_rc_readiness()
    autonomous = build_autonomous_complex_capability_gate()
    bundle = verify_bundle(bundle_root)
    checks = [
        _check("source_tree_present", root.is_dir(), str(root)),
        *(_source_path_checks(root)),
        _check("runtime_materialization", runtime.get("status") == "READY", str(runtime.get("status"))),
        _check("wheelhouse_integrity", wheelhouse.get("status") == "HASH_VERIFIED", str(wheelhouse.get("status"))),
        _check(
            "embedded_package_audit",
            package_audit.get("status") == "PACKAGE_AUDIT_READY",
            str(package_audit.get("status")),
        ),
        _check("installer_rc", installer_rc.get("status") == "RC_READY", str(installer_rc.get("status"))),
        _check(
            "autonomous_complex_capability",
            autonomous.get("status") == "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED",
            str(autonomous.get("status")),
        ),
        _check("release_candidate_handoff", bundle.get("status") == "HANDOFF_VERIFIED", str(bundle.get("status"))),
        _check(
            "release_command_contract",
            _release_command_contract_ready(bundle),
            _release_command_contract_detail(bundle),
        ),
        _check("unsigned_installer_allowed", True, "git_source_channel_requires_user_approval"),
        _check("authenticode_not_required", True, "trusted_installer_channel_separate"),
    ]
    blockers = [check for check in checks if not check["passed"]]
    status = "GIT_SOURCE_RELEASE_READY" if not blockers else "GIT_SOURCE_RELEASE_BLOCKED"
    return {
        "version": "19.6",
        "status": status,
        "exit_code": 0 if status == "GIT_SOURCE_RELEASE_READY" else 2,
        "release_channel": "GIT_SOURCE",
        "distribution_model": "source_first_git_distribution",
        "trusted_windows_installer_status": "NOT_CLAIMED",
        "unsigned_installer_status": "USER_APPROVAL_REQUIRED",
        "final_signed_installer_channel": "FINAL_RELEASE_BLOCKED_UNTIL_AUTHENTICODE",
        "repo_root": str(root),
        "runtime_root": str(runtime_root or "D:/ANN/runtime"),
        "bundle_root": str(bundle_root),
        "checks": checks,
        "blockers": blockers,
        "runtime_materialization": runtime.get("status"),
        "wheelhouse_integrity": wheelhouse.get("status"),
        "embedded_package_audit": package_audit.get("status"),
        "installer_rc": installer_rc.get("status"),
        "autonomous_complex_capability": autonomous.get("status"),
        "release_candidate_handoff": bundle.get("status"),
        "release_command_contract_ready": _release_command_contract_ready(bundle),
        "no_authenticode_required": True,
        "no_signing": True,
        "no_install": True,
        "no_download": True,
        "no_model_load": True,
        "no_inference": True,
        "next_step": _next_step(blockers),
    }


def write_git_source_release_artifacts(report: dict[str, Any], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "375_git_source_release_verification.json"
    md_path = target / "376_git_source_release_verification.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_git_source_release_report(
        repo_root=args.repo_root,
        runtime_root=args.runtime_root,
        bundle_root=args.bundle_root,
    )
    if args.output_dir:
        write_git_source_release_artifacts(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_summary(report))
    return int(report["exit_code"])


def _source_path_checks(root: Path) -> list[dict[str, Any]]:
    return [
        _check(
            f"source_path:{relative}",
            (root / relative).exists(),
            str(root / relative),
        )
        for relative in REQUIRED_SOURCE_PATHS
    ]


def _release_command_contract_ready(bundle: dict[str, Any]) -> bool:
    return _release_command_contract_detail(bundle) == "contract_ready"


def _release_command_contract_detail(bundle: dict[str, Any]) -> str:
    transfer = bundle.get("transfer_manifest")
    if not isinstance(transfer, dict):
        return "transfer_manifest_missing"
    contract = transfer.get("release_command_contract")
    if not isinstance(contract, dict):
        return "release_command_contract_missing"
    if contract.get("repo_root_final_verifier_required") is not True:
        return "repo_root_final_verifier_required_missing"
    hashes = contract.get("command_sha256")
    if not isinstance(hashes, dict):
        return "command_sha256_missing"
    repo_root_hash = hashes.get("repo_root_final_verifier_command")
    if not isinstance(repo_root_hash, str) or not _is_sha256(repo_root_hash):
        return "repo_root_final_verifier_command_hash_invalid"
    return "contract_ready"


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Publish the Git/source release with unsigned-installer user-approval notes."
    first = str(blockers[0]["id"])
    if first.startswith("source_path:"):
        return "Restore the missing source path before publishing the Git release."
    if first == "release_candidate_handoff":
        return "Regenerate and verify outputs/release_candidates/ANN_RC_HANDOFF."
    if first == "release_command_contract":
        return "Regenerate the handoff bundle so the transfer manifest includes the release command contract."
    return f"Resolve Git/source release blocker: {first}"


def _summary(report: dict[str, Any]) -> str:
    blockers = ", ".join(str(blocker["id"]) for blocker in report["blockers"]) or "none"
    return "\n".join(
        [
            "ANN Git/Source Release Verification",
            f"Status: {report['status']}",
            f"Release Channel: {report['release_channel']}",
            f"Trusted Windows Installer: {report['trusted_windows_installer_status']}",
            f"Unsigned Installer: {report['unsigned_installer_status']}",
            f"Runtime Materialization: {report['runtime_materialization']}",
            f"Wheelhouse Integrity: {report['wheelhouse_integrity']}",
            f"Installer RC: {report['installer_rc']}",
            f"Autonomous Complex Capability: {report['autonomous_complex_capability']}",
            f"Release Candidate Handoff: {report['release_candidate_handoff']}",
            f"Release Command Contract: {'PASS' if report['release_command_contract_ready'] else 'BLOCKED'}",
            f"Blockers: {blockers}",
            f"Next Step: {report['next_step']}",
        ]
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ANN Git/Source Release Verification",
        "",
        f"- Status: `{report['status']}`",
        f"- Release Channel: `{report['release_channel']}`",
        f"- Trusted Windows Installer: `{report['trusted_windows_installer_status']}`",
        f"- Unsigned Installer: `{report['unsigned_installer_status']}`",
        f"- Final Signed Installer Channel: `{report['final_signed_installer_channel']}`",
        f"- Runtime Materialization: `{report['runtime_materialization']}`",
        f"- Wheelhouse Integrity: `{report['wheelhouse_integrity']}`",
        f"- Embedded Package Audit: `{report['embedded_package_audit']}`",
        f"- Installer RC: `{report['installer_rc']}`",
        f"- Autonomous Complex Capability: `{report['autonomous_complex_capability']}`",
        f"- Release Candidate Handoff: `{report['release_candidate_handoff']}`",
        f"- Release Command Contract: `{'PASS' if report['release_command_contract_ready'] else 'BLOCKED'}`",
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
