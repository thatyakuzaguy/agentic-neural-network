"""Distribution readiness checks for ANN Desktop alpha.

This module reuses installer, runtime bundle, model inventory, and model policy
foundations. It is read-only: no downloads, installs, model loads, training, or
project mutations are performed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.installer.paths import BLOCKED_PARTS, get_default_install_root, is_c_drive
from agentic_network.installer.runtime import build_install_plan, build_uninstall_plan
from agentic_network.installer.validation import validate_install_plan, validate_runtime_requirements
from agentic_network.runtime_bundle.runtime import build_runtime_manifest
from agentic_network.runtime_bundle.validation import validate_runtime_bundle
from agentic_network.runtime_engine.model_inventory import ModelRecord, load_model_inventory
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DISTRIBUTION_ARTIFACT_ROOT = REPO_ROOT / "outputs" / "distribution"
MODEL_TARGETS = (
    {
        "id": "qwen2_5_coder_7b_v5",
        "display_name": "Qwen2.5-Coder-7B adapter v5",
        "purpose": "coding",
        "mode": "FAST",
        "confirmed_local_asset": True,
        "required_tokens": ("qwen2.5", "coder", "7b", "v5"),
    },
    {
        "id": "qwen3_8b_v9_repaired_v2_bullets",
        "display_name": "Qwen3-8B adapter v9-repaired-v2-bullets",
        "purpose": "product_agent_and_structuring",
        "mode": "FAST",
        "confirmed_local_asset": True,
        "required_tokens": ("qwen3", "8b", "v9"),
    },
    {
        "id": "deepseek_r1_distill_qwen_14b_powerful",
        "display_name": "DeepSeek-R1-Distill-Qwen-14B POWERFUL",
        "purpose": "powerful_reasoning",
        "mode": "POWERFUL",
        "confirmed_local_asset": False,
        "required_tokens": ("deepseek", "14b"),
    },
)
SCRIPT_BLOCKLIST = (
    "invoke-webrequest",
    "start-bitstransfer",
    "curl ",
    "wget ",
    "pip install",
    "npm install",
    "conda install",
)


def build_distribution_readiness(
    repo_root: str | Path | None = None,
    install_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only alpha distribution readiness report."""

    source_root = Path(repo_root or REPO_ROOT).resolve()
    target_root = Path(install_root or get_default_install_root())
    plan = build_install_plan(source_root, target_root)
    validation = validate_install_plan(plan)
    runtime_validation = validate_runtime_requirements(target_root)
    installer_scripts = _installer_script_status(source_root)
    model_status = build_model_distribution_status(source_root)
    checks = [
        _check("installer_plan", validation.valid, validation.errors + validation.warnings),
        _check("desktop_entrypoint", runtime_validation.desktop_importable, runtime_validation.errors),
        _check("runtime_config", runtime_validation.runtime_config_exists, runtime_validation.errors),
        _check("model_policy", runtime_validation.model_policy_exists, runtime_validation.errors),
        _check("no_c_drive_default", not is_c_drive(target_root), [str(target_root)]),
        _check("protected_paths_excluded", _protected_paths_excluded(), sorted(BLOCKED_PARTS)),
        _check("scripts_present", installer_scripts["missing"] == [], installer_scripts["missing"]),
        _check("scripts_no_downloads", installer_scripts["blocked_tokens"] == [], installer_scripts["blocked_tokens"]),
        _check("model_status_visible", bool(model_status["models"]), []),
    ]
    gaps = [check for check in checks if check["status"] != "PASS"]
    return {
        "version": "12.5",
        "generated_at": _now(),
        "status": "READY_FOR_ALPHA" if not gaps else "ALPHA_GAPS",
        "repo_root": str(source_root),
        "install_root": str(target_root),
        "installer_plan": plan.to_dict(),
        "installer_validation": validation.to_dict(),
        "runtime_validation": runtime_validation.to_dict(),
        "installer_scripts": installer_scripts,
        "checks": checks,
        "gaps": gaps,
        "model_distribution_status": model_status,
        "safety": _safety_payload(),
    }


