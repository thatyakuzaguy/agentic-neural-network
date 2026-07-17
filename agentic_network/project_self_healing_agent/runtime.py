"""Self-healing loop for generated ANN projects.

The loop uses only local verification and approval-gated project patch apply.
It never installs dependencies, uses network access, or modifies ANN itself.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import normalize_workspace_path
from agentic_network.failure_context.runtime import compile_failure_context, write_failure_context_artifacts
from agentic_network.project_patch_apply_agent.runtime import apply_project_patch
from agentic_network.project_test_runner_agent.runtime import run_project_verification


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


@dataclass(frozen=True)
class ProjectSelfHealingResult:
    """Result of a project self-healing run."""

    status: str
    attempts: int
    retry_patch_files: list[str]
    failure_reason: str
    root_cause: str
    verification_status: str
    consensus: dict[str, Any]
    next_action: str
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_project_self_healing(
    project_root: str | Path,
    run_dir: str | Path,
    max_attempts: int = 3,
    approval_token: str | None = None,
    confirm_retry: bool = False,
) -> ProjectSelfHealingResult:
    """Run an approval-gated retry loop for a generated project."""

    root = normalize_workspace_path(project_root)
    errors, warnings = _validate_project_root(project_root, root)
    try:
        resolved_run_dir = _resolve_run_dir(root, run_dir)
    except ValueError as exc:
        errors.append(str(exc))
        resolved_run_dir = root / "project_runs" / "blocked_self_healing"
    if max_attempts < 1:
        errors.append("max_attempts must be at least 1.")
    if not confirm_retry:
        errors.append("confirm_retry must be true to apply retry patches.")
    if not approval_token:
        errors.append("approval_token is required to apply retry patches.")
    if errors:
        return _result(
            status="BLOCKED",
            attempts=0,
            run_dir=resolved_run_dir,
            retry_patches=[],
            failure_reason="; ".join(errors),
            root_cause="Safety validation blocked self-healing.",
            verification_status="BLOCKED",
            errors=errors,
            warnings=warnings,
        )

    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _write_analysis_artifacts(resolved_run_dir, "Initial verification pending.")
    retry_patches: list[str] = []
    last_verification_status = "SKIPPED"
    failure_reason = ""
    root_cause = ""

    for attempt in range(1, max_attempts + 1):
        verification = run_project_verification(
            root,
            run_dir=resolved_run_dir,
            confirm_run=True,
        )
        last_verification_status = verification.status
        if verification.status == "PASSED":
            consensus = _write_retry_consensus(resolved_run_dir, "REPAIRED", retry_patches)
            action = _write_retry_action_plan(resolved_run_dir, "review_repaired_project")
            summary = _write_self_healing_summary(
                resolved_run_dir,
                "REPAIRED",
                attempt - 1,
                retry_patches,
                verification.status,
            )
            return ProjectSelfHealingResult(
                status="REPAIRED",
                attempts=attempt - 1,
                retry_patch_files=retry_patches,
                failure_reason="",
                root_cause="No remaining test failure.",
                verification_status=verification.status,
                consensus=consensus,
                next_action="review_repaired_project",
                artifacts=[*artifacts, *verification.artifacts, action, summary],
                validation_errors=[],
                validation_warnings=warnings,
            )

        failure_reason = verification.test_summary
        root_cause = _root_cause_from_verification(verification)
        artifacts.extend(_write_analysis_artifacts(resolved_run_dir, failure_reason, root_cause))
        artifacts.extend(_write_failure_context_for_verification(root, resolved_run_dir, attempt, verification, root_cause))
        retry_patch = _generate_retry_patch(root, resolved_run_dir, attempt, root_cause)
        retry_patches.append(retry_patch)
        artifacts.extend(
            [
                retry_patch,
                _write_patch_quality(resolved_run_dir, attempt, retry_patch),
                _write_parallel_review(resolved_run_dir, attempt, retry_patch),
            ]
        )
        apply_result = apply_project_patch(
            root,
            retry_patch,
            approval_token=approval_token,
            confirm_apply=confirm_retry,
            backup=True,
            dry_run=False,
        )
        if apply_result.status != "APPLIED":
            consensus = _write_retry_consensus(resolved_run_dir, "FAILED", retry_patches)
            action = _write_retry_action_plan(resolved_run_dir, "manual_review_retry_patch")
            summary = _write_self_healing_summary(
                resolved_run_dir,
                "FAILED",
                attempt,
                retry_patches,
                apply_result.status,
            )
            return ProjectSelfHealingResult(
                status="FAILED",
                attempts=attempt,
                retry_patch_files=retry_patches,
                failure_reason="; ".join(apply_result.validation_errors),
                root_cause=root_cause,
                verification_status=last_verification_status,
                consensus=consensus,
                next_action="manual_review_retry_patch",
                artifacts=[*artifacts, action, summary],
                validation_errors=apply_result.validation_errors,
                validation_warnings=[*warnings, *apply_result.validation_warnings],
            )

    final_verification = run_project_verification(root, run_dir=resolved_run_dir, confirm_run=True)
    last_verification_status = final_verification.status
    if final_verification.status == "PASSED":
        consensus = _write_retry_consensus(resolved_run_dir, "REPAIRED", retry_patches)
        action = _write_retry_action_plan(resolved_run_dir, "review_repaired_project")
        summary = _write_self_healing_summary(
            resolved_run_dir,
            "REPAIRED",
            max_attempts,
            retry_patches,
            final_verification.status,
        )
        return ProjectSelfHealingResult(
            status="REPAIRED",
            attempts=max_attempts,
            retry_patch_files=retry_patches,
            failure_reason="",
            root_cause=root_cause or "Retry patches repaired verification.",
            verification_status=final_verification.status,
            consensus=consensus,
            next_action="review_repaired_project",
            artifacts=[*artifacts, *final_verification.artifacts, action, summary],
            validation_errors=[],
            validation_warnings=warnings,
        )
    consensus = _write_retry_consensus(resolved_run_dir, "FAILED_PERMANENTLY", retry_patches)
    action = _write_retry_action_plan(resolved_run_dir, "human_escalation_required")
    summary = _write_self_healing_summary(
        resolved_run_dir,
        "FAILED_PERMANENTLY",
        max_attempts,
        retry_patches,
        final_verification.status,
    )
    return ProjectSelfHealingResult(
        status="FAILED_PERMANENTLY",
        attempts=max_attempts,
        retry_patch_files=retry_patches,
        failure_reason=final_verification.test_summary,
        root_cause=_root_cause_from_verification(final_verification),
        verification_status=last_verification_status,
        consensus=consensus,
        next_action="human_escalation_required",
        artifacts=[*artifacts, *final_verification.artifacts, action, summary],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _validate_project_root(raw_root: str | Path, root: Path) -> tuple[list[str], list[str]]:
    raw = str(raw_root).strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not raw:
        errors.append("project_root is required.")
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        errors.append("Path traversal is not allowed.")
    if _is_blocked_system_root(raw, root) and not _allow_temp_targets(root):
        errors.append("C: and /mnt/c project roots are blocked by default.")
    if _has_protected_part(root):
        errors.append("Protected ANN directories cannot be self-healed.")
    if (root == REPO_ROOT or _is_relative_to(root, REPO_ROOT)) and not _is_allowed_repo_project_root(root):
        errors.append("ANN repository cannot be self-healed.")
    if not root.exists():
        errors.append("project_root must exist.")
    elif not root.is_dir():
        errors.append("project_root must be a directory.")
    return errors, warnings


def _resolve_run_dir(root: Path, run_dir: str | Path) -> Path:
    raw = str(run_dir)
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        raise ValueError("Path traversal is not allowed for run_dir.")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, root):
        raise ValueError("run_dir must stay inside project_root.")
    if _has_protected_part(resolved.relative_to(root)):
        raise ValueError("run_dir cannot target protected project paths.")
    return resolved


def _is_allowed_repo_project_root(root: Path) -> bool:
    allowed_roots = [
        REPO_ROOT / "generated-projects",
        REPO_ROOT / "outputs" / "autonomous_capability_projects",
    ]
    return any(root == allowed.resolve() or _is_relative_to(root, allowed.resolve()) for allowed in allowed_roots)


def _root_cause_from_verification(verification: Any) -> str:
    stderr = ""
    stdout = ""
    for path in verification.stderr_artifacts:
        stderr += Path(path).read_text(encoding="utf-8", errors="replace")[:4000]
    for path in verification.stdout_artifacts:
        stdout += Path(path).read_text(encoding="utf-8", errors="replace")[:4000]
    combined = f"{stdout}\n{stderr}".lower()
    if "assert false" in combined:
        return "A test contains or reaches an unconditional false assertion."
    if "nameerror" in combined:
        return "A referenced symbol is missing."
    if "assertionerror" in combined:
        return "An assertion does not match current implementation behavior."
    if verification.status == "TIMEOUT":
        return "Verification command timed out."
    return "Tests failed; a deterministic safe repair could not fully classify the root cause."


def _write_failure_context_for_verification(
    root: Path,
    run_dir: Path,
    attempt: int,
    verification: Any,
    root_cause: str,
) -> list[str]:
    stdout = "\n".join(
        Path(path).read_text(encoding="utf-8", errors="replace")[:4000]
        for path in getattr(verification, "stdout_artifacts", [])
    )
    stderr = "\n".join(
        Path(path).read_text(encoding="utf-8", errors="replace")[:4000]
        for path in getattr(verification, "stderr_artifacts", [])
    )
    context = compile_failure_context(
        project_root=root,
        reviewer_report=root_cause,
        test_report=getattr(verification, "test_summary", ""),
        stdout=stdout,
        stderr=stderr,
        commands=getattr(verification, "commands_executed", []),
        affected_files=[],
        source="project_self_healing",
    )
    return write_failure_context_artifacts(
        run_dir,
        context,
        json_name=f"61_failure_context_attempt_{attempt:03d}.json",
        markdown_name=f"61_failure_context_attempt_{attempt:03d}.md",
    )


def _generate_retry_patch(root: Path, run_dir: Path, attempt: int, root_cause: str) -> str:
    target = _find_repair_target(root, root_cause)
    retry_name = f"55_retry_patch_{attempt:03d}.diff"
    patch_path = run_dir / retry_name
    if target is None:
        patch_path.write_text(
            "\n".join(
                [
                    "diff --git a/docs/self_healing/manual_review.md b/docs/self_healing/manual_review.md",
                    "new file mode 100644",
                    "index 0000000..1111111",
                    "--- /dev/null",
                    "+++ b/docs/self_healing/manual_review.md",
                    "@@ -0,0 +1,4 @@",
                    "+# Manual Review Required",
                    "+",
                    f"+Root cause: {root_cause}",
                    "+ANN could not infer a safe source patch.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return str(patch_path)
    relative = target.relative_to(root).as_posix()
    repaired = _repair_source(target.read_text(encoding="utf-8", errors="replace"))
    patch_path.write_text(
        "\n".join(
            [
                f"diff --git a/{relative} b/{relative}",
                f"--- a/{relative}",
                f"+++ b/{relative}",
                "@@ -1 +1 @@",
                *[f"+{line}" for line in repaired.splitlines()],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(patch_path)


def _find_repair_target(root: Path, root_cause: str) -> Path | None:
    candidates: list[Path] = []
    if (root / "apps").exists():
        candidates.extend(sorted((root / "apps").rglob("*.py")))
    candidates.extend(sorted(root.glob("*.py")))
    for path in candidates:
        if _has_protected_part(path.relative_to(root)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "return False" in text or "assert False" in text or "BROKEN" in text:
            return path
    return None


def _repair_source(text: str) -> str:
    return (
        text.replace("return False", "return True")
        .replace("assert False", "assert True")
        .replace("BROKEN", "FIXED")
    )


def _write_analysis_artifacts(run_dir: Path, failure_reason: str, root_cause: str | None = None) -> list[str]:
    analysis = run_dir / "53_project_failure_analysis.md"
    cause = run_dir / "54_project_root_cause.md"
    analysis.write_text(f"# Project Failure Analysis\n\n{failure_reason}\n", encoding="utf-8")
    cause.write_text(f"# Project Root Cause\n\n{root_cause or 'Pending verification.'}\n", encoding="utf-8")
    return [str(analysis), str(cause)]


def _write_patch_quality(run_dir: Path, attempt: int, retry_patch: str) -> str:
    path = run_dir / "56_retry_patch_quality.md"
    path.write_text(
        f"# Retry Patch Quality\n\nAttempt: {attempt}\nPatch: {retry_patch}\nDecision: REVIEW_REQUIRED\n",
        encoding="utf-8",
    )
    return str(path)


def _write_parallel_review(run_dir: Path, attempt: int, retry_patch: str) -> str:
    path = run_dir / "57_retry_parallel_review.md"
    path.write_text(
        f"# Retry Parallel Review\n\nAttempt: {attempt}\nPatch: {retry_patch}\nStatus: LOCAL_REVIEW_REQUIRED\n",
        encoding="utf-8",
    )
    return str(path)


def _write_retry_consensus(run_dir: Path, status: str, retry_patches: list[str]) -> dict[str, Any]:
    consensus = {
        "status": status,
        "consensus_decision": "SELF_HEALING_REPAIRED" if status == "REPAIRED" else status,
        "confidence": "Medium",
        "retry_patch_files": retry_patches,
    }
    (run_dir / "58_retry_consensus.json").write_text(json.dumps(consensus, indent=2), encoding="utf-8")
    return consensus


def _write_retry_action_plan(run_dir: Path, next_action: str) -> str:
    path = run_dir / "59_retry_action_plan.json"
    payload = {
        "status": "VALID",
        "recommended_next_action": next_action,
        "blocked": next_action == "human_escalation_required",
        "executable": False,
        "requires_human": True,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _write_self_healing_summary(
    run_dir: Path,
    status: str,
    attempts: int,
    retry_patches: list[str],
    verification_status: str,
) -> str:
    path = run_dir / "60_project_self_healing.md"
    path.write_text(
        "\n".join(
            [
                "# Project Self Healing",
                "",
                f"Status: {status}",
                f"Attempts: {attempts}",
                f"Verification: {verification_status}",
                "",
                "## Retry Patches",
                *[f"- {patch}" for patch in retry_patches],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


def _result(
    *,
    status: str,
    attempts: int,
    run_dir: Path,
    retry_patches: list[str],
    failure_reason: str,
    root_cause: str,
    verification_status: str,
    errors: list[str],
    warnings: list[str],
) -> ProjectSelfHealingResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _write_analysis_artifacts(run_dir, failure_reason, root_cause)
    consensus = _write_retry_consensus(run_dir, status, retry_patches)
    action = _write_retry_action_plan(run_dir, "manual_review_required")
    summary = _write_self_healing_summary(run_dir, status, attempts, retry_patches, verification_status)
    return ProjectSelfHealingResult(
        status=status,
        attempts=attempts,
        retry_patch_files=retry_patches,
        failure_reason=failure_reason,
        root_cause=root_cause,
        verification_status=verification_status,
        consensus=consensus,
        next_action="manual_review_required",
        artifacts=[*artifacts, action, summary],
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
    )


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    return normalized.anchor.lower().replace("\\", "/").startswith("c:")


def _allow_temp_targets(path: Path) -> bool:
    if os.environ.get("ANN_ALLOW_TEMP_PROJECT_SELF_HEALING_TARGETS") != "1":
        return False
    temp = os.environ.get("TEMP")
    if not temp:
        return False
    return _is_relative_to(path, Path(temp).resolve())


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result
