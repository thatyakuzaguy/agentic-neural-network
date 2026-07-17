"""ANN v4.0 guarded autonomous engineering loop.

The loop coordinates existing safety-gated stages. It does not synthesize
patches itself, apply custom writes, run arbitrary commands, or bypass approval.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_network.human_approval_agent.runtime import authorize_apply
from agentic_network.pipeline.parallel_gate_runtime import evaluate_parallel_review_gate
from agentic_network.patch_apply_agent.runtime import (
    APPLY_STATUS_APPLIED,
    apply_approved_patches,
)
from agentic_network.patch_approval_agent.runtime import approve_patches as evaluate_patch_approval
from agentic_network.patch_quality_agent.runtime import (
    IMPLEMENTATION_READY,
    evaluate_patch_quality,
)
from agentic_network.safety.filesystem_policy import load_filesystem_policy
from agentic_network.self_healing_agent.runtime import (
    STATUS_RETRY_PATCH_GENERATED as SELF_HEALING_STATUS_RETRY_PATCH_GENERATED,
    run_self_healing,
)
from agentic_network.test_runner_agent.runtime import run_tests_for_run
from agentic_network.failure_context.runtime import compile_failure_context, write_failure_context_artifacts

AUTONOMOUS_LOOP_FILE = "27_autonomous_loop.md"
ATTEMPT_FILE_TEMPLATE = "28_autonomous_attempt_{attempt:03d}.md"
RETRY_PATCH_QUALITY_FILE = "29_retry_patch_quality.md"
RETRY_PATCH_APPROVAL_FILE = "30_retry_patch_approval.md"
RETRY_HUMAN_APPROVAL_FILE = "31_retry_human_approval.md"
RETRY_PATCH_APPLY_FILE = "32_retry_patch_apply.md"
RETRY_TEST_RUN_FILE = "33_retry_test_run.md"
RETRY_TEST_FAILURE_ANALYSIS_TEMPLATE = "34_retry_test_failure_analysis_attempt_{attempt:03d}.md"
RETRY_FAILURE_FOLLOWUP_PLAN_TEMPLATE = "35_retry_failure_followup_plan_attempt_{attempt:03d}.md"
RETRY_FAILURE_LOOP_TEMPLATE = "36_retry_failure_loop_attempt_{attempt:03d}.md"
RETRY_PATCHES_DIR = "retry_patches"
ATTEMPT_WORK_DIR = "autonomous_attempts"
SUMMARY_FILE = "summary.json"

STATUS_SKIPPED = "SKIPPED"
STATUS_PASSED = "PASSED"
STATUS_RETRY_PATCH_GENERATED = "RETRY_PATCH_GENERATED"
STATUS_RETRY_APPLIED = "RETRY_APPLIED"
STATUS_FAILED_TESTS = "FAILED_TESTS"
STATUS_FAILED_APPROVAL = "FAILED_APPROVAL"
STATUS_FAILED_APPLY = "FAILED_APPLY"
STATUS_FAILED_PERMANENTLY = "FAILED_PERMANENTLY"
STATUS_BLOCKED = "BLOCKED"

FAILED_TEST_STATUSES = {"FAILED", "TIMEOUT"}
PASSING_TEST_STATUSES = {"PASSED", "NO_TESTS_DETECTED"}
APPLIED_STATUSES = {"APPLIED", "DRY_RUN_PASSED"}


@dataclass(frozen=True)
class AutonomousLoopAttempt:
    """One guarded autonomous repair attempt."""

    attempt: int
    status: str
    artifact_path: str
    input_test_status: str
    self_healing_status: str
    retry_patch_path: str
    patch_quality_decision: str
    patch_approval_decision: str
    patch_apply_status: str
    test_result_status: str
    validation_errors: list[str]
    validation_warnings: list[str]
    failure_reason: str = ""
    failure_artifacts: list[str] = field(default_factory=list)
    failure_next_action: str = ""


@dataclass(frozen=True)
class AutonomousLoopResult:
    """Final result for the guarded autonomous loop."""

    run_dir: str
    status: str
    attempts: list[AutonomousLoopAttempt]
    max_attempts: int
    artifact_path: str
    last_error: str
    last_retry_patch: str
    validation_errors: list[str]
    validation_warnings: list[str]
    report: str

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def run_autonomous_engineering_loop(
    run_dir: Path,
    max_attempts: int = 3,
    approve_patches: bool = False,
    approval_token: str | None = None,
    run_tests: bool = False,
    timeout_seconds: int = 300,
) -> AutonomousLoopResult:
    """Run guarded autonomous repair attempts after apply and test stages."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    attempts: list[AutonomousLoopAttempt] = []
    last_retry_patch = ""
    last_error = ""

    initial_errors = _validate_initial_state(
        resolved_run_dir,
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
    )
    errors.extend(initial_errors)
    summary = _load_summary(resolved_run_dir, warnings)
    parallel_gate = evaluate_parallel_review_gate(resolved_run_dir)
    test_status = _status(summary.get("test_runner_status"))
    patch_apply_status = _status(summary.get("patch_apply_status"))

    if parallel_gate.blocks_autonomous_loop:
        status = STATUS_BLOCKED
        last_error = f"parallel_review_gate_blocks_autonomous_loop:{parallel_gate.decision}"
        errors.append(last_error)
        errors.extend(parallel_gate.validation_errors)
    elif not run_tests:
        status = STATUS_SKIPPED
        warnings.append("run_tests_flag_missing")
        last_error = "Autonomous loop requires --run-tests."
    elif initial_errors:
        status = STATUS_BLOCKED
        last_error = initial_errors[0]
    elif patch_apply_status not in APPLIED_STATUSES:
        status = STATUS_BLOCKED
        last_error = "patch_apply_must_happen_first"
        errors.append("patch_apply_must_happen_first")
    elif test_status in PASSING_TEST_STATUSES:
        status = STATUS_PASSED
    elif test_status not in FAILED_TEST_STATUSES:
        status = STATUS_BLOCKED
        last_error = f"unsupported_test_status:{test_status or 'UNKNOWN'}"
        errors.append(last_error)
    else:
        status = STATUS_FAILED_TESTS
        for attempt_number in range(1, max_attempts + 1):
            attempt = _run_attempt(
                run_dir=resolved_run_dir,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                approve_patches=approve_patches,
                approval_token=approval_token,
                run_tests=run_tests,
                timeout_seconds=timeout_seconds,
            )
            attempts.append(attempt)
            last_retry_patch = attempt.retry_patch_path
            if attempt.validation_errors:
                last_error = attempt.validation_errors[0]
            if attempt.failure_reason:
                last_error = attempt.failure_reason
            if attempt.status == STATUS_PASSED:
                status = STATUS_PASSED
                last_error = ""
                break
            if attempt.status in {STATUS_FAILED_TESTS, STATUS_RETRY_APPLIED}:
                status = STATUS_FAILED_TESTS
                continue
            if attempt.status in {STATUS_FAILED_APPROVAL, STATUS_FAILED_APPLY, STATUS_FAILED_PERMANENTLY}:
                status = attempt.status
                break
        else:
            status = STATUS_FAILED_PERMANENTLY
            last_error = "max_attempts_reached"

    artifact_path = resolved_run_dir / AUTONOMOUS_LOOP_FILE
    report = _render_loop_report(
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        last_error=last_error,
        last_retry_patch=last_retry_patch,
        warnings=_dedupe(warnings),
        errors=_dedupe(errors),
    )
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    result = AutonomousLoopResult(
        run_dir=str(resolved_run_dir),
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        artifact_path=str(artifact_path),
        last_error=last_error,
        last_retry_patch=last_retry_patch,
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
        report=report,
    )
    _update_summary(resolved_run_dir, result)
    return result