def build_embedded_runtime_plan(install_root: str | Path | None = None) -> dict[str, Any]:
    """Describe how the future embedded runtime will be packaged."""

    target_root = Path(install_root or get_default_install_root())
    runtime_dir = target_root / "runtime"
    embedded_python = runtime_dir / "python" / "python.exe"
    manifest = build_runtime_manifest()
    validation = validate_runtime_bundle(manifest)
    return {
        "version": "12.6",
        "generated_at": _now(),
        "status": "PLAN_ONLY",
        "install_root": str(target_root),
        "runtime_dir": str(runtime_dir),
        "embedded_python_executable": str(embedded_python),
        "embedded_python_present": embedded_python.is_file(),
        "active_runtime_kind": manifest.python_runtime.kind,
        "runtime_validation": validation.to_dict(),
        "dependencies": manifest.runtime_dependencies,
        "available_backends": manifest.available_backends,
        "packaging_steps": [
            "Bundle a signed Python runtime under runtime/python.",
            "Copy runtime dependencies from a reproducible local build cache.",
            "Copy ANN app/config/installer files using the existing install plan.",
            "Verify imports and desktop launch without network access.",
            "Keep model files external or explicitly declared by Model Inventory.",
        ],
        "blocked_actions": [
            "no_downloads",
            "no_pip_install",
            "no_model_download",
            "no_training",
            "no_adapter_write",
            "no_dataset_write",
        ],
        "warnings": _dedupe(
            validation.warnings
            + ([] if embedded_python.is_file() else ["embedded_python_absent; current runtime is development-only"])
        ),
        "errors": validation.errors,
        "safety": _safety_payload(),
    }


