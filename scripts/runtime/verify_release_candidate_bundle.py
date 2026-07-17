"""Verify ANN release-candidate handoff bundle integrity.

This script is intended to run after copying the handoff bundle to a signing or
clean-machine validation host. It checks manifest-declared files, SHA256 hashes,
and protected-directory exclusions. It never installs, downloads, signs, loads
models, or runs inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROTECTED_TOP_LEVEL = {
    ".git",
    "adapters",
    "datasets",
    "models",
    "training",
    "outputs",
    "memory",
    "knowledge",
    "unsloth_compiled_cache",
    "node_modules",
}
REQUIRED_HANDOFF_FILES = {
    "config/ann_model_policy.json",
    "config/ann_runtime_engine.json",
    "config/ann_runtime_lock.example.json",
    "installer/ANN_Setup.exe",
    "installer/ANN_Uninstall.exe",
    "installer/README_INSTALLER.md",
    "installer/install_ann.ps1",
    "installer/sign_release.ps1",
    "installer/uninstall_ann.ps1",
    "installer/validate_clean_machine.ps1",
    "installer/verify_install.ps1",
    "scripts/runtime/plan_autonomous_capability_evidence.py",
    "scripts/runtime/run_autonomous_capability_scenarios.py",
    "scripts/runtime/verify_autonomous_capability.py",
    "scripts/runtime/verify_external_release_evidence.py",
    "scripts/runtime/verify_final_release.py",
    "scripts/runtime/verify_release_candidate_bundle.py",
    "scripts/runtime/verify_release_operator_environment.py",
}
REQUIRED_AUXILIARY_FILES = {
    "FINAL_RELEASE_EXTERNAL_STEPS.md",
    "README_HANDOFF.md",
    "RELEASE_TRANSFER_MANIFEST.json",
    "RELEASE_TRANSFER_MANIFEST.file.sha256",
    "RELEASE_TRANSFER_MANIFEST.sha256",
    "clean_machine_external_validation.template.json",
    "release_candidate_handoff_manifest.json",
}
HASHED_AUXILIARY_FILES = {
    "FINAL_RELEASE_EXTERNAL_STEPS.md",
    "README_HANDOFF.md",
    "clean_machine_external_validation.template.json",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN release candidate handoff bundle.")
    parser.add_argument(
        "--bundle-root",
        default="outputs/release_candidates/ANN_RC_HANDOFF",
        help="Bundle root containing release_candidate_handoff_manifest.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print full verification JSON.")
    return parser


def verify_bundle(bundle_root: str | Path) -> dict[str, Any]:
    root = Path(bundle_root).resolve()
    manifest_path = root / "release_candidate_handoff_manifest.json"
    manifest = _read_json(manifest_path)
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    checks = []
    duplicate_paths = _duplicate_manifest_paths(files)
    manifest_paths = _manifest_relative_paths(files)
    missing_required = sorted(REQUIRED_HANDOFF_FILES - manifest_paths)
    checks.append(
        _check(
            "manifest_relative_paths_unique",
            not duplicate_paths,
            ", ".join(duplicate_paths) or "all relative paths unique",
        )
    )
    checks.append(
        _check(
            "required_handoff_files_present",
            not missing_required,
            ", ".join(missing_required) or "all required handoff files present",
        )
    )
    for entry in files:
        if not isinstance(entry, dict):
            checks.append(_check("manifest_entry_shape", False, "entry is not an object"))
            continue
        relative_path = str(entry.get("relative_path", ""))
        expected_hash = str(entry.get("sha256", ""))
        expected_size = _safe_int(entry.get("size_bytes"))
        path_safe, path_detail = _safe_bundle_relative_path(root, relative_path)
        checks.append(_check(f"file_path_safe:{relative_path or '<empty>'}", path_safe, path_detail))
        if not path_safe:
            continue
        path = (root / relative_path).resolve()
        exists = path.is_file()
        actual_hash = _sha256(path) if exists else ""
        actual_size = path.stat().st_size if exists else -1
        checks.append(_check(f"file:{relative_path}", exists and actual_hash == expected_hash, actual_hash or "missing"))
        checks.append(
            _check(
                f"file_size:{relative_path}",
                exists and expected_size >= 0 and actual_size == expected_size,
                str(actual_size) if exists else "missing",
            )
        )
    protected_hits = _protected_hits(root)
    checks.append(_check("protected_directories_absent", not protected_hits, ", ".join(protected_hits) or "none"))
    checks.append(_check("manifest_present", manifest_path.is_file(), str(manifest_path)))
    checks.extend(_verify_required_auxiliary_files(root))
    checks.extend(_verify_hashed_auxiliary_files(root, manifest))
    checks.append(_check("handoff_manifest_status", manifest.get("status") == "HANDOFF_READY", str(manifest.get("status", "missing"))))
    checks.append(_check("handoff_manifest_materialized", manifest.get("materialized") is True, str(manifest.get("materialized"))))
    checks.append(_check("handoff_manifest_missing_empty", manifest.get("missing") == [], str(manifest.get("missing"))))
    copied = manifest.get("copied") if isinstance(manifest.get("copied"), list) else []
    checks.append(
        _check(
            "handoff_manifest_copied_count_matches",
            len(copied) == len(files),
            f"{len(copied)} copied for {len(files)} files",
        )
    )
    copied_paths_match, copied_paths_detail = _copied_paths_match_manifest(root, copied, files)
    checks.append(_check("handoff_manifest_copied_paths_match", copied_paths_match, copied_paths_detail))
    transfer_checks = _verify_transfer_manifest(root, manifest)
    checks.extend(transfer_checks)
    checks.append(_check("no_models_in_manifest", manifest.get("model_files_included") is False, str(manifest.get("model_files_included"))))
    checks.append(_check("no_training_in_manifest", manifest.get("training_files_included") is False, str(manifest.get("training_files_included"))))
    checks.append(_check("no_datasets_in_manifest", manifest.get("dataset_files_included") is False, str(manifest.get("dataset_files_included"))))
    checks.append(_check("no_adapters_in_manifest", manifest.get("adapter_files_included") is False, str(manifest.get("adapter_files_included"))))
    checks.append(
        _check(
            "no_historical_outputs_in_manifest",
            manifest.get("historical_outputs_included") is False,
            str(manifest.get("historical_outputs_included")),
        )
    )
    checks.append(
        _check(
            "manifest_requires_authenticode_signing",
            manifest.get("signing_required_after_handoff") is True,
            str(manifest.get("signing_required_after_handoff")),
        )
    )
    checks.append(
        _check(
            "manifest_requires_clean_machine_validation",
            manifest.get("clean_machine_validation_required_after_signing") is True,
            str(manifest.get("clean_machine_validation_required_after_signing")),
        )
    )
    checks.append(_check("manifest_no_model_load", manifest.get("no_model_load") is True, str(manifest.get("no_model_load"))))
    checks.append(_check("manifest_no_inference", manifest.get("no_inference") is True, str(manifest.get("no_inference"))))
    checks.append(_check("manifest_no_download", manifest.get("no_download") is True, str(manifest.get("no_download"))))
    checks.append(_check("manifest_no_install", manifest.get("no_install") is True, str(manifest.get("no_install"))))
    checks.extend(_verify_release_command_template_policy(manifest))
    checks.extend(_verify_handoff_command_policy(manifest))
    blockers = [check for check in checks if not check["passed"]]
    status = "HANDOFF_VERIFIED" if not blockers else "HANDOFF_VERIFICATION_FAILED"
    return {
        "version": "18.9.13",
        "status": status,
        "exit_code": 0 if status == "HANDOFF_VERIFIED" else 2,
        "bundle_root": str(root),
        "manifest_path": str(manifest_path),
        "files_checked": len(files),
        "checks": checks,
        "blockers": blockers,
        "protected_hits": protected_hits,
        "transfer_manifest_status": "PASS" if all(check["passed"] for check in transfer_checks) else "BLOCKED",
        "transfer_manifest": _read_json(root / "RELEASE_TRANSFER_MANIFEST.json"),
        "transfer_manifest_file_sha256": _sha256(root / "RELEASE_TRANSFER_MANIFEST.json")
        if (root / "RELEASE_TRANSFER_MANIFEST.json").is_file()
        else "",
        "installer_hashes": _installer_hashes_from_manifest(manifest),
        "no_install": True,
        "no_download": True,
        "no_signing": True,
        "no_model_load": True,
        "no_inference": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = verify_bundle(args.bundle_root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        blockers = ", ".join(check["id"] for check in result["blockers"]) or "none"
        print(
            "\n".join(
                [
                    "ANN Release Candidate Bundle Verification",
                    f"Status: {result['status']}",
                    f"Bundle Root: {result['bundle_root']}",
                    f"Files Checked: {result['files_checked']}",
                    f"Transfer Manifest: {result['transfer_manifest_status']}",
                    f"Blockers: {blockers}",
                ]
            )
        )
    return int(result["exit_code"])


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _protected_hits(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    hits = []
    for child in root.iterdir():
        if child.name.lower() in PROTECTED_TOP_LEVEL:
            hits.append(child.name)
    return sorted(hits)


def _verify_required_auxiliary_files(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for relative_path in sorted(REQUIRED_AUXILIARY_FILES):
        safe, detail = _safe_bundle_relative_path(root, relative_path)
        path = (root / relative_path).resolve() if safe else root / relative_path
        checks.append(
            _check(
                f"auxiliary_file:{relative_path}",
                safe and path.is_file(),
                str(path) if safe else detail,
            )
        )
    return checks


def _verify_hashed_auxiliary_files(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    auxiliary_files = (
        manifest.get("auxiliary_files")
        if isinstance(manifest.get("auxiliary_files"), list)
        else []
    )
    checks: list[dict[str, Any]] = []
    duplicate_paths = _duplicate_manifest_paths(auxiliary_files)
    declared_paths = _manifest_relative_paths(auxiliary_files)
    missing = sorted(HASHED_AUXILIARY_FILES - declared_paths)
    extra = sorted(declared_paths - HASHED_AUXILIARY_FILES)
    checks.append(
        _check(
            "auxiliary_manifest_paths_unique",
            not duplicate_paths,
            ", ".join(duplicate_paths) or "all auxiliary paths unique",
        )
    )
    checks.append(
        _check(
            "auxiliary_manifest_declares_required_hashes",
            not missing and not extra,
            _path_delta_detail(missing, extra) or "all hashed auxiliary files declared",
        )
    )
    for entry in auxiliary_files:
        if not isinstance(entry, dict):
            checks.append(_check("auxiliary_manifest_entry_shape", False, "entry is not an object"))
            continue
        relative_path = str(entry.get("relative_path", ""))
        expected_hash = str(entry.get("sha256", ""))
        expected_size = _safe_int(entry.get("size_bytes"))
        safe, detail = _safe_bundle_relative_path(root, relative_path)
        checks.append(_check(f"auxiliary_path_safe:{relative_path or '<empty>'}", safe, detail))
        if not safe:
            continue
        path = (root / relative_path).resolve()
        exists = path.is_file()
        actual_hash = _sha256(path) if exists else ""
        actual_size = path.stat().st_size if exists else -1
        checks.append(
            _check(
                f"auxiliary_hash:{relative_path}",
                exists and actual_hash == expected_hash,
                actual_hash or "missing",
            )
        )
        checks.append(
            _check(
                f"auxiliary_size:{relative_path}",
                exists and expected_size >= 0 and actual_size == expected_size,
                str(actual_size) if exists else "missing",
            )
        )
    return checks


def _verify_release_command_template_policy(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _check(
            "release_commands_are_templates",
            manifest.get("release_commands_are_templates") is True,
            str(manifest.get("release_commands_are_templates")),
        ),
        _check(
            "release_command_placeholders_must_be_replaced",
            manifest.get("release_command_placeholders_must_be_replaced") is True,
            str(manifest.get("release_command_placeholders_must_be_replaced")),
        ),
        _check(
            "release_command_thumbprint_placeholder",
            manifest.get("release_command_thumbprint_placeholder") == "<CERT_THUMBPRINT>",
            str(manifest.get("release_command_thumbprint_placeholder", "missing")),
        ),
        _check(
            "release_command_thumbprint_regex",
            manifest.get("release_command_thumbprint_regex") == "^[0-9A-Fa-f]{40}$",
            str(manifest.get("release_command_thumbprint_regex", "missing")),
        ),
        _check(
            "sign_release_blocks_placeholder",
            manifest.get("sign_release_blocks_placeholder") is True,
            str(manifest.get("sign_release_blocks_placeholder")),
        ),
    ]


def _verify_transfer_manifest(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    transfer_path = root / "RELEASE_TRANSFER_MANIFEST.json"
    digest_path = root / "RELEASE_TRANSFER_MANIFEST.sha256"
    file_digest_path = root / "RELEASE_TRANSFER_MANIFEST.file.sha256"
    transfer = _read_json(transfer_path)
    expected_digest = _transfer_digest_from_handoff_manifest(manifest)
    digest_text = ""
    file_digest_text = ""
    try:
        digest_text = digest_path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        digest_text = ""
    try:
        file_digest_text = file_digest_path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        file_digest_text = ""
    actual_digest = str(transfer.get("aggregate_sha256", "")) if transfer else ""
    actual_file_digest = _sha256(transfer_path) if transfer_path.is_file() else ""
    transfer_paths_safe, transfer_path_detail = _transfer_manifest_paths_safe(root, transfer)
    transfer_auxiliary_paths_safe, transfer_auxiliary_path_detail = _transfer_manifest_auxiliary_paths_safe(root, transfer)
    file_list_matches, file_list_detail = _transfer_manifest_file_list_matches_handoff(transfer, manifest)
    auxiliary_list_matches, auxiliary_list_detail = _transfer_manifest_auxiliary_list_matches_handoff(transfer, manifest)
    expected_command_contract = _release_command_contract_from_manifest(manifest)
    transfer_command_contract = transfer.get("release_command_contract")
    command_contract_matches = transfer_command_contract == expected_command_contract
    transfer_files = transfer.get("files") if isinstance(transfer.get("files"), list) else []
    transfer_auxiliary_files = (
        transfer.get("auxiliary_files")
        if isinstance(transfer.get("auxiliary_files"), list)
        else []
    )
    duplicate_transfer_paths = _duplicate_manifest_paths(transfer_files)
    duplicate_transfer_auxiliary_paths = _duplicate_manifest_paths(transfer_auxiliary_files)
    return [
        _check("transfer_manifest_present", transfer_path.is_file(), str(transfer_path)),
        _check("transfer_digest_file_present", digest_path.is_file(), str(digest_path)),
        _check("transfer_file_digest_file_present", file_digest_path.is_file(), str(file_digest_path)),
        _check("transfer_manifest_status", transfer.get("status") == "TRANSFER_MANIFEST_READY", str(transfer.get("status", "missing"))),
        _check(
            "transfer_manifest_file_paths_unique",
            not duplicate_transfer_paths,
            ", ".join(duplicate_transfer_paths) or "all transfer file paths unique",
        ),
        _check(
            "transfer_manifest_auxiliary_paths_unique",
            not duplicate_transfer_auxiliary_paths,
            ", ".join(duplicate_transfer_auxiliary_paths) or "all transfer auxiliary paths unique",
        ),
        _check("transfer_file_count_matches", transfer.get("file_count") == len(transfer_files), str(transfer.get("file_count", "missing"))),
        _check(
            "transfer_auxiliary_file_count_matches",
            transfer.get("auxiliary_file_count") == len(transfer_auxiliary_files),
            str(transfer.get("auxiliary_file_count", "missing")),
        ),
        _check("transfer_manifest_matches_handoff", actual_digest == expected_digest, actual_digest or "missing"),
        _check("transfer_digest_file_matches", digest_text == actual_digest and bool(digest_text), digest_text or "missing"),
        _check(
            "transfer_file_digest_file_matches",
            file_digest_text == actual_file_digest and bool(file_digest_text),
            file_digest_text or "missing",
        ),
        _check("transfer_manifest_no_absolute_paths", transfer.get("no_absolute_paths_required") is True, str(transfer.get("no_absolute_paths_required"))),
        _check("transfer_manifest_paths_safe", transfer_paths_safe, transfer_path_detail),
        _check("transfer_manifest_auxiliary_paths_safe", transfer_auxiliary_paths_safe, transfer_auxiliary_path_detail),
        _check("transfer_manifest_file_list_matches_handoff", file_list_matches, file_list_detail),
        _check("transfer_manifest_auxiliary_list_matches_handoff", auxiliary_list_matches, auxiliary_list_detail),
        _check(
            "transfer_release_command_contract_matches",
            command_contract_matches,
            "release_command_contract_match" if command_contract_matches else "release_command_contract_mismatch",
        ),
        _check("transfer_no_models", transfer.get("no_models") is True, str(transfer.get("no_models"))),
        _check("transfer_no_training", transfer.get("no_training") is True, str(transfer.get("no_training"))),
        _check("transfer_no_datasets", transfer.get("no_datasets") is True, str(transfer.get("no_datasets"))),
        _check("transfer_no_adapters", transfer.get("no_adapters") is True, str(transfer.get("no_adapters"))),
        _check("transfer_no_historical_outputs", transfer.get("no_historical_outputs") is True, str(transfer.get("no_historical_outputs"))),
        _check(
            "transfer_requires_authenticode_signing",
            transfer.get("requires_trusted_authenticode_signing") is True,
            str(transfer.get("requires_trusted_authenticode_signing")),
        ),
        _check(
            "transfer_requires_clean_machine_validation",
            transfer.get("requires_external_clean_machine_validation") is True,
            str(transfer.get("requires_external_clean_machine_validation")),
        ),
        _check("transfer_no_model_load", transfer.get("no_model_load") is True, str(transfer.get("no_model_load"))),
        _check("transfer_no_inference", transfer.get("no_inference") is True, str(transfer.get("no_inference"))),
        _check("transfer_no_download", transfer.get("no_download") is True, str(transfer.get("no_download"))),
        _check("transfer_no_install", transfer.get("no_install") is True, str(transfer.get("no_install"))),
    ]


def _safe_bundle_relative_path(root: Path, relative_path: str) -> tuple[bool, str]:
    if not relative_path.strip():
        return False, "empty_relative_path"
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return False, "absolute_path_blocked"
    if ".." in candidate.parts:
        return False, "parent_traversal_blocked"
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return False, "path_escapes_bundle_root"
    return True, str(resolved)


def _transfer_manifest_paths_safe(root: Path, transfer: dict[str, Any]) -> tuple[bool, str]:
    files = transfer.get("files") if isinstance(transfer.get("files"), list) else []
    unsafe = []
    for entry in files:
        if not isinstance(entry, dict):
            unsafe.append("non_object_entry")
            continue
        relative_path = str(entry.get("relative_path", ""))
        safe, detail = _safe_bundle_relative_path(root, relative_path)
        if not safe:
            unsafe.append(f"{relative_path or '<empty>'}:{detail}")
    return (False, ", ".join(unsafe)) if unsafe else (True, "all transfer paths safe")


def _transfer_manifest_auxiliary_paths_safe(root: Path, transfer: dict[str, Any]) -> tuple[bool, str]:
    files = transfer.get("auxiliary_files") if isinstance(transfer.get("auxiliary_files"), list) else []
    unsafe = []
    for entry in files:
        if not isinstance(entry, dict):
            unsafe.append("non_object_entry")
            continue
        relative_path = str(entry.get("relative_path", ""))
        safe, detail = _safe_bundle_relative_path(root, relative_path)
        if not safe:
            unsafe.append(f"{relative_path or '<empty>'}:{detail}")
    return (False, ", ".join(unsafe)) if unsafe else (True, "all transfer auxiliary paths safe")


def _transfer_manifest_file_list_matches_handoff(
    transfer: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[bool, str]:
    transfer_files = _portable_files_from_manifest_like(transfer)
    handoff_files = _portable_files_from_manifest_like(manifest)
    if transfer_files == handoff_files:
        return True, "transfer files match handoff manifest"
    transfer_paths = {item["relative_path"] for item in transfer_files}
    handoff_paths = {item["relative_path"] for item in handoff_files}
    missing = sorted(handoff_paths - transfer_paths)
    extra = sorted(transfer_paths - handoff_paths)
    changed = sorted(
        path
        for path in transfer_paths & handoff_paths
        if next(item for item in transfer_files if item["relative_path"] == path)
        != next(item for item in handoff_files if item["relative_path"] == path)
    )
    details = []
    if missing:
        details.append("missing:" + ",".join(missing))
    if extra:
        details.append("extra:" + ",".join(extra))
    if changed:
        details.append("changed:" + ",".join(changed))
    return False, "; ".join(details) or "file_list_mismatch"


def _transfer_manifest_auxiliary_list_matches_handoff(
    transfer: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[bool, str]:
    transfer_files = _portable_auxiliary_files_from_manifest_like(transfer)
    handoff_files = _portable_auxiliary_files_from_manifest_like(manifest)
    if transfer_files == handoff_files:
        return True, "transfer auxiliary files match handoff manifest"
    transfer_paths = {item["relative_path"] for item in transfer_files}
    handoff_paths = {item["relative_path"] for item in handoff_files}
    missing = sorted(handoff_paths - transfer_paths)
    extra = sorted(transfer_paths - handoff_paths)
    changed = sorted(
        path
        for path in transfer_paths & handoff_paths
        if next(item for item in transfer_files if item["relative_path"] == path)
        != next(item for item in handoff_files if item["relative_path"] == path)
    )
    details = []
    if missing:
        details.append("missing:" + ",".join(missing))
    if extra:
        details.append("extra:" + ",".join(extra))
    if changed:
        details.append("changed:" + ",".join(changed))
    return False, "; ".join(details) or "auxiliary_file_list_mismatch"


def _path_delta_detail(missing: list[str], extra: list[str]) -> str:
    details = []
    if missing:
        details.append("missing:" + ",".join(missing))
    if extra:
        details.append("extra:" + ",".join(extra))
    return "; ".join(details)


def _duplicate_manifest_paths(files: list[Any]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("relative_path", "")).strip()
        if not relative_path:
            continue
        if relative_path in seen:
            duplicates.add(relative_path)
        seen.add(relative_path)
    return sorted(duplicates)


def _manifest_relative_paths(files: list[Any]) -> set[str]:
    return {
        str(entry.get("relative_path", "")).strip()
        for entry in files
        if isinstance(entry, dict) and str(entry.get("relative_path", "")).strip()
    }


def _copied_paths_match_manifest(root: Path, copied: list[Any], files: list[Any]) -> tuple[bool, str]:
    expected_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("relative_path", "")).strip()
        safe, _detail = _safe_bundle_relative_path(root, relative_path)
        if safe:
            expected_paths.add(relative_path.replace("\\", "/"))
    copied_paths: set[str] = set()
    unsafe: list[str] = []
    for item in copied:
        raw = str(item).strip()
        if not raw:
            unsafe.append("<empty>:empty_copied_path")
            continue
        relative = _copied_path_relative_suffix(raw, expected_paths)
        if not relative:
            unsafe.append(f"{raw}:not_a_declared_bundle_file")
            continue
        copied_paths.add(relative)
    missing = sorted(expected_paths - copied_paths)
    extra = sorted(copied_paths - expected_paths)
    details = []
    if unsafe:
        details.append("unsafe:" + ",".join(unsafe))
    if missing:
        details.append("missing:" + ",".join(missing))
    if extra:
        details.append("extra:" + ",".join(extra))
    return (False, "; ".join(details)) if details else (True, "copied paths match manifest files")


def _copied_path_relative_suffix(raw: str, expected_paths: set[str]) -> str:
    normalized = raw.replace("\\", "/").rstrip("/")
    if not normalized or any(part == ".." for part in normalized.split("/")):
        return ""
    matches = [
        expected
        for expected in expected_paths
        if normalized == expected or normalized.endswith("/" + expected)
    ]
    if len(matches) != 1:
        return ""
    return matches[0]


def _transfer_digest_from_handoff_manifest(manifest: dict[str, Any]) -> str:
    portable_files = _portable_files_from_manifest_like(manifest)
    portable_auxiliary_files = _portable_auxiliary_files_from_manifest_like(manifest)
    canonical_payload = {
        "files": portable_files,
        "auxiliary_files": portable_auxiliary_files,
        "release_command_contract": _release_command_contract_from_manifest(manifest),
        "model_files_included": bool(manifest.get("model_files_included")),
        "training_files_included": bool(manifest.get("training_files_included")),
        "dataset_files_included": bool(manifest.get("dataset_files_included")),
        "adapter_files_included": bool(manifest.get("adapter_files_included")),
        "historical_outputs_included": bool(manifest.get("historical_outputs_included")),
        "signing_required_after_handoff": bool(manifest.get("signing_required_after_handoff")),
        "clean_machine_validation_required_after_signing": bool(
            manifest.get("clean_machine_validation_required_after_signing")
        ),
    }
    return hashlib.sha256(
        json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _release_command_contract_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    command_keys = [
        "bundle_verifier_command",
        "release_operator_environment_command",
        "sign_command",
        "clean_machine_command",
        "external_release_evidence_command",
        "final_verifier_command",
        "repo_root_final_verifier_command",
    ]
    return {
        "version": "18.9.17",
        "commands_are_templates": bool(manifest.get("release_commands_are_templates")),
        "placeholder_must_be_replaced": bool(
            manifest.get("release_command_placeholders_must_be_replaced")
        ),
        "thumbprint_placeholder": str(manifest.get("release_command_thumbprint_placeholder") or ""),
        "thumbprint_regex": str(manifest.get("release_command_thumbprint_regex") or ""),
        "repo_root_final_verifier_required": bool(manifest.get("repo_root_final_verifier_command")),
        "command_sha256": {
            key: hashlib.sha256(str(manifest.get(key) or "").encode("utf-8")).hexdigest()
            for key in command_keys
        },
    }


def _portable_files_from_manifest_like(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    portable_files = [
        {
            "relative_path": str(entry.get("relative_path", "")),
            "size_bytes": int(entry.get("size_bytes", 0)),
            "sha256": str(entry.get("sha256", "")),
        }
        for entry in files
        if isinstance(entry, dict)
    ]
    portable_files.sort(key=lambda item: item["relative_path"])
    return portable_files


def _portable_auxiliary_files_from_manifest_like(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("auxiliary_files") if isinstance(payload.get("auxiliary_files"), list) else []
    portable_files = [
        {
            "relative_path": str(entry.get("relative_path", "")),
            "size_bytes": int(entry.get("size_bytes", 0)),
            "sha256": str(entry.get("sha256", "")),
        }
        for entry in files
        if isinstance(entry, dict)
    ]
    portable_files.sort(key=lambda item: item["relative_path"])
    return portable_files


def _installer_hashes_from_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    expected = {
        "installer/ANN_Setup.exe": "ANN_Setup.exe",
        "installer/ANN_Uninstall.exe": "ANN_Uninstall.exe",
    }
    hashes: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("relative_path", ""))
        name = expected.get(relative_path)
        if name:
            hashes[name] = str(entry.get("sha256", ""))
    return hashes


def _verify_handoff_command_policy(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sign_command = str(manifest.get("sign_command") or "")
    clean_machine_command = str(manifest.get("clean_machine_command") or "")
    final_verifier_command = str(manifest.get("final_verifier_command") or "")
    external_evidence_command = str(manifest.get("external_release_evidence_command") or "")
    operator_command = str(manifest.get("release_operator_environment_command") or "")
    bundle_verifier_command = str(manifest.get("bundle_verifier_command") or "")
    repo_root_final_verifier_command = str(manifest.get("repo_root_final_verifier_command") or "")
    commands = {
        "sign_command": sign_command,
        "clean_machine_command": clean_machine_command,
        "final_verifier_command": final_verifier_command,
        "external_release_evidence_command": external_evidence_command,
        "release_operator_environment_command": operator_command,
        "bundle_verifier_command": bundle_verifier_command,
        "repo_root_final_verifier_command": repo_root_final_verifier_command,
    }
    checks = [
        _check(
            "sign_command_targets_sign_release_script",
            "installer\\sign_release.ps1" in sign_command,
            sign_command or "missing",
        ),
        _check(
            "sign_command_requires_execute",
            "-Execute" in sign_command,
            sign_command or "missing",
        ),
        _check(
            "sign_command_requires_thumbprint_placeholder",
            '-CertificateThumbprint "<CERT_THUMBPRINT>"' in sign_command,
            sign_command or "missing",
        ),
        _check(
            "sign_command_writes_signing_evidence",
            "-OutputPath installer\\release_signing_evidence.json" in sign_command,
            sign_command or "missing",
        ),
        _check(
            "sign_command_requires_timestamp_url",
            "-TimestampUrl " in sign_command,
            sign_command or "missing",
        ),
        _check(
            "clean_machine_command_targets_clean_machine_validator",
            "installer\\validate_clean_machine.ps1" in clean_machine_command,
            clean_machine_command or "missing",
        ),
        _check(
            "clean_machine_command_requires_clean_machine_environment",
            "-EnvironmentType clean_machine" in clean_machine_command,
            clean_machine_command or "missing",
        ),
        _check(
            "clean_machine_command_requires_signed_installer",
            "-RequireSignedInstaller" in clean_machine_command,
            clean_machine_command or "missing",
        ),
        _check(
            "clean_machine_command_links_signing_evidence",
            "-SigningEvidencePath installer\\release_signing_evidence.json" in clean_machine_command,
            clean_machine_command or "missing",
        ),
        _check(
            "clean_machine_command_links_transfer_manifest",
            "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json" in clean_machine_command,
            clean_machine_command or "missing",
        ),
        _check(
            "final_verifier_command_targets_final_verifier",
            "scripts/runtime/verify_final_release.py" in final_verifier_command,
            final_verifier_command or "missing",
        ),
        _check(
            "final_verifier_command_requires_signing_evidence",
            "--signing-evidence installer\\release_signing_evidence.json" in final_verifier_command,
            final_verifier_command or "missing",
        ),
        _check(
            "final_verifier_command_requires_certificate_thumbprint",
            '--certificate-thumbprint "<CERT_THUMBPRINT>"' in final_verifier_command,
            final_verifier_command or "missing",
        ),
        _check(
            "external_evidence_command_targets_external_evidence_verifier",
            "scripts/runtime/verify_external_release_evidence.py" in external_evidence_command,
            external_evidence_command or "missing",
        ),
        _check(
            "external_evidence_command_requires_clean_machine_marker",
            "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json" in external_evidence_command,
            external_evidence_command or "missing",
        ),
        _check(
            "external_evidence_command_requires_signing_evidence",
            "--signing-evidence installer\\release_signing_evidence.json" in external_evidence_command,
            external_evidence_command or "missing",
        ),
        _check(
            "operator_command_targets_operator_environment_verifier",
            "scripts/runtime/verify_release_operator_environment.py" in operator_command,
            operator_command or "missing",
        ),
        _check(
            "operator_command_requires_certificate_thumbprint",
            '--certificate-thumbprint "<CERT_THUMBPRINT>"' in operator_command,
            operator_command or "missing",
        ),
        _check(
            "bundle_verifier_command_targets_bundle_verifier",
            "scripts/runtime/verify_release_candidate_bundle.py" in bundle_verifier_command,
            bundle_verifier_command or "missing",
        ),
        _check(
            "bundle_verifier_command_targets_current_bundle",
            "--bundle-root ." in bundle_verifier_command,
            bundle_verifier_command or "missing",
        ),
        _check(
            "repo_root_final_verifier_command_targets_final_verifier",
            "scripts/runtime/verify_final_release.py" in repo_root_final_verifier_command,
            repo_root_final_verifier_command or "missing",
        ),
        _check(
            "repo_root_final_verifier_command_targets_handoff_bundle",
            "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF" in repo_root_final_verifier_command,
            repo_root_final_verifier_command or "missing",
        ),
        _check(
            "repo_root_final_verifier_command_requires_clean_machine_marker",
            "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json" in repo_root_final_verifier_command,
            repo_root_final_verifier_command or "missing",
        ),
        _check(
            "repo_root_final_verifier_command_requires_signing_evidence",
            "--signing-evidence installer\\release_signing_evidence.json" in repo_root_final_verifier_command,
            repo_root_final_verifier_command or "missing",
        ),
        _check(
            "repo_root_final_verifier_command_requires_certificate_thumbprint",
            '--certificate-thumbprint "<CERT_THUMBPRINT>"' in repo_root_final_verifier_command,
            repo_root_final_verifier_command or "missing",
        ),
    ]
    checks.extend(
        _check(
            f"{name}_shell_safety",
            _command_string_safety_detail(command) == "command_string_safe",
            _command_string_safety_detail(command),
        )
        for name, command in commands.items()
    )
    return checks


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


if __name__ == "__main__":
    sys.exit(main())