def autonomous_loop_summary_fields(result: AutonomousLoopResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    retry_failure_attempt = _last_failure_attempt(result)
    retry_failure_detected = retry_failure_attempt is not None
    retry_failure_artifacts = retry_failure_attempt.failure_artifacts if retry_failure_attempt else []
    retry_failure_next_action = ""
    if retry_failure_attempt:
        if result.status == STATUS_PASSED:
            retry_failure_next_action = "resolved"
        elif result.status == STATUS_FAILED_PERMANENTLY:
            retry_failure_next_action = "max_attempts_exhausted"
        else:
            retry_failure_next_action = retry_failure_attempt.failure_next_action
    return {
        "autonomous_loop_enabled": True,
        "autonomous_loop_status": result.status,
        "autonomous_loop_attempts": len(result.attempts),
        "autonomous_loop_attempt_artifacts": [attempt.artifact_path for attempt in result.attempts],
        "autonomous_loop_max_attempts": result.max_attempts,
        "autonomous_loop_last_error": result.last_error,
        "autonomous_loop_last_retry_patch": result.last_retry_patch,
        "autonomous_loop_retry_quality_decision": _last_attempt_value(result, "patch_quality_decision"),
        "autonomous_loop_retry_approval_decision": _last_attempt_value(result, "patch_approval_decision"),
        "autonomous_loop_retry_apply_status": _last_attempt_value(result, "patch_apply_status"),
        "autonomous_loop_retry_test_status": _last_attempt_value(result, "test_result_status"),
        "autonomous_loop_retry_failure_detected": retry_failure_detected,
        "autonomous_loop_retry_failure_attempt": retry_failure_attempt.attempt if retry_failure_attempt else 0,
        "autonomous_loop_retry_failure_reason": retry_failure_attempt.failure_reason if retry_failure_attempt else "",
        "autonomous_loop_retry_failure_artifacts": retry_failure_artifacts,
        "autonomous_loop_retry_failure_next_action": retry_failure_next_action,
        "autonomous_loop_validation_passed": result.validation_passed,
        "autonomous_loop_validation_errors": result.validation_errors,
        "autonomous_loop_validation_warnings": result.validation_warnings,
    }


def _run_attempt(
    *,
    run_dir: Path,
    attempt_number: int,
    max_attempts: int,
    approve_patches: bool,
    approval_token: str | None,
    run_tests: bool,
    timeout_seconds: int,
) -> AutonomousLoopAttempt:
    warnings: list[str] = []
    errors: list[str] = []
    summary = _load_summary(run_dir, warnings)
    input_test_status = _status(summary.get("retry_test_runner_status") or summary.get("test_runner_status"))
    retry_patch_path = ""
    quality_decision = ""
    approval_decision = ""
    apply_status = ""
    test_result_status = ""
    failure_reason = ""
    failure_artifacts: list[str] = []
    failure_next_action = ""

    healing = run_self_healing(run_dir, max_attempts=max(attempt_number, 1))
    if healing.status != SELF_HEALING_STATUS_RETRY_PATCH_GENERATED or not healing.retry_patch_path:
        errors.extend(healing.validation_errors or ["retry_patch_not_generated"])
        status = STATUS_FAILED_PERMANENTLY
        return _write_attempt(
            run_dir=run_dir,
            attempt_number=attempt_number,
            status=status,
            input_test_status=input_test_status,
            self_healing_status=healing.status,
            retry_patch_path="",
            patch_quality_decision=quality_decision,
            patch_approval_decision=approval_decision,
            patch_apply_status=apply_status,
            test_result_status=test_result_status,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings + healing.validation_warnings),
        )

    retry_patch_path = _register_retry_patch(run_dir, Path(healing.retry_patch_path), attempt_number)
    _write_retry_summary_fields(
        run_dir,
        {
            "autonomous_loop_last_retry_patch": retry_patch_path,
            "autonomous_loop_retry_patch_registered": True,
        },
        output_files={"autonomous_retry_patch": retry_patch_path},
    )
    quality = evaluate_patch_quality(
        run_dir,
        patch_dir=RETRY_PATCHES_DIR,
        artifact_name=RETRY_PATCH_QUALITY_FILE,
    )
    quality_decision = quality.decision
    _write_retry_summary_fields(
        run_dir,
        {
            "retry_patch_quality_status": "VALID" if quality.validation_passed else "INVALID",
            "retry_patch_quality_decision": quality.decision,
            "retry_patch_quality_score": quality.score,
            "retry_patch_quality_validation_passed": quality.validation_passed,
            "retry_patch_quality_validation_errors": quality.validation_errors,
            "retry_patch_quality_validation_warnings": quality.warnings,
            "autonomous_loop_retry_quality_decision": quality.decision,
        },
        output_files={"retry_patch_quality": quality.artifact_path},
    )
    if quality.decision != IMPLEMENTATION_READY or not quality.validation_passed:
        errors.extend(quality.validation_errors or [f"patch_quality_not_ready:{quality.decision}"])
        return _write_attempt(
            run_dir=run_dir,
            attempt_number=attempt_number,
            status=STATUS_FAILED_APPROVAL,
            input_test_status=input_test_status,
            self_healing_status=healing.status,
            retry_patch_path=retry_patch_path,
            patch_quality_decision=quality_decision,
            patch_approval_decision=approval_decision,
            patch_apply_status=apply_status,
            test_result_status=test_result_status,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings + quality.warnings),
        )

    approval = evaluate_patch_approval(
        run_dir,
        patch_dir=RETRY_PATCHES_DIR,
        artifact_name=RETRY_PATCH_APPROVAL_FILE,
    )
    approval_decision = approval.decision
    _write_retry_summary_fields(
        run_dir,
        {
            "retry_patch_approval_status": "VALID" if approval.validation_passed else "INVALID",
            "retry_patch_approval_decision": approval.decision,
            "retry_patch_approval_validation_passed": approval.validation_passed,
            "retry_patch_approval_validation_errors": approval.validation_errors,
            "retry_patch_approval_validation_warnings": approval.warnings,
            "autonomous_loop_retry_approval_decision": approval.decision,
        },
        output_files={"retry_patch_approval": approval.artifact_path},
    )
    if approval.decision != "Approved" or not approval.validation_passed:
        errors.extend(approval.validation_errors or ["patch_approval_not_approved"])
        return _write_attempt(
            run_dir=run_dir,
            attempt_number=attempt_number,
            status=STATUS_FAILED_APPROVAL,
            input_test_status=input_test_status,
            self_healing_status=healing.status,
            retry_patch_path=retry_patch_path,
            patch_quality_decision=quality_decision,
            patch_approval_decision=approval_decision,
            patch_apply_status=apply_status,
            test_result_status=test_result_status,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings + approval.warnings),
        )

    if approve_patches:
        human = authorize_apply(
            run_dir,
            approval_token=approval_token,
            approve_apply=True,
            artifact_name=RETRY_HUMAN_APPROVAL_FILE,
            required_artifacts=(SUMMARY_FILE, RETRY_PATCH_APPROVAL_FILE),
            summary_prefix="retry_human_approval",
            patch_approval_decision_key="retry_patch_approval_decision",
            patch_approval_validation_key="retry_patch_approval_validation_passed",
            patch_approval_errors_key="retry_patch_approval_validation_errors",
            require_merge_readiness=False,
        )
        _write_retry_summary_fields(
            run_dir,
            {
                "autonomous_loop_retry_human_approval_decision": human.decision,
            },
            output_files={"retry_human_approval": human.artifact_path},
        )
        if human.decision != "Approved" or not human.validation_passed:
            errors.extend(human.validation_errors or ["human_approval_not_approved"])
            return _write_attempt(
                run_dir=run_dir,
                attempt_number=attempt_number,
                status=STATUS_FAILED_APPROVAL,
                input_test_status=input_test_status,
                self_healing_status=healing.status,
                retry_patch_path=retry_patch_path,
                patch_quality_decision=quality_decision,
                patch_approval_decision=approval_decision,
                patch_apply_status=apply_status,
                test_result_status=test_result_status,
                errors=_dedupe(errors),
                warnings=_dedupe(warnings + human.warnings),
            )
    else:
        errors.append("approve_patches_required_for_retry_apply")
        return _write_attempt(
            run_dir=run_dir,
            attempt_number=attempt_number,
            status=STATUS_FAILED_APPROVAL,
            input_test_status=input_test_status,
            self_healing_status=healing.status,
            retry_patch_path=retry_patch_path,
            patch_quality_decision=quality_decision,
            patch_approval_decision=approval_decision,
            patch_apply_status=apply_status,
            test_result_status=test_result_status,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings),
        )

    apply_result = apply_approved_patches(
        run_dir,
        approve_patches=approve_patches,
        dry_run=False,
        patch_dir=RETRY_PATCHES_DIR,
        output_artifact=RETRY_PATCH_APPLY_FILE,
        human_approval_artifact=RETRY_HUMAN_APPROVAL_FILE,
        summary_prefix="retry_patch_apply",
        approval_decision_key="retry_patch_approval_decision",
        approval_validation_key="retry_patch_approval_validation_passed",
        human_decision_key="retry_human_approval_decision",
        human_validation_key="retry_human_approval_validation_passed",
    )
    apply_status = apply_result.status
    _write_retry_summary_fields(
        run_dir,
        {
            "autonomous_loop_retry_apply_status": apply_result.status,
        },
        output_files={"retry_patch_apply": apply_result.artifact_path},
    )
    if apply_result.status != APPLY_STATUS_APPLIED:
        errors.extend(apply_result.validation_errors or [f"patch_apply_status:{apply_result.status}"])
        status = STATUS_FAILED_APPLY
    else:
        test_result = run_tests_for_run(
            run_dir,
            run_tests=run_tests,
            timeout_seconds=timeout_seconds,
            artifact_name=RETRY_TEST_RUN_FILE,
            summary_prefix="retry_test_runner",
        )
        normalized_test_status = _status(test_result.status)
        test_result_status = (
            normalized_test_status
            if normalized_test_status in PASSING_TEST_STATUSES
            else STATUS_FAILED_TESTS
        )
        _write_retry_summary_fields(
            run_dir,
            {
                "autonomous_loop_retry_test_status": test_result_status,
            },
            output_files={"retry_test_runner": test_result.artifact_path},
        )
        if normalized_test_status in PASSING_TEST_STATUSES:
            status = STATUS_PASSED
        else:
            status = STATUS_FAILED_TESTS
            failure_reason = f"retry_tests_failed:{normalized_test_status or 'UNKNOWN'}"
            failure_next_action = (
                f"retry_attempt_{attempt_number + 1:03d}"
                if attempt_number < max_attempts
                else "max_attempts_exhausted"
            )
            failure_artifacts = _write_retry_test_failure_artifacts(
                run_dir=run_dir,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                retry_patch_path=retry_patch_path,
                apply_result=apply_result,
                test_result=test_result,
                reason=failure_reason,
            )

    return _write_attempt(
        run_dir=run_dir,
        attempt_number=attempt_number,
        status=status,
        input_test_status=input_test_status,
        self_healing_status=healing.status,
        retry_patch_path=retry_patch_path,
        patch_quality_decision=quality_decision,
        patch_approval_decision=approval_decision,
        patch_apply_status=apply_status,
        test_result_status=test_result_status,
        errors=_dedupe(errors),
        warnings=_dedupe(warnings),
        failure_reason=failure_reason,
        failure_artifacts=failure_artifacts,
        failure_next_action=failure_next_action,
    )


