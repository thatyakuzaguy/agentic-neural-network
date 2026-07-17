"""ANN v7.3 Consensus-Driven Action Planner.

The planner turns a consensus recommendation into a deterministic operational
plan for humans and future desktop subsystems. It does not execute commands,
apply patches, mutate approvals, or change tokens.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
MARKDOWN_ARTIFACT = "39_action_plan.md"
JSON_ARTIFACT = "39_action_plan.json"
CONSENSUS_ARTIFACT = "38_consensus_decision.json"
PARALLEL_REVIEW_ARTIFACT = "37_parallel_review.json"
SUMMARY_FILE = "summary.json"

STATUS_VALID = "VALID"
STATUS_INVALID = "INVALID"

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
BLOCKED_PARTS = {".git", "models", "training", "memory", "knowledge", "unsloth_compiled_cache"}


@dataclass(frozen=True)
class ActionPlanResult:
    """Structured result for the Consensus-Driven Action Planner."""

    status: str
    source_consensus_decision: str
    recommended_next_action: str
    executable: bool
    requires_human: bool
    requires_terminal: bool
    requires_approval: bool
    requires_apply: bool
    blocked: bool
    blocking_reasons: list[str]
    planned_steps: list[dict[str, Any]]
    allowed_actions: list[str]
    blocked_actions: list[str]
    prerequisites: list[str]
    risks: list[str]
    expected_artifacts: list[str]
    responsible_subsystems: list[str]
    user_message: str
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]
    skill_evidence_status: str = "SKIPPED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_action_plan(
    run_dir: str | Path,
    *,
    runs_root: str | Path | None = None,
) -> ActionPlanResult:
    """Create a read-only action plan from consensus artifacts."""

    validation_errors, validation_warnings, resolved_run_dir = _validate_run_dir(
        run_dir,
        runs_root=Path(runs_root).resolve() if runs_root is not None else DEFAULT_RUNS_ROOT,
        custom_runs_root=runs_root is not None,
    )
    if validation_errors or resolved_run_dir is None:
        return ActionPlanResult(
            status=STATUS_INVALID,
            source_consensus_decision="BLOCKED",
            recommended_next_action="manual_review",
            executable=False,
            requires_human=True,
            requires_terminal=False,
            requires_approval=False,
            requires_apply=False,
            blocked=True,
            blocking_reasons=validation_errors,
            planned_steps=[],
            allowed_actions=["inspect_run_directory_configuration"],
            blocked_actions=["execute_terminal", "apply_patch", "mutate_approval", "mutate_tokens"],
            prerequisites=["valid_run_dir_inside_outputs_runs"],
            risks=["Action planning cannot continue with an invalid run directory."],
            expected_artifacts=[],
            responsible_subsystems=["Action Planner"],
            user_message="Action planning is blocked because the run directory is invalid.",
            artifacts=[],
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
        )

    summary, summary_errors = _read_json(resolved_run_dir / SUMMARY_FILE, missing_ok=True)
    consensus, consensus_errors = _read_json(resolved_run_dir / CONSENSUS_ARTIFACT, missing_ok=False)
    parallel_review, parallel_warnings = _read_json(resolved_run_dir / PARALLEL_REVIEW_ARTIFACT, missing_ok=True)
    skill_evidence, skill_evidence_warnings = _read_json(resolved_run_dir / "70_skill_evidence_bundle.json", missing_ok=True)
    validation_errors = _dedupe(summary_errors + consensus_errors)
    validation_warnings = _dedupe(validation_warnings + parallel_warnings + skill_evidence_warnings)

    plan = _build_plan(
        summary=summary,
        consensus=consensus,
        parallel_review=parallel_review,
        validation_errors=validation_errors,
        validation_warnings=validation_warnings,
    )
    plan = _attach_skill_evidence(plan, skill_evidence, consensus)
    artifacts = _write_artifacts(resolved_run_dir, plan)
    result = ActionPlanResult(**{**plan.to_dict(), "artifacts": artifacts})
    _write_json_artifact(resolved_run_dir / JSON_ARTIFACT, result)
    return result


def _build_plan(
    *,
    summary: dict[str, Any],
    consensus: dict[str, Any],
    parallel_review: dict[str, Any],
    validation_errors: list[str],
    validation_warnings: list[str],
) -> ActionPlanResult:
    if validation_errors:
        return _manual_review_plan(
            source_decision=_consensus_decision(consensus) or "BLOCKED",
            action="manual_review",
            blocking_reasons=validation_errors,
            warnings=validation_warnings,
            user_message="Action planning is blocked until consensus artifacts are available and valid.",
        )

    source_decision = _consensus_decision(consensus)
    action = _normalize_action(consensus.get("recommended_next_action"))
    if source_decision == "BLOCKED" and action != "resolve_parallel_review_blockers":
        return _manual_review_plan(
            source_decision=source_decision,
            action=action,
            blocking_reasons=["Consensus decision is BLOCKED."],
            warnings=validation_warnings,
            user_message="Consensus is blocked. Resolve blockers before any execution or apply action.",
        )
    if action == "resolve_parallel_review_blockers":
        return _resolve_parallel_blockers_plan(source_decision, action, consensus, parallel_review, validation_warnings)
    if action in {"run_tests", "run_guarded_tests"}:
        return _run_tests_plan(source_decision, action, validation_warnings)
    if action in {"apply_patch", "request_human_approval_then_patch_apply"}:
        return _apply_patch_plan(source_decision, action, summary, consensus, validation_warnings)
    if action in {"retry", "run_guarded_retry_loop", "revise_patch_or_enter_retry_loop"}:
        return _retry_plan(source_decision, action, consensus, validation_warnings)
    if action == "challenge_or_repair_test_contract_before_code_fix":
        return _test_contract_challenge_plan(source_decision, action, consensus, validation_warnings)
    if action == "run_architecture_refactor_review":
        return _architecture_refactor_review_plan(source_decision, action, consensus, validation_warnings)
    if action in {
        "wait_for_new_plan_or_patch",
        "wait_for_functional_evidence_or_user_preference",
        "no_action",
    }:
        return _no_action_plan(source_decision, action, validation_warnings)
    return _manual_review_plan(
        source_decision=source_decision or "UNKNOWN",
        action=action or "manual_review",
        blocking_reasons=[f"Unsupported recommended_next_action: {action or 'MISSING'}."],
        warnings=validation_warnings,
        user_message="The recommended next action is not recognized. Manual review is required.",
    )


def _resolve_parallel_blockers_plan(
    source_decision: str,
    action: str,
    consensus: dict[str, Any],
    parallel_review: dict[str, Any],
    warnings: list[str],
) -> ActionPlanResult:
    blockers = _as_list(consensus.get("blocking_findings")) or ["Parallel Review reported blocking findings."]
    blocked_reviewers = _blocked_reviewers(parallel_review)
    steps = [
        _step(1, "Open 37_parallel_review.md and 37_parallel_review.json.", "Parallel Review Agent", "read_only"),
        _step(2, f"Identify blocked reviewers: {', '.join(blocked_reviewers) or 'see blocking_findings'}.", "Meta Review Agent", "read_only"),
        _step(3, "Inspect referenced blocking artifacts and patch context.", "Repository Intelligence", "read_only"),
        _step(4, "Prepare a revision or rerun recommendation without applying patches.", "Action Planner", "planning_only"),
        _step(5, "Rerun Parallel Review and Consensus after blockers are resolved.", "Parallel Review Agent", "future_action"),
    ]
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=False,
        requires_human=True,
        requires_terminal=False,
        requires_approval=False,
        requires_apply=False,
        blocked=True,
        blocking_reasons=blockers,
        planned_steps=steps,
        allowed_actions=["inspect_parallel_review", "inspect_blocking_artifacts", "propose_revision"],
        blocked_actions=["apply_patch", "approve_patch", "execute_terminal", "deploy"],
        prerequisites=["37_parallel_review.md", "37_parallel_review.json", "human_engineer_review"],
        risks=["Applying while parallel review is blocked can preserve unsafe or inconsistent changes."],
        expected_artifacts=["updated_37_parallel_review.md", "updated_38_consensus_decision.md"],
        responsible_subsystems=["Parallel Review Agent", "Repository Intelligence", "Meta Review Agent", "Action Planner"],
        user_message="Parallel Review is blocking the run. Inspect reviewer blockers before approving or applying anything.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _run_tests_plan(source_decision: str, action: str, warnings: list[str]) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=True,
        requires_human=True,
        requires_terminal=True,
        requires_approval=False,
        requires_apply=False,
        blocked=False,
        blocking_reasons=[],
        planned_steps=[
            _step(1, "Request user confirmation for Terminal Agent execution.", "Desktop App", "approval_prompt"),
            _step(2, "Run allowlisted pytest command through Terminal Agent with confirm_execute.", "Terminal Agent", "terminal_plan"),
            _step(3, "Capture stdout, stderr, exit code, and command metadata.", "Terminal Agent", "artifact_capture"),
            _step(4, "Feed test result back into Consensus Engine.", "Consensus Engine", "future_action"),
        ],
        allowed_actions=["terminal_agent_allowlisted_pytest_after_confirmation", "capture_test_output"],
        blocked_actions=["direct_host_shell", "apply_patch", "mutate_approval", "deploy"],
        prerequisites=["confirm_execute", "allowlisted_test_command", "workspace_run_context"],
        risks=["Tests can fail or time out and must be captured as artifacts for follow-up."],
        expected_artifacts=["terminal_test_run.md", "updated_38_consensus_decision.md", "updated_39_action_plan.md"],
        responsible_subsystems=["Terminal Agent", "Test Runner Agent", "Consensus Engine", "Desktop App"],
        user_message="Tests can be run through the guarded Terminal Agent after explicit confirmation.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _apply_patch_plan(
    source_decision: str,
    action: str,
    summary: dict[str, Any],
    consensus: dict[str, Any],
    warnings: list[str],
) -> ActionPlanResult:
    missing = _apply_prerequisite_gaps(summary, consensus)
    blocked = bool(missing)
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=not blocked,
        requires_human=True,
        requires_terminal=False,
        requires_approval=True,
        requires_apply=True,
        blocked=blocked,
        blocking_reasons=missing,
        planned_steps=[
            _step(1, "Confirm Patch Quality is IMPLEMENTATION_READY.", "Patch Quality Agent", "gate_check"),
            _step(2, "Confirm Parallel Review Gate is APPROVED.", "Parallel Review Gate", "gate_check"),
            _step(3, "Collect valid Human Approval and approval token through UI/Desktop.", "Human Approval Agent", "approval_required"),
            _step(4, "Use Patch Apply Agent; do not bypass its safety gates.", "Patch Apply Agent", "future_action"),
            _step(5, "Run tests and feed results back into Consensus.", "Test Runner Agent", "future_action"),
        ],
        allowed_actions=["request_human_approval", "run_patch_apply_gate_after_approval", "run_tests_after_apply"],
        blocked_actions=["bypass_patch_apply", "apply_without_token", "direct_file_write", "execute_terminal_without_confirmation"],
        prerequisites=[
            "patch_quality_implementation_ready",
            "parallel_review_gate_approved",
            "patch_approval_approved",
            "valid_human_approval",
            "approval_token",
        ],
        risks=["Applying patches can modify project files and must remain behind approval and Patch Apply gates."],
        expected_artifacts=["16_human_approval.md", "13_patch_apply.md", "14_test_run.md", "38_consensus_decision.md"],
        responsible_subsystems=["Human Approval Agent", "Patch Apply Agent", "Test Runner Agent", "Consensus Engine"],
        user_message=(
            "Patch apply is available only after all approval and safety prerequisites are satisfied."
            if blocked
            else "Patch apply can proceed through existing approval and Patch Apply gates."
        ),
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _retry_plan(source_decision: str, action: str, consensus: dict[str, Any], warnings: list[str]) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=True,
        requires_human=True,
        requires_terminal=False,
        requires_approval=True,
        requires_apply=True,
        blocked=False,
        blocking_reasons=[],
        planned_steps=[
            _step(1, "Start Autonomous Loop only with --run-tests enabled.", "Autonomous Loop", "guarded_retry"),
            _step(2, "Generate or reuse retry patch through Self Healing.", "Self Healing Agent", "retry_patch"),
            _step(3, "Run Retry Patch Quality and Retry Patch Approval.", "Patch Quality and Approval", "gate_check"),
            _step(4, "Require Retry Human Approval before retry Patch Apply.", "Human Approval Agent", "approval_required"),
            _step(5, "Apply retry patch through Patch Apply and run Retry Test Runner.", "Patch Apply/Test Runner", "future_action"),
            _step(6, "Feed retry result back into Consensus.", "Consensus Engine", "future_action"),
        ],
        allowed_actions=["run_autonomous_loop_with_run_tests", "retry_patch_quality", "retry_patch_approval"],
        blocked_actions=["retry_apply_without_approval", "run_tests_without_flag", "bypass_max_attempts"],
        prerequisites=["--run-tests", "max_attempts_policy", "retry_patch_approval_flow", "valid_approval_token_for_apply"],
        risks=_as_list(consensus.get("warnings")) or ["Retry loops can consume attempts and must stop at max_attempts."],
        expected_artifacts=[
            "29_retry_patch_quality.md",
            "30_retry_patch_approval.md",
            "31_retry_human_approval.md",
            "32_retry_patch_apply.md",
            "33_retry_test_run.md",
            "38_consensus_decision.md",
        ],
        responsible_subsystems=["Autonomous Loop", "Self Healing Agent", "Patch Quality Agent", "Patch Apply Agent", "Test Runner Agent"],
        user_message="A guarded retry is recommended; preserve all v4.1/v4.2 gates and max_attempts.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _test_contract_challenge_plan(
    source_decision: str,
    action: str,
    consensus: dict[str, Any],
    warnings: list[str],
) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=False,
        requires_human=True,
        requires_terminal=False,
        requires_approval=False,
        requires_apply=False,
        blocked=True,
        blocking_reasons=_as_list(consensus.get("blocking_findings"))
        or ["Test Validity Gate requires contract validation before code repair."],
        planned_steps=[
            _step(1, "Open 06a_failure_context.json or the latest 37_failure_context_attempt_*.json.", "Failure Context Compiler", "read_only"),
            _step(2, "Compare failing assertion evidence against Product, Architecture, and Test plan artifacts.", "Reviewer/Test Engineer", "contract_check"),
            _step(3, "If the assertion contradicts the contract, regenerate or patch the test/fixture through guarded patch flow.", "Test Engineer", "future_action"),
            _step(4, "If the contract is ambiguous, ask for clarification or escalate before changing code under test.", "Human Approval Agent", "human_review"),
            _step(5, "Rerun tests and Consensus only after test validity is resolved.", "Test Runner/Consensus", "future_action"),
        ],
        allowed_actions=["inspect_failure_context", "inspect_test_contract", "propose_test_or_fixture_fix"],
        blocked_actions=["rewrite_code_under_test", "apply_patch_without_approval", "consume_retry_attempt_for_style_or_bad_test"],
        prerequisites=["test_validity_gate_evidence", "product_or_acceptance_contract", "human_review_for_ambiguous_contracts"],
        risks=[
            "A hallucinated or stale test can force a regression if code is changed only to satisfy the failing assertion."
        ],
        expected_artifacts=["updated_test_plan_or_fixture_patch", "updated_38_consensus_decision.md", "updated_39_action_plan.md"],
        responsible_subsystems=["Test Validity Gate", "Failure Context Compiler", "Reviewer Agent", "Test Engineer", "Consensus Engine"],
        user_message="Tests failed, but the test expectation or fixture is suspect. Validate the contract before changing code.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _architecture_refactor_review_plan(
    source_decision: str,
    action: str,
    consensus: dict[str, Any],
    warnings: list[str],
) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=False,
        requires_human=True,
        requires_terminal=False,
        requires_approval=False,
        requires_apply=False,
        blocked=True,
        blocking_reasons=_as_list(consensus.get("blocking_findings"))
        or ["Architecture Entropy Gate requires refactor review before more localized fixes."],
        planned_steps=[
            _step(1, "Inspect architecture_entropy signals inside 38_consensus_decision.json.", "Architecture Entropy Gate", "read_only"),
            _step(2, "Identify repeated hotspots, control-flow accretion, and complex functions.", "Repository Intelligence", "read_only"),
            _step(3, "Ask Architect Agent for a design-level refactor plan before another localized Fixer attempt.", "Architect Agent", "planning_only"),
            _step(4, "Create a small guarded refactor patch that reduces complexity before adding edge-case fixes.", "Code/Execution Agent", "future_action"),
            _step(5, "Run Patch Quality, approvals, Patch Apply, and tests through existing gates.", "Patch Quality/Test Runner", "future_action"),
        ],
        allowed_actions=["inspect_entropy_signals", "plan_refactor", "propose_refactor_patch"],
        blocked_actions=["localized_retry_patch", "rewrite_hotspot_without_architecture_plan", "apply_patch_without_approval"],
        prerequisites=["architecture_entropy_evidence", "architect_refactor_plan", "human_review_for_design_change"],
        risks=[
            "Continuing localized patches on entropy hotspots can convert a healthy architecture into unmaintainable code."
        ],
        expected_artifacts=["architect_refactor_plan.md", "refactor_patch.diff", "updated_38_consensus_decision.md"],
        responsible_subsystems=["Architecture Entropy Gate", "Architect Agent", "Repository Intelligence", "Consensus Engine"],
        user_message="Architecture entropy is rising. Run a design-level refactor review before adding more local fixes.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _no_action_plan(source_decision: str, action: str, warnings: list[str]) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=False,
        requires_human=False,
        requires_terminal=False,
        requires_approval=False,
        requires_apply=False,
        blocked=False,
        blocking_reasons=[],
        planned_steps=[_step(1, "Wait for a new patch, run, or user request.", "Project Manager", "idle")],
        allowed_actions=["inspect_artifacts", "start_new_request"],
        blocked_actions=["apply_patch", "execute_terminal", "deploy"],
        prerequisites=["new_user_request_or_patch"],
        risks=["No operational work is available until a new signal appears."],
        expected_artifacts=[],
        responsible_subsystems=["Project Manager", "Desktop App"],
        user_message="No action is currently required.",
        artifacts=[],
        validation_errors=[],
        validation_warnings=warnings,
    )


def _manual_review_plan(
    *,
    source_decision: str,
    action: str,
    blocking_reasons: list[str],
    warnings: list[str],
    user_message: str,
) -> ActionPlanResult:
    return ActionPlanResult(
        status=STATUS_VALID if not blocking_reasons else STATUS_INVALID,
        source_consensus_decision=source_decision,
        recommended_next_action=action,
        executable=False,
        requires_human=True,
        requires_terminal=False,
        requires_approval=False,
        requires_apply=False,
        blocked=True,
        blocking_reasons=_dedupe(blocking_reasons),
        planned_steps=[
            _step(1, "Inspect consensus and summary artifacts manually.", "Human Engineer", "read_only"),
            _step(2, "Decide whether to rerun Consensus, Parallel Review, or upstream agents.", "Human Engineer", "manual_review"),
        ],
        allowed_actions=["inspect_artifacts", "rerun_read_only_review"],
        blocked_actions=["apply_patch", "execute_terminal", "mutate_approval", "mutate_tokens", "deploy"],
        prerequisites=["human_engineer_review"],
        risks=["Unsupported or missing recommendations must not be executed automatically."],
        expected_artifacts=["updated_38_consensus_decision.md", "updated_39_action_plan.md"],
        responsible_subsystems=["Human Engineer", "Action Planner", "Consensus Engine"],
        user_message=user_message,
        artifacts=[],
        validation_errors=_dedupe(blocking_reasons),
        validation_warnings=warnings,
    )


def _attach_skill_evidence(
    plan: ActionPlanResult,
    skill_evidence: dict[str, Any],
    consensus: dict[str, Any],
) -> ActionPlanResult:
    status = str(skill_evidence.get("status") or consensus.get("skill_evidence_status") or "SKIPPED")
    data = plan.to_dict()
    data["skill_evidence_status"] = status
    if status.upper() != "VALID":
        return ActionPlanResult(**data)
    if plan.recommended_next_action in {
        "run_tests",
        "run_guarded_tests",
        "apply_patch",
        "request_human_approval_then_patch_apply",
        "retry",
        "run_guarded_retry_loop",
        "revise_patch_or_enter_retry_loop",
    }:
        data["recommended_next_action"] = f"{plan.recommended_next_action}_and_consult_skill_evidence"
        data["planned_steps"] = [
            *plan.planned_steps,
            _step(
                len(plan.planned_steps) + 1,
                "Consult 70_skill_evidence_bundle.json before refining architecture, tests, or patch strategy.",
                "Skill Evidence Agent",
                "read_only_context",
            ),
        ]
        data["responsible_subsystems"] = _dedupe([*plan.responsible_subsystems, "Skill Evidence Agent"])
        data["risks"] = _dedupe([*plan.risks, "Skill evidence is advisory and must not be copied as external source code."])
    return ActionPlanResult(**data)


def _apply_prerequisite_gaps(summary: dict[str, Any], consensus: dict[str, Any]) -> list[str]:
    signals = consensus.get("signals_used") if isinstance(consensus.get("signals_used"), dict) else {}
    gaps: list[str] = []
    quality = str(signals.get("patch_quality_decision") or summary.get("patch_quality_decision") or "").upper()
    if quality not in {"IMPLEMENTATION_READY", "APPROVED", "PASS", "PASSED"}:
        gaps.append("patch_quality_not_ready")
    parallel = str(signals.get("parallel_review_decision") or "").upper()
    if parallel != "APPROVED":
        gaps.append("parallel_review_not_approved")
    patch_approval = str(signals.get("patch_approval_decision") or summary.get("patch_approval_decision") or "")
    if patch_approval != "Approved":
        gaps.append("patch_approval_not_approved")
    human_decision = str(summary.get("human_approval_decision") or "")
    human_valid = summary.get("human_approval_validation_passed") is True
    if human_decision and (human_decision != "Approved" or not human_valid):
        gaps.append("human_approval_not_valid")
    return _dedupe(gaps)


def _validate_run_dir(
    run_dir: str | Path,
    *,
    runs_root: Path,
    custom_runs_root: bool,
) -> tuple[list[str], list[str], Path | None]:
    errors: list[str] = []
    warnings: list[str] = []
    text = str(run_dir).strip().strip('"').strip("'")
    if not text:
        return ["run_dir_missing"], warnings, None
    if ".." in text.replace("\\", "/").split("/"):
        return ["run_dir_path_traversal_blocked"], warnings, None
    candidate = Path(text)
    if not candidate.is_absolute():
        normalized = text.replace("\\", "/")
        if normalized.startswith("outputs/runs/"):
            candidate = REPO_ROOT / candidate
        else:
            candidate = runs_root / candidate
    resolved = candidate.resolve()
    root = runs_root.resolve()
    if not custom_runs_root and re.match(r"(?i)^(?:c:[\\/]|/mnt/c\b)", text):
        errors.append("run_dir_c_drive_blocked")
    if not _is_relative_to(resolved, root):
        errors.append("run_dir_must_be_inside_outputs_runs")
    if any(part.lower() in BLOCKED_PARTS for part in resolved.parts):
        errors.append("run_dir_protected_path_blocked")
    if not resolved.exists() or not resolved.is_dir():
        errors.append("run_dir_missing")
    if resolved.exists() and not _valid_run_id(resolved.name):
        errors.append("run_dir_invalid_run_id")
    return _dedupe(errors), _dedupe(warnings), resolved if not errors else None


def _read_json(path: Path, *, missing_ok: bool) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [] if missing_ok else [f"missing_artifact:{path.name}"]
    if not path.is_file():
        return {}, [f"artifact_not_file:{path.name}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, [f"invalid_json:{path.name}"]
    if not isinstance(payload, dict):
        return {}, [f"json_not_object:{path.name}"]
    return payload, []


def _write_artifacts(run_dir: Path, result: ActionPlanResult) -> list[str]:
    markdown_path = run_dir / MARKDOWN_ARTIFACT
    json_path = run_dir / JSON_ARTIFACT
    artifacts = [str(markdown_path), str(json_path)]
    markdown_path.write_text(_render_markdown(result, artifacts=artifacts), encoding="utf-8")
    return artifacts


def _write_json_artifact(path: Path, result: ActionPlanResult) -> None:
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def _render_markdown(result: ActionPlanResult, *, artifacts: list[str]) -> str:
    return "\n".join(
        [
            "# ANN Action Plan",
            "",
            "## Summary",
            f"- Status: {result.status}",
            f"- Source consensus decision: {result.source_consensus_decision}",
            f"- Recommended next action: {result.recommended_next_action}",
            f"- Executable: {result.executable}",
            f"- Blocked: {result.blocked}",
            f"- Skill evidence status: {result.skill_evidence_status}",
            f"- Generated at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            "",
            "## User Message",
            result.user_message,
            "",
            "## Planned Steps",
            *_bullets([f"{step['order']}. {step['description']} ({step['subsystem']})" for step in result.planned_steps] or ["None"]),
            "",
            "## Allowed Actions",
            *_bullets(result.allowed_actions or ["None"]),
            "",
            "## Blocked Actions",
            *_bullets(result.blocked_actions or ["None"]),
            "",
            "## Prerequisites",
            *_bullets(result.prerequisites or ["None"]),
            "",
            "## Blocking Reasons",
            *_bullets(result.blocking_reasons or ["None"]),
            "",
            "## Risks",
            *_bullets(result.risks or ["None"]),
            "",
            "## Responsible Subsystems",
            *_bullets(result.responsible_subsystems or ["None"]),
            "",
            "## Expected Artifacts",
            *_bullets(result.expected_artifacts or ["None"]),
            "",
            "## Artifacts Created",
            *_bullets(artifacts),
            "",
        ]
    ).rstrip() + "\n"


def _step(order: int, description: str, subsystem: str, action_type: str) -> dict[str, Any]:
    return {
        "order": order,
        "description": description,
        "subsystem": subsystem,
        "action_type": action_type,
    }


def _blocked_reviewers(parallel_review: dict[str, Any]) -> list[str]:
    results = parallel_review.get("agent_results")
    if not isinstance(results, dict):
        return []
    blocked: list[str] = []
    for name, payload in results.items():
        if isinstance(payload, dict) and str(payload.get("decision") or "").upper() == "BLOCKED":
            blocked.append(str(name))
    return sorted(blocked)


def _consensus_decision(consensus: dict[str, Any]) -> str:
    return str(consensus.get("consensus_decision") or "UNKNOWN").strip() or "UNKNOWN"


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "resolve_blockers": "resolve_parallel_review_blockers",
        "run_tests_for_run": "run_tests",
        "request_human_approval_then_patch_apply": "request_human_approval_then_patch_apply",
        "run_guarded_retry": "run_guarded_retry_loop",
    }
    return aliases.get(text, text)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id)) and run_id not in {".", ".."}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


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
