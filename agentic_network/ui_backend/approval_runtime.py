"""Local UI approval artifacts for ANN runs.

This module deliberately records review intent only. It does not apply patches,
invoke Patch Apply, run shell commands, or mutate files outside the selected run.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from agentic_network.ui_backend import runtime as ui_runtime

APPROVAL_STATUS = "APPROVED_FOR_REVIEW"
APPROVAL_AUDIT_FILE = "ui_approval_audit.md"
TOKEN_ENV_VAR = "ANN_UI_APPROVAL_TOKEN"
DIFF_FILE_LINE = re.compile(r"^(?:---|\+\+\+)\s+(.+?)\s*$")
WINDOWS_C_PATTERN = re.compile(r"(?i)(?:c:[\\/]|/mnt/c\b)")
PROTECTED_PATH_PATTERN = re.compile(
    r"(?i)(?:^|/)(?:\.git|models|memory|knowledge|unsloth_compiled_cache)(?:/|$)|"
    r"(?:^|/)training/(?:datasets|adapters)(?:/|$)|"
    r"(?:^|/)outputs/(?!runs/[^/]+(?:/|$))"
)


def get_patch_metadata(run_id: str, patch_name: str, runs_root: Path | None = None) -> dict[str, Any]:
    root = ui_runtime._resolve_runs_root(runs_root)
    run_dir = ui_runtime._resolve_run_dir(root, run_id)
    patch_text = ui_runtime.read_patch(run_id, patch_name, root)
    summary = ui_runtime._read_summary(run_dir)
    touched = _files_touched(patch_text)
    protected = any(
        PROTECTED_PATH_PATTERN.search(path) or _is_forbidden_outputs_path(path, run_id)
        for path in touched
    )
    c_drive = bool(WINDOWS_C_PATTERN.search(patch_text)) or any(_is_c_drive_path(path) for path in touched)
    model_dataset_training = any(_is_model_dataset_training_path(path) for path in touched)
    creates = _creates_files(patch_text)
    deletes = _deletes_files(patch_text)
    reasons = _approval_reasons(
        files_touched=touched,
        protected_path_detected=protected,
        c_drive_detected=c_drive,
        model_dataset_training_detected=model_dataset_training,
    )
    return {
        "patch_name": patch_name,
        "files_touched": touched,
        "creates_files": creates,
        "deletes_files": deletes,
        "protected_path_detected": protected,
        "c_drive_detected": c_drive,
        "model_dataset_training_detected": model_dataset_training,
        "patch_quality_decision": _summary_value(summary, "patch_quality_decision"),
        "patch_approval_decision": _summary_value(summary, "patch_approval_decision"),
        "can_be_approved_from_ui": not (protected or c_drive or model_dataset_training),
        "reasons": reasons,
    }


def approve_patch(
    run_id: str,
    payload: dict[str, Any],
    runs_root: Path | None = None,
) -> dict[str, Any]:
    root = ui_runtime._resolve_runs_root(runs_root)
    run_dir = ui_runtime._resolve_run_dir(root, run_id)
    patch_name = str(payload.get("patch_name") or "").strip()
    token = str(payload.get("approval_token") or "")
    note = str(payload.get("note") or "").strip()
    if not patch_name:
        raise HTTPException(status_code=400, detail="patch_name is required.")
    _validate_approval_token(token)
    if payload.get("confirm_reviewed") is not True:
        raise HTTPException(status_code=400, detail="confirm_reviewed must be true.")
    if payload.get("confirm_no_apply") is not True:
        raise HTTPException(status_code=400, detail="confirm_no_apply must be true.")

    metadata = get_patch_metadata(run_id, patch_name, root)
    if not metadata["can_be_approved_from_ui"]:
        raise HTTPException(status_code=403, detail="Patch is blocked by UI approval safety metadata.")

    now = datetime.now(timezone.utc).isoformat()
    artifact_name = _approval_artifact_name(patch_name)
    artifact_path = (run_dir / artifact_name).resolve()
    if not ui_runtime._is_relative_to(artifact_path, run_dir):
        raise HTTPException(status_code=403, detail="Approval artifact path blocked.")
    artifact_payload = {
        "status": APPROVAL_STATUS,
        "run_id": run_id,
        "patch_name": patch_name,
        "approved_at": now,
        "applied": False,
        "confirm_reviewed": True,
        "confirm_no_apply": True,
        "note": note,
        "metadata": metadata,
    }
    artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")
    audit_path = _append_audit(run_dir, artifact_payload)
    return {
        "status": APPROVAL_STATUS,
        "patch_name": patch_name,
        "applied": False,
        "artifact": artifact_path.relative_to(run_dir).as_posix(),
        "audit": audit_path.relative_to(run_dir).as_posix(),
    }


def list_approvals(run_id: str, runs_root: Path | None = None) -> dict[str, Any]:
    root = ui_runtime._resolve_runs_root(runs_root)
    run_dir = ui_runtime._resolve_run_dir(root, run_id)
    approvals: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("ui_approval_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            approvals.append(
                {
                    "artifact": path.name,
                    "status": _text(payload.get("status")),
                    "patch_name": _text(payload.get("patch_name")),
                    "approved_at": _text(payload.get("approved_at")),
                    "applied": payload.get("applied") is True,
                    "note": _text(payload.get("note")),
                }
            )
    return {"run_id": run_id, "approvals": approvals}


def _validate_approval_token(token: str) -> None:
    expected = os.getenv(TOKEN_ENV_VAR, "")
    if not token:
        raise HTTPException(status_code=401, detail="approval_token is required.")
    if not expected:
        raise HTTPException(status_code=403, detail=f"{TOKEN_ENV_VAR} is not configured.")
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="approval_token is invalid.")


def _files_touched(patch_text: str) -> list[str]:
    paths: list[str] = []
    for line in patch_text.splitlines():
        match = DIFF_FILE_LINE.search(line)
        if not match:
            continue
        normalized = _normalize_diff_path(match.group(1))
        if normalized:
            paths.append(normalized)
    return _dedupe(paths)


def _creates_files(patch_text: str) -> bool:
    return any(line.strip() == "--- /dev/null" for line in patch_text.splitlines())


def _deletes_files(patch_text: str) -> bool:
    return any(line.strip() == "+++ /dev/null" for line in patch_text.splitlines())


def _normalize_diff_path(raw_path: str) -> str:
    text = raw_path.strip().strip('"').strip("'")
    if "\t" in text:
        text = text.split("\t", 1)[0]
    if text.startswith(("a/", "b/")):
        text = text[2:]
    return "" if text in {"old", "new", "/dev/null"} else text.replace("\\", "/")


def _is_c_drive_path(path: str) -> bool:
    text = path.strip().lower().replace("\\", "/")
    return text.startswith("c:/") or text.startswith("/mnt/c")


def _is_model_dataset_training_path(path: str) -> bool:
    text = path.strip().lower().replace("\\", "/")
    return (
        text.startswith("models/")
        or text.startswith("training/datasets/")
        or text.startswith("training/adapters/")
        or text.startswith("unsloth_compiled_cache/")
    )


def _is_forbidden_outputs_path(path: str, run_id: str) -> bool:
    text = path.strip().lower().replace("\\", "/")
    allowed_prefix = f"outputs/runs/{run_id.lower()}/"
    return text.startswith("outputs/") and not text.startswith(allowed_prefix)


def _approval_reasons(
    *,
    files_touched: list[str],
    protected_path_detected: bool,
    c_drive_detected: bool,
    model_dataset_training_detected: bool,
) -> list[str]:
    reasons: list[str] = []
    if not files_touched:
        reasons.append("No touched files were detected in the patch.")
    if protected_path_detected:
        reasons.append("Patch touches a protected ANN path.")
    if c_drive_detected:
        reasons.append("Patch references C: or /mnt/c, which UI approval blocks.")
    if model_dataset_training_detected:
        reasons.append("Patch touches model, dataset, adapter, or training cache paths.")
    if not reasons:
        reasons.append("Patch metadata passed UI approval safety checks.")
    return reasons


def _approval_artifact_name(patch_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", patch_name).strip("._")
    if not safe_name:
        safe_name = "patch"
    return f"ui_approval_{safe_name}.json"


def _append_audit(run_dir: Path, approval: dict[str, Any]) -> Path:
    audit_path = (run_dir / APPROVAL_AUDIT_FILE).resolve()
    if not ui_runtime._is_relative_to(audit_path, run_dir):
        raise HTTPException(status_code=403, detail="Approval audit path blocked.")
    line = (
        f"- {approval['approved_at']} | {approval['status']} | "
        f"{approval['patch_name']} | applied=false | note={approval['note'] or 'none'}\n"
    )
    header = "# UI Approval Audit\n\n"
    if not audit_path.exists():
        audit_path.write_text(header + line, encoding="utf-8")
    else:
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return audit_path


def _summary_value(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else "UNKNOWN"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