def _register_retry_patch(run_dir: Path, source_patch: Path, attempt_number: int) -> str:
    retry_dir = run_dir / RETRY_PATCHES_DIR
    retry_dir.mkdir(parents=True, exist_ok=True)
    target = retry_dir / f"retry_patch_{attempt_number:03d}.diff"
    target.write_text(source_patch.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
    return str(target)


def _write_retry_test_failure_artifacts(
    *,
    run_dir: Path,
    attempt_number: int,
    max_attempts: int,
    retry_patch_path: str,
    apply_result: Any,
    test_result: Any,
    reason: str,
) -> list[str]:
    next_action = f"retry_attempt_{attempt_number + 1:03d}" if attempt_number < max_attempts else "max_attempts_exhausted"
    test_status = str(getattr(test_result, "status", "") or "UNKNOWN")
    test_artifact = str(getattr(test_result, "artifact_path", "") or "")
    stdout = _test_result_text(test_result, "stdout", "stdout_summary")
    stderr = _test_result_text(test_result, "stderr", "stderr_summary")
    commands = _test_result_list(test_result, "commands_executed", "commands_selected", "commands")
    files_affected = _test_result_list(apply_result, "files_modified", "files_changed", "touched_files")
    patch_excerpt = _read_excerpt(Path(retry_patch_path), max_chars=6000)
    test_report = _read_excerpt(Path(test_artifact), max_chars=6000) if test_artifact else ""

    analysis_path = run_dir / RETRY_TEST_FAILURE_ANALYSIS_TEMPLATE.format(attempt=attempt_number)
    plan_path = run_dir / RETRY_FAILURE_FOLLOWUP_PLAN_TEMPLATE.format(attempt=attempt_number)
    loop_path = run_dir / RETRY_FAILURE_LOOP_TEMPLATE.format(attempt=attempt_number)

    analysis_path.write_text(
        "\n".join(
            [
                "RETRY TEST FAILURE ANALYSIS",
                f"- Attempt: {attempt_number}.",
                f"- Status: {STATUS_FAILED_TESTS}.",
                f"- Reason: {reason}.",
                f"- Test runner status: {test_status}.",
                f"- Test artifact: {test_artifact or 'None'}.",
                f"- Retry patch: {retry_patch_path or 'None'}.",
                "",
                "COMMANDS EXECUTED",
                *_bullets(commands),
                "",
                "FILES AFFECTED",
                *_bullets(files_affected),
                "",
                "STDOUT",
                _fenced(stdout or "None"),
                "",
                "STDERR",
                _fenced(stderr or "None"),
                "",
                "TEST REPORT EXCERPT",
                _fenced(test_report or "None"),
                "",
                "PATCH APPLIED EXCERPT",
                _fenced(patch_excerpt or "None"),
                "",
                "CONFIDENCE",
                "High",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    plan_path.write_text(
        "\n".join(
            [
                "RETRY FAILURE FOLLOWUP PLAN",
                f"- Attempt: {attempt_number}.",
                f"- Next action: {next_action}.",
                "- Reuse the failed test stdout, stderr, command list, affected files, and applied patch as repair context.",
                "- Generate a new retry patch through the existing Self Healing stage.",
                "- Preserve Patch Quality, Retry Patch Approval, Retry Human Approval, Patch Apply, and Test Runner gates.",
                "- Stop with FAILED_PERMANENTLY if max attempts are exhausted.",
                "",
                "FOCUS AREAS",
                *_bullets(_derive_focus_areas(stdout=stdout, stderr=stderr, commands=commands, files_affected=files_affected)),
                "",
                "CONFIDENCE",
                "High",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    loop_path.write_text(
        "\n".join(
            [
                "RETRY FAILURE LOOP",
                f"- Attempt: {attempt_number}.",
                f"- Max attempts: {max_attempts}.",
                "- Retry failure detected: true.",
                f"- Current status: {STATUS_FAILED_TESTS}.",
                f"- Next action: {next_action}.",
                f"- Failure analysis artifact: {analysis_path}.",
                f"- Followup plan artifact: {plan_path}.",
                "",
                "LOOP RULES",
                "- Do not apply patches without --approve-patches and a valid token.",
                "- Do not run tests without --run-tests.",
                "- Do not bypass v4.1 quality, approval, human approval, apply, or test gates.",
                "",
                "CONFIDENCE",
                "High",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )

    failure_context = compile_failure_context(
        project_root=run_dir,
        reviewer_report=reason,
        test_report=test_report,
        stdout=stdout,
        stderr=stderr,
        commands=commands,
        affected_files=files_affected,
        patch_text=patch_excerpt,
        artifact_paths={
            "retry_patch": retry_patch_path,
            "test_artifact": test_artifact,
            "failure_analysis": str(analysis_path),
            "followup_plan": str(plan_path),
        },
        source="autonomous_loop_retry_failure",
    )
    context_artifacts = write_failure_context_artifacts(
        run_dir,
        failure_context,
        json_name=f"37_failure_context_attempt_{attempt_number:03d}.json",
        markdown_name=f"37_failure_context_attempt_{attempt_number:03d}.md",
    )
    artifacts = [str(analysis_path), str(plan_path), str(loop_path), *context_artifacts]
    _write_retry_summary_fields(
        run_dir,
        {
            "autonomous_loop_retry_failure_detected": True,
            "autonomous_loop_retry_failure_attempt": attempt_number,
            "autonomous_loop_retry_failure_reason": reason,
            "autonomous_loop_retry_failure_artifacts": artifacts,
            "autonomous_loop_retry_failure_next_action": next_action,
        },
        output_files={
            f"retry_test_failure_analysis_attempt_{attempt_number:03d}": str(analysis_path),
            f"retry_failure_followup_plan_attempt_{attempt_number:03d}": str(plan_path),
            f"retry_failure_loop_attempt_{attempt_number:03d}": str(loop_path),
            f"retry_failure_context_attempt_{attempt_number:03d}": context_artifacts[0],
        },
    )
    return artifacts


def _prepare_attempt_dir(run_dir: Path, retry_patch: Path, attempt_number: int) -> Path:
    attempt_dir = run_dir / ATTEMPT_WORK_DIR / f"attempt_{attempt_number:03d}"
    patches_dir = attempt_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "08_final_review.md",
        "11_execution_plan.md",
        "14_test_run.md",
        "15_merge_readiness.md",
        "16_human_approval.md",
        "24_experience_context.md",
    ):
        source = run_dir / filename
        if source.exists():
            shutil.copy2(source, attempt_dir / filename)
    summary = _load_summary(run_dir, [])
    summary.setdefault("output_files", {})
    (attempt_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    shutil.copy2(retry_patch, patches_dir / retry_patch.name)
    return attempt_dir


def _write_attempt(
    *,
    run_dir: Path,
    attempt_number: int,
    status: str,
    input_test_status: str,
    self_healing_status: str,
    retry_patch_path: str,
    patch_quality_decision: str,
    patch_approval_decision: str,
    patch_apply_status: str,
    test_result_status: str,
    errors: list[str],
    warnings: list[str],
    failure_reason: str = "",
    failure_artifacts: list[str] | None = None,
    failure_next_action: str = "",
) -> AutonomousLoopAttempt:
    failure_artifacts = failure_artifacts or []
    artifact_path = run_dir / ATTEMPT_FILE_TEMPLATE.format(attempt=attempt_number)
    report = _render_attempt_report(
        status=status,
        input_test_status=input_test_status,
        self_healing_status=self_healing_status,
        retry_patch_path=retry_patch_path,
        patch_quality_decision=patch_quality_decision,
        patch_approval_decision=patch_approval_decision,
        patch_apply_status=patch_apply_status,
        test_result_status=test_result_status,
        errors=errors,
        warnings=warnings,
        failure_reason=failure_reason,
        failure_artifacts=failure_artifacts,
        failure_next_action=failure_next_action,
    )
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    return AutonomousLoopAttempt(
        attempt=attempt_number,
        status=status,
        artifact_path=str(artifact_path),
        input_test_status=input_test_status,
        self_healing_status=self_healing_status,
        retry_patch_path=retry_patch_path,
        patch_quality_decision=patch_quality_decision,
        patch_approval_decision=patch_approval_decision,
        patch_apply_status=patch_apply_status,
        test_result_status=test_result_status,
        validation_errors=errors,
        validation_warnings=warnings,
        failure_reason=failure_reason,
        failure_artifacts=failure_artifacts,
        failure_next_action=failure_next_action,
    )


def _validate_initial_state(run_dir: Path, *, max_attempts: int, timeout_seconds: int) -> list[str]:
    errors: list[str] = []
    if max_attempts <= 0:
        errors.append("max_attempts_invalid")
    if timeout_seconds <= 0:
        errors.append("timeout_seconds_invalid")
    for filename in (SUMMARY_FILE, "14_test_run.md"):
        if not (run_dir / filename).exists():
            errors.append(f"missing_artifact:{filename}")
    policy = load_filesystem_policy()
    if policy.is_path_blocked(run_dir):
        errors.append("run_dir_forbidden_path")
    return _dedupe(errors)


def _render_loop_report(
    *,
    status: str,
    attempts: list[AutonomousLoopAttempt],
    max_attempts: int,
    last_error: str,
    last_retry_patch: str,
    warnings: list[str],
    errors: list[str],
) -> str:
    return "\n".join(
        [
            "AUTONOMOUS LOOP SUMMARY",
            f"- Status: {status}.",
            f"- Attempts completed: {len(attempts)}.",
            f"- Max attempts: {max_attempts}.",
            "- Existing Patch Quality, Patch Approval, Human Approval, Patch Apply, and Test Runner gates were preserved.",
            "",
            "ATTEMPTS",
            *_bullets([f"Attempt {attempt.attempt}: {attempt.status}" for attempt in attempts] or ["None"]),
            "",
            "LAST FAILURE",
            *_bullets([last_error or "None", *[f"Warning: {warning}" for warning in warnings], *[f"Error: {error}" for error in errors]]),
            "",
            "RETRY PATCHES",
            *_bullets([last_retry_patch] if last_retry_patch else ["None"]),
            "",
            "RETRY TEST FAILURE LOOP",
            *_bullets(
                [
                    artifact
                    for attempt in attempts
                    for artifact in attempt.failure_artifacts
                ]
                or ["None"]
            ),
            "",
            "FINAL STATUS",
            status,
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _render_attempt_report(
    *,
    status: str,
    input_test_status: str,
    self_healing_status: str,
    retry_patch_path: str,
    patch_quality_decision: str,
    patch_approval_decision: str,
    patch_apply_status: str,
    test_result_status: str,
    errors: list[str],
    warnings: list[str],
    failure_reason: str,
    failure_artifacts: list[str],
    failure_next_action: str,
) -> str:
    return "\n".join(
        [
            "ATTEMPT SUMMARY",
            f"- Attempt completed with status: {status}.",
            "",
            "INPUT TEST STATUS",
            f"- {input_test_status or 'Unknown'}",
            "",
            "SELF HEALING RESULT",
            f"- {self_healing_status or 'Not run'}",
            f"- Retry patch: {retry_patch_path or 'None'}",
            "",
            "PATCH QUALITY RESULT",
            f"- {patch_quality_decision or 'Not run'}",
            "",
            "PATCH APPROVAL RESULT",
            f"- {patch_approval_decision or 'Not run'}",
            "",
            "PATCH APPLY RESULT",
            f"- {patch_apply_status or 'Not run'}",
            "",
            "TEST RESULT",
            f"- {test_result_status or 'Not run'}",
            "",
            "RETRY TEST FAILURE LOOP",
            f"- Failure reason: {failure_reason or 'None'}",
            f"- Next action: {failure_next_action or 'None'}",
            *_bullets(failure_artifacts),
            "",
            "VALIDATION",
            *_bullets([f"Warning: {warning}" for warning in warnings] + [f"Error: {error}" for error in errors]),
            "",
            "ATTEMPT STATUS",
            status,
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _update_summary(run_dir: Path, result: AutonomousLoopResult) -> None:
    summary = _load_summary(run_dir, [])
    summary.update(autonomous_loop_summary_fields(result))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files["autonomous_loop"] = result.artifact_path
        for attempt in result.attempts:
            output_files[f"autonomous_attempt_{attempt.attempt:03d}"] = attempt.artifact_path
    (run_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _merge_summary_from_attempt(run_dir: Path, attempt_dir: Path, *, prefix: str) -> None:
    run_summary = _load_summary(run_dir, [])
    attempt_summary = _load_summary(attempt_dir, [])
    for key, value in attempt_summary.items():
        if key == "output_files":
            continue
        if key.startswith(("patch_quality_", "patch_approval_", "patch_apply_", "human_approval_")):
            run_summary[f"{prefix}_{key}"] = value
    (run_dir / SUMMARY_FILE).write_text(json.dumps(run_summary, indent=2), encoding="utf-8")


def _write_attempt_gate_summary(attempt_dir: Path, fields: dict[str, Any]) -> None:
    summary = _load_summary(attempt_dir, [])
    summary.update(fields)
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        for key, value in fields.items():
            if key.endswith("_artifact") and value:
                output_files[key.removesuffix("_artifact")] = str(value)
    (attempt_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _write_retry_summary_fields(
    run_dir: Path,
    fields: dict[str, Any],
    *,
    output_files: dict[str, str] | None = None,
) -> None:
    summary = _load_summary(run_dir, [])
    summary.update(fields)
    files = summary.setdefault("output_files", {})
    if isinstance(files, dict) and output_files:
        files.update(output_files)
    (run_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _status(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _last_attempt_value(result: AutonomousLoopResult, field_name: str) -> str:
    if not result.attempts:
        return ""
    return str(getattr(result.attempts[-1], field_name, "") or "")


def _last_failure_attempt(result: AutonomousLoopResult) -> AutonomousLoopAttempt | None:
    for attempt in reversed(result.attempts):
        if attempt.failure_artifacts or attempt.failure_reason:
            return attempt
    return None


def _test_result_text(result: Any, *keys: str) -> str:
    for key in keys:
        value = getattr(result, key, "")
        if value is not None and value != "":
            return str(value)
    return ""


def _test_result_list(result: Any, *keys: str) -> list[str]:
    for key in keys:
        value = getattr(result, key, None)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, set):
            return sorted(str(item) for item in value if str(item).strip())
        return [str(value)]
    return []


def _read_excerpt(path: Path, *, max_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def _fenced(text: str) -> str:
    safe_text = text.replace("```", "'''")
    return f"```text\n{safe_text}\n```"


def _derive_focus_areas(
    *,
    stdout: str,
    stderr: str,
    commands: list[str],
    files_affected: list[str],
) -> list[str]:
    focus: list[str] = []
    combined = f"{stdout}\n{stderr}".lower()
    if "assert" in combined:
        focus.append("Review failing assertions and expected behavior.")
    if "importerror" in combined or "modulenotfounderror" in combined:
        focus.append("Check imports, package boundaries, and dependency availability.")
    if "syntaxerror" in combined:
        focus.append("Fix syntax before deeper behavioral changes.")
    if "timeout" in combined:
        focus.append("Inspect long-running tests and retry backoff behavior.")
    if commands:
        focus.append(f"Re-run command after the next patch: {commands[0]}")
    if files_affected:
        focus.append(f"Prioritize recently patched file: {files_affected[0]}")
    return focus or ["Use test stdout and stderr to generate the smallest safe retry patch."]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items or ["None"]]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