def verify_installer_foundation(
    repo_root: str | Path | None = None,
    install_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify current installer foundation without copying or deleting files."""

    source_root = Path(repo_root or REPO_ROOT).resolve()
    target_root = Path(install_root or get_default_install_root())
    install_plan = build_install_plan(source_root, target_root)
    uninstall_plan = build_uninstall_plan(target_root)
    install_validation = validate_install_plan(install_plan)
    script_status = _installer_script_status(source_root)
    checks = [
        _check("install_root_not_c_drive", not is_c_drive(target_root), [str(target_root)]),
        _check("install_plan_valid", install_validation.valid, install_validation.errors),
        _check("uninstall_preserves_projects", uninstall_plan.keep_projects, []),
        _check("uninstall_preserves_models", uninstall_plan.keep_models, []),
        _check("scripts_no_downloads", script_status["blocked_tokens"] == [], script_status["blocked_tokens"]),
        _check("launcher_planned", _desktop_launcher_planned(install_plan.files_to_copy), []),
    ]
    return {
        "version": "12.6",
        "generated_at": _now(),
        "status": "VERIFIED" if all(check["status"] == "PASS" for check in checks) else "NEEDS_ATTENTION",
        "install_plan": install_plan.to_dict(),
        "uninstall_plan": uninstall_plan.to_dict(),
        "install_validation": install_validation.to_dict(),
        "script_status": script_status,
        "checks": checks,
        "safety": _safety_payload(),
    }


def build_model_distribution_status(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Return explicit model distribution status without loading model files."""

    _ = Path(repo_root or REPO_ROOT).resolve()
    inventory = load_model_inventory()
    policy = load_model_policy()
    models = [_target_status(target, inventory.models, policy) for target in MODEL_TARGETS]
    fast_ready = all(
        (model["declared"] or model["confirmed_local_asset"]) and model["mode"] == "FAST"
        for model in models
        if model["id"] != "deepseek_r1_distill_qwen_14b_powerful"
    )
    deepseek14b = next(model for model in models if model["id"] == "deepseek_r1_distill_qwen_14b_powerful")
    return {
        "version": "12.6",
        "generated_at": _now(),
        "status": "MODEL_LOADING_BLOCKED_BY_POLICY"
        if not policy.allow_real_model_load
        else "MODEL_POLICY_ALLOWS_REAL_LOAD",
        "inventory_version": inventory.version,
        "inventory_errors": inventory.errors,
        "inventory_warnings": inventory.warnings,
        "policy": policy.to_dict(),
        "sequential_policy": {
            "vram_policy": policy.vram_policy,
            "max_loaded_models": policy.max_loaded_models,
            "active_models_target": "<=1",
            "parallel_llm_loads": 0,
            "valid": policy.vram_policy.upper() == "SEQUENTIAL" and policy.max_loaded_models == 1,
        },
        "fast_mode": "declared_not_loadable" if fast_ready else "not_fully_configured",
        "powerful_mode": deepseek14b["status"],
        "models": models,
        "safety": _safety_payload(),
    }


def build_alpha_release_checklist(
    repo_root: str | Path | None = None,
    install_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build the alpha release checklist for productization."""

    readiness = build_distribution_readiness(repo_root, install_root)
    runtime_plan = build_embedded_runtime_plan(install_root)
    installer = verify_installer_foundation(repo_root, install_root)
    model_status = build_model_distribution_status(repo_root)
    checklist = [
        _check("desktop_app_foundation", True, []),
        _check("runtime_bundle_detection", runtime_plan["runtime_validation"]["status"] == "VALID", runtime_plan["errors"]),
        _check("installer_foundation", installer["status"] == "VERIFIED", []),
        _check("first_run_productization", True, []),
        _check("model_inventory_visible", bool(model_status["models"]), []),
        _check("real_model_loading_policy_safe", model_status["policy"]["allow_real_model_load"] is False, []),
        _check("deepseek14b_not_misrepresented", model_status["powerful_mode"] != "loadable", []),
        _check("alpha_distribution_readiness", readiness["status"] in {"READY_FOR_ALPHA", "ALPHA_GAPS"}, []),
    ]
    return {
        "version": "12.7",
        "generated_at": _now(),
        "status": "ALPHA_READY_WITH_LIMITATIONS"
        if all(item["status"] == "PASS" for item in checklist)
        else "ALPHA_BLOCKED",
        "checklist": checklist,
        "manual_steps_remaining": [
            "Bundle or select an embedded Python runtime.",
            "Package model assets only after explicit model inventory and license review.",
            "Enable real model loading only after policy and backend smoke tests pass.",
            "Build and sign the final installer in a separate release phase.",
        ],
        "developer_preview_warning": (
            "This is an alpha/developer preview. It should not claim automatic sellable product generation "
            "or real model execution when model policy blocks loading."
        ),
        "safety": _safety_payload(),
    }


def write_distribution_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 88-97 into an outputs/distribution directory."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "88_distribution_readiness.json": build_distribution_readiness(),
        "90_embedded_runtime_plan.json": build_embedded_runtime_plan(),
        "92_installer_verification.json": verify_installer_foundation(),
        "94_model_distribution_status.json": build_model_distribution_status(),
        "96_alpha_release_checklist.json": build_alpha_release_checklist(),
    }
    written: list[str] = []
    for name, payload in payloads.items():
        path = target / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))
        md_name = str(int(name[:2]) + 1).zfill(2) + name[2:].replace(".json", ".md")
        md_path = target / md_name
        md_path.write_text(_payload_markdown(md_name, payload), encoding="utf-8")
        written.append(str(md_path))
    return written


def first_run_distribution_state(install_root: str | Path | None = None) -> dict[str, Any]:
    """Return compact state for the desktop First Run view."""

    runtime_plan = build_embedded_runtime_plan(install_root)
    model_status = build_model_distribution_status()
    runtime_validation = validate_runtime_requirements(install_root)
    policy = model_status["policy"]
    return {
        "runtime_status": runtime_validation.status,
        "current_runtime_mode": runtime_plan["active_runtime_kind"],
        "embedded_python_present": runtime_plan["embedded_python_present"],
        "embedded_python_executable": runtime_plan["embedded_python_executable"],
        "model_policy": {
            "real_model_loading": "blocked" if not policy["allow_real_model_load"] else "allowed",
            "downloads": policy["allow_model_download"],
            "training": policy["allow_training"],
            "vram_policy": policy["vram_policy"],
            "max_loaded_models": policy["max_loaded_models"],
        },
        "fast_mode": model_status["fast_mode"],
        "powerful_mode": model_status["powerful_mode"],
        "models": model_status["models"],
        "recommended_steps": build_alpha_release_checklist(install_root=install_root)["manual_steps_remaining"],
        "developer_preview_warning": build_alpha_release_checklist(install_root=install_root)[
            "developer_preview_warning"
        ],
    }


def _target_status(target: dict[str, Any], records: list[ModelRecord], policy: Any) -> dict[str, Any]:
    matched = _match_target_record(target, records)
    if matched is None:
        if target["id"] == "deepseek_r1_distill_qwen_14b_powerful":
            status = "not_configured"
        elif target.get("confirmed_local_asset"):
            status = "confirmed_local_asset_inventory_pending"
        else:
            status = "not_declared"
        return {
            "id": target["id"],
            "display_name": target["display_name"],
            "purpose": target["purpose"],
            "mode": target["mode"],
            "status": status,
            "declared": False,
            "confirmed_local_asset": bool(target.get("confirmed_local_asset")),
            "load_allowed": False,
            "load_blocked_reason": "inventory_record_missing_or_policy_blocked",
        }
    decision = validate_model_load_request(matched.name, matched.backend, matched.mode, policy=policy)
    status = _model_status_from_record(matched, decision)
    return {
        "id": target["id"],
        "display_name": target["display_name"],
        "purpose": target["purpose"],
        "mode": matched.mode,
        "status": status,
        "declared": True,
        "confirmed_local_asset": bool(target.get("confirmed_local_asset")),
        "inventory_name": matched.name,
        "family": matched.family,
        "backend": matched.backend,
        "path": matched.path,
        "source_path": matched.source_path,
        "distribution_path": matched.distribution_path,
        "adapter_path": matched.adapter_path,
        "enabled": matched.enabled,
        "exists": matched.exists,
        "validation_status": matched.validation_status,
        "estimated_vram_mb": matched.estimated_vram_mb,
        "load_allowed": decision.allowed,
        "load_blocked_reason": decision.reason if not decision.allowed else "allowed_by_policy",
        "policy_errors": decision.errors,
        "policy_warnings": decision.warnings,
    }


def _match_target_record(target: dict[str, Any], records: list[ModelRecord]) -> ModelRecord | None:
    tokens = tuple(str(item).lower() for item in target["required_tokens"])
    for record in records:
        haystack = " ".join(
            [
                record.name,
                record.family,
                record.mode,
                record.backend,
                record.path,
                record.adapter_path or "",
            ]
        ).lower()
        if all(token in haystack for token in tokens):
            return record
    if target["id"] == "deepseek_r1_distill_qwen_14b_powerful":
        for record in records:
            if record.mode.upper() == "POWERFUL" and "14" in record.name.lower():
                return record
    return None


def _model_status_from_record(record: ModelRecord, decision: Any) -> str:
    if not decision.allowed:
        return "blocked_by_policy"
    if not record.enabled:
        return "disabled"
    if record.validation_status == "VALID":
        return "loadable"
    return record.validation_status.lower()


def _installer_script_status(source_root: Path) -> dict[str, Any]:
    installer_root = source_root / "installer"
    required = (
        "install_ann.ps1",
        "uninstall_ann.ps1",
        "create_shortcut.ps1",
        "verify_install.ps1",
        "ann_launcher.ps1",
    )
    present: list[str] = []
    missing: list[str] = []
    blocked_tokens: list[str] = []
    for name in required:
        path = installer_root / name
        if not path.is_file():
            missing.append(name)
            continue
        present.append(name)
        try:
            text = path.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        for token in SCRIPT_BLOCKLIST:
            if token in text:
                blocked_tokens.append(f"{name}:{token.strip()}")
    return {"present": present, "missing": missing, "blocked_tokens": _dedupe(blocked_tokens)}


def _desktop_launcher_planned(files_to_copy: list[str]) -> bool:
    return any(str(path).replace("\\", "/").endswith("desktop_app/run.py") for path in files_to_copy)


def _protected_paths_excluded() -> bool:
    required = {".git", "models", "training", "datasets", "adapters", "memory", "knowledge", "unsloth_compiled_cache"}
    return required.issubset(BLOCKED_PARTS)


def _check(name: str, condition: bool, evidence: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if condition else "FAIL",
        "evidence": evidence,
    }


def _payload_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated at: {payload.get('generated_at')}",
        f"Status: {payload.get('status')}",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(_compact_payload(payload), indent=2),
        "```",
        "",
        "Safety: read-only distribution check; no internet, downloads, dependency installation, model loading, "
        "training, adapter writes, dataset writes, or protected path mutations.",
        "",
    ]
    return "\n".join(lines)


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "version",
        "status",
        "checks",
        "checklist",
        "gaps",
        "manual_steps_remaining",
        "fast_mode",
        "powerful_mode",
        "sequential_policy",
        "warnings",
        "errors",
    )
    return {key: payload[key] for key in keys if key in payload}


def _timestamped_artifact_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_DISTRIBUTION_ARTIFACT_ROOT / stamp


def _safety_payload() -> dict[str, Any]:
    return {
        "local_only": True,
        "internet": False,
        "downloads": False,
        "dependency_install": False,
        "model_load": False,
        "training": False,
        "modify_models": False,
        "modify_adapters": False,
        "modify_datasets": False,
        "touch_git": False,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result
