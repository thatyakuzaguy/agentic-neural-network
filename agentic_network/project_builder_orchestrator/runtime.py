"""End-to-end orchestrator for generated ANN projects.

The orchestrator composes v8.2 through v8.7. It remains local-only, deterministic,
and approval-gated for scaffold/apply/test phases.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import normalize_workspace_path
from agentic_network.model_routing.models import PipelineRoutingPlan
from agentic_network.model_routing.runtime import build_pipeline_routing_plan
from agentic_network.project_creation_agent.runtime import plan_new_project
from agentic_network.project_implementation_agent.runtime import start_project_implementation
from agentic_network.project_patch_apply_agent.runtime import apply_project_patch
from agentic_network.project_scaffold_agent.runtime import apply_project_scaffold
from agentic_network.project_self_healing_agent.runtime import run_project_self_healing
from agentic_network.project_test_generation_agent.runtime import generate_project_tests
from agentic_network.project_test_runner_agent.runtime import run_project_verification
from agentic_network.skill_evidence_agent.runtime import SkillEvidenceResult, build_skill_evidence_bundle


@dataclass(frozen=True)
class EndToEndProjectResult:
    """Result of running the end-to-end project builder."""

    status: str
    project_root: str
    creation_status: str
    scaffold_status: str
    implementation_status: str
    patch_status: str
    verification_status: str
    self_healing_status: str
    consensus: dict[str, Any]
    next_action: str
    recommended_next_action: str
    completion_quality: str
    verification_evidence: dict[str, Any]
    skill_evidence_used: bool
    skill_evidence_status: str
    skill_evidence_summary: str
    skill_evidence_recommendations: list[str]
    skill_evidence_artifacts: list[str]
    execution_mode: str
    model_routing_status: str
    model_routing_decisions: list[dict[str, Any]]
    model_routing_artifacts: list[str]
    artifacts: list[str]
    validation_errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_end_to_end_project(
    idea: str,
    target_root: str | Path,
    project_name: str | None = None,
    approval_token: str | None = None,
    max_features: int = 5,
    max_retries: int = 3,
    confirm_create: bool = False,
    confirm_apply: bool = False,
    confirm_tests: bool = False,
    generate_tests_if_missing: bool = False,
    use_skill_evidence: bool = False,
    skill_evidence_roots: list[str | Path] | None = None,
    execution_mode: str = "FAST",
) -> EndToEndProjectResult:
    """Run ANN project creation through verification/self-healing."""

    artifacts: list[str] = []
    errors: list[str] = []
    creation = plan_new_project(idea, target_root, project_name)
    artifacts.extend(creation.artifacts)
    plan_dir = Path(creation.artifacts[0]).parent if creation.artifacts else None
    routing_plan = build_pipeline_routing_plan(
        ["product", "architect", "code", "test", "security", "reviewer"],
        mode=execution_mode,
        run_dir=plan_dir,
    )
    artifacts.extend(routing_plan.artifacts)
    skill_evidence = _build_optional_skill_evidence(
        enabled=use_skill_evidence,
        roots=skill_evidence_roots,
        run_dir=plan_dir,
    )
    artifacts.extend(skill_evidence.artifacts)
    project_root = str(normalize_workspace_path(target_root) / creation.project_slug)
    if creation.status != "VALID" or plan_dir is None:
        errors.extend(creation.validation_errors)
        return _finish(
            status="BLOCKED",
            project_root=project_root,
            creation_status=creation.status,
            scaffold_status="SKIPPED",
            implementation_status="SKIPPED",
            patch_status="SKIPPED",
            verification_status="SKIPPED",
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=errors,
            next_action="fix_project_creation_inputs",
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )

    scaffold = apply_project_scaffold(
        plan_dir,
        approval_token=approval_token,
        confirm_create=confirm_create,
        dry_run=not confirm_create,
    )
    artifacts.extend([scaffold.preview_artifact, scaffold.audit_artifact])
    if scaffold.status not in {"APPLIED", "DRY_RUN"}:
        errors.extend(scaffold.validation_errors)
        return _finish(
            status="BLOCKED",
            project_root=scaffold.project_path,
            creation_status=creation.status,
            scaffold_status=scaffold.status,
            implementation_status="SKIPPED",
            patch_status="SKIPPED",
            verification_status="SKIPPED",
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=errors,
            next_action="review_scaffold_blockers",
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )
    if scaffold.status == "DRY_RUN":
        return _finish(
            status="BLOCKED",
            project_root=scaffold.project_path,
            creation_status=creation.status,
            scaffold_status=scaffold.status,
            implementation_status="SKIPPED",
            patch_status="SKIPPED",
            verification_status="SKIPPED",
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=["confirm_create is required to continue end-to-end build."],
            next_action="confirm_project_scaffold",
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )

    implementation = start_project_implementation(
        scaffold.project_path,
        idea,
        max_features=max_features,
        skill_evidence_used=skill_evidence.status == "VALID",
        skill_evidence_recommendations=skill_evidence.recommendations,
    )
    artifacts.extend(implementation.artifacts)
    if implementation.status != "PLANNED":
        errors.extend(implementation.validation_errors)
        return _finish(
            status="FAILED",
            project_root=scaffold.project_path,
            creation_status=creation.status,
            scaffold_status=scaffold.status,
            implementation_status=implementation.status,
            patch_status="SKIPPED",
            verification_status="SKIPPED",
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=errors,
            next_action="review_implementation_errors",
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )

    patch_status = "SKIPPED"
    run_dir = _latest_run_dir(Path(scaffold.project_path))
    for patch in implementation.patches_generated:
        patch_apply = apply_project_patch(
            scaffold.project_path,
            patch,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
            dry_run=not confirm_apply,
        )
        patch_status = patch_apply.status
        if patch_apply.retry_patch_generated:
            artifacts.append(patch_apply.retry_patch_generated)
        artifacts.extend(patch_apply.backups_created)
        if patch_apply.status != "APPLIED":
            errors.extend(patch_apply.validation_errors)
            return _finish(
                status="BLOCKED",
                project_root=scaffold.project_path,
                creation_status=creation.status,
                scaffold_status=scaffold.status,
                implementation_status=implementation.status,
                patch_status=patch_apply.status,
                verification_status="SKIPPED",
                self_healing_status="SKIPPED",
                artifacts=artifacts,
                errors=errors or ["confirm_apply is required to apply generated patches."],
                next_action="review_or_approve_project_patches",
                skill_evidence=skill_evidence,
                routing_plan=routing_plan,
            )

    verification = run_project_verification(
        scaffold.project_path,
        run_dir=run_dir,
        confirm_run=confirm_tests,
    )
    artifacts.extend(verification.artifacts)
    if (
        generate_tests_if_missing
        and verification.status == "SKIPPED"
        and not getattr(verification, "commands_selected", [])
    ):
        generated = generate_project_tests(
            scaffold.project_path,
            run_dir=run_dir,
            max_tests=5,
            skill_evidence_used=skill_evidence.status == "VALID",
        )
        artifacts.extend(generated.artifacts)
        if generated.status != "VALID":
            classification = _classification(
                "NEEDS_TESTS",
                "REVIEW_REQUIRED",
                generated.next_action,
                _verification_evidence(verification),
            )
            return _finish(
                status=classification["status"],
                project_root=scaffold.project_path,
                creation_status=creation.status,
                scaffold_status=scaffold.status,
                implementation_status=implementation.status,
                patch_status=patch_status,
                verification_status=verification.status,
                self_healing_status="SKIPPED",
                artifacts=artifacts,
                errors=generated.validation_errors,
                next_action=classification["recommended_next_action"],
                verification_evidence=classification["verification_evidence"],
                completion_quality=classification["completion_quality"],
                skill_evidence=skill_evidence,
                routing_plan=routing_plan,
            )
        for patch in generated.test_patch_files:
            test_patch_apply = apply_project_patch(
                scaffold.project_path,
                patch,
                approval_token=approval_token,
                confirm_apply=confirm_apply,
                dry_run=not confirm_apply,
            )
            patch_status = test_patch_apply.status
            artifacts.extend(test_patch_apply.backups_created)
            if test_patch_apply.retry_patch_generated:
                artifacts.append(test_patch_apply.retry_patch_generated)
            if test_patch_apply.status != "APPLIED":
                errors.extend(test_patch_apply.validation_errors)
                return _finish(
                    status="BLOCKED",
                    project_root=scaffold.project_path,
                    creation_status=creation.status,
                    scaffold_status=scaffold.status,
                    implementation_status=implementation.status,
                    patch_status=test_patch_apply.status,
                    verification_status=verification.status,
                    self_healing_status="SKIPPED",
                    artifacts=artifacts,
                    errors=errors or ["confirm_apply is required to apply generated test patches."],
                    next_action="review_or_approve_generated_test_patches",
                    verification_evidence=_verification_evidence(verification),
                    completion_quality="REVIEW_REQUIRED",
                    skill_evidence=skill_evidence,
                    routing_plan=routing_plan,
                )
        if not confirm_tests:
            return _finish(
                status="BLOCKED",
                project_root=scaffold.project_path,
                creation_status=creation.status,
                scaffold_status=scaffold.status,
                implementation_status=implementation.status,
                patch_status=patch_status,
                verification_status=verification.status,
                self_healing_status="SKIPPED",
                artifacts=artifacts,
                errors=["confirm_tests is required to run generated tests."],
                next_action="confirm_project_tests",
                verification_evidence=_verification_evidence(verification),
                completion_quality="REVIEW_REQUIRED",
                skill_evidence=skill_evidence,
                routing_plan=routing_plan,
            )
        verification = run_project_verification(
            scaffold.project_path,
            run_dir=run_dir,
            confirm_run=True,
        )
        artifacts.extend(verification.artifacts)
    if not confirm_tests:
        return _finish(
            status="BLOCKED",
            project_root=scaffold.project_path,
            creation_status=creation.status,
            scaffold_status=scaffold.status,
            implementation_status=implementation.status,
            patch_status=patch_status,
            verification_status=verification.status,
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=["confirm_tests is required to complete end-to-end build."],
            next_action="confirm_project_tests",
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )
    if verification.status in {"PASSED", "SKIPPED"}:
        classification = _classify_verification(verification, patch_status)
        return _finish(
            status=classification["status"],
            project_root=scaffold.project_path,
            creation_status=creation.status,
            scaffold_status=scaffold.status,
            implementation_status=implementation.status,
            patch_status=patch_status,
            verification_status=verification.status,
            self_healing_status="SKIPPED",
            artifacts=artifacts,
            errors=[],
            next_action=classification["recommended_next_action"],
            verification_evidence=classification["verification_evidence"],
            completion_quality=classification["completion_quality"],
            skill_evidence=skill_evidence,
            routing_plan=routing_plan,
        )

    self_healing = run_project_self_healing(
        scaffold.project_path,
        run_dir=run_dir,
        max_attempts=max_retries,
        approval_token=approval_token,
        confirm_retry=confirm_apply,
    )
    artifacts.extend(self_healing.artifacts)
    healed = _classify_self_healing(verification, self_healing)
    return _finish(
        status=healed["status"],
        project_root=scaffold.project_path,
        creation_status=creation.status,
        scaffold_status=scaffold.status,
        implementation_status=implementation.status,
        patch_status=patch_status,
        verification_status=verification.status,
        self_healing_status=self_healing.status,
        artifacts=artifacts,
        errors=self_healing.validation_errors,
        next_action=healed["recommended_next_action"],
        verification_evidence=healed["verification_evidence"],
        completion_quality=healed["completion_quality"],
        skill_evidence=skill_evidence,
        routing_plan=routing_plan,
    )


def _finish(
    *,
    status: str,
    project_root: str,
    creation_status: str,
    scaffold_status: str,
    implementation_status: str,
    patch_status: str,
    verification_status: str,
    self_healing_status: str,
    artifacts: list[str],
    errors: list[str],
    next_action: str,
    verification_evidence: dict[str, Any] | None = None,
    completion_quality: str = "REVIEW_REQUIRED",
    skill_evidence: SkillEvidenceResult | None = None,
    routing_plan: PipelineRoutingPlan | None = None,
) -> EndToEndProjectResult:
    project_path = Path(project_root)
    summary_dir = _summary_dir(project_path)
    summary_dir.mkdir(parents=True, exist_ok=True)
    consensus = {
        "status": status,
        "consensus_decision": _consensus_decision(status),
        "confidence": "Medium",
        "completion_quality": completion_quality,
        "verification_evidence": verification_evidence or _empty_verification_evidence(verification_status),
        "skill_evidence_status": skill_evidence.status if skill_evidence else "SKIPPED",
        "model_routing_status": routing_plan.status if routing_plan else "SKIPPED",
    }
    skill_recommendations = skill_evidence.recommendations if skill_evidence else []
    adjusted_next_action = _skill_evidence_next_action(next_action, skill_evidence)
    result = EndToEndProjectResult(
        status=status,
        project_root=project_root,
        creation_status=creation_status,
        scaffold_status=scaffold_status,
        implementation_status=implementation_status,
        patch_status=patch_status,
        verification_status=verification_status,
        self_healing_status=self_healing_status,
        consensus=consensus,
        next_action=adjusted_next_action,
        recommended_next_action=adjusted_next_action,
        completion_quality=completion_quality,
        verification_evidence=verification_evidence or _empty_verification_evidence(verification_status),
        skill_evidence_used=skill_evidence is not None and skill_evidence.status != "SKIPPED",
        skill_evidence_status=skill_evidence.status if skill_evidence else "SKIPPED",
        skill_evidence_summary=skill_evidence.summary if skill_evidence else "",
        skill_evidence_recommendations=skill_recommendations,
        skill_evidence_artifacts=skill_evidence.artifacts if skill_evidence else [],
        execution_mode=routing_plan.mode if routing_plan else "FAST",
        model_routing_status=routing_plan.status if routing_plan else "SKIPPED",
        model_routing_decisions=routing_plan.decisions if routing_plan else [],
        model_routing_artifacts=routing_plan.artifacts if routing_plan else [],
        artifacts=artifacts,
        validation_errors=_dedupe(errors),
    )
    generated = _write_end_to_end_artifacts(summary_dir, result)
    return EndToEndProjectResult(**{**result.to_dict(), "artifacts": [*artifacts, *generated]})


def _write_end_to_end_artifacts(summary_dir: Path, result: EndToEndProjectResult) -> list[str]:
    plan = summary_dir / "61_end_to_end_plan.md"
    progress = summary_dir / "62_end_to_end_progress.json"
    consensus = summary_dir / "63_end_to_end_consensus.json"
    action = summary_dir / "64_end_to_end_action_plan.json"
    summary = summary_dir / "65_end_to_end_summary.md"
    evidence_json = summary_dir / "66_end_to_end_verification_evidence.json"
    evidence_md = summary_dir / "66_end_to_end_verification_evidence.md"
    plan.write_text("# End-to-End Project Plan\n\nIdea -> Creation -> Scaffold -> Implementation -> Verification.\n", encoding="utf-8")
    progress.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    consensus.write_text(json.dumps(result.consensus, indent=2), encoding="utf-8")
    action.write_text(
        json.dumps(
            {
                "status": "VALID",
                "recommended_next_action": result.recommended_next_action,
                "blocked": result.status not in {"COMPLETED_VERIFIED", "COMPLETED_UNVERIFIED"},
                "completion_quality": result.completion_quality,
                "verification_evidence": result.verification_evidence,
                "skill_evidence_status": result.skill_evidence_status,
                "skill_evidence_recommendations": result.skill_evidence_recommendations,
                "execution_mode": result.execution_mode,
                "model_routing_status": result.model_routing_status,
                "model_routing_decisions": result.model_routing_decisions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary.write_text(_summary_markdown(result), encoding="utf-8")
    evidence_json.write_text(json.dumps(result.verification_evidence, indent=2), encoding="utf-8")
    evidence_md.write_text(_evidence_markdown(result), encoding="utf-8")
    return [str(plan), str(progress), str(consensus), str(action), str(summary), str(evidence_json), str(evidence_md)]


def _classify_verification(verification: Any, patch_status: str) -> dict[str, Any]:
    evidence = _verification_evidence(verification)
    status = getattr(verification, "status", "SKIPPED")
    if status == "PASSED" and evidence["commands_executed"]:
        return _classification("COMPLETED_VERIFIED", "VERIFIED", "completed_verified", evidence)
    if status == "SKIPPED" and not evidence["tests_detected"]:
        return _classification("NEEDS_TESTS", "REVIEW_REQUIRED", "add_project_tests", evidence)
    if status == "SKIPPED" and patch_status == "APPLIED":
        return _classification("COMPLETED_UNVERIFIED", "UNVERIFIED", "run_project_verification", evidence)
    if status == "BLOCKED":
        return _classification("BLOCKED", "REVIEW_REQUIRED", "review_verification_blockers", evidence)
    return _classification("NEEDS_REVIEW", "REVIEW_REQUIRED", "review_generated_project", evidence)


def _classify_self_healing(initial_verification: Any, self_healing: Any) -> dict[str, Any]:
    evidence = _verification_evidence(initial_verification)
    if getattr(self_healing, "status", "") == "REPAIRED" and getattr(self_healing, "verification_status", "") == "PASSED":
        repaired_evidence = {**evidence, "verification_status": "PASSED", "evidence_level": "STRONG"}
        return _classification("COMPLETED_VERIFIED", "VERIFIED", "completed_verified", repaired_evidence)
    if getattr(self_healing, "status", "") == "FAILED_PERMANENTLY":
        return _classification("FAILED_PERMANENTLY", "REVIEW_REQUIRED", "resolve_failures", evidence)
    if getattr(self_healing, "status", "") == "BLOCKED":
        return _classification("BLOCKED", "REVIEW_REQUIRED", "review_self_healing_blockers", evidence)
    return _classification("FAILED", "REVIEW_REQUIRED", getattr(self_healing, "next_action", "resolve_failures"), evidence)


def _classification(
    status: str,
    completion_quality: str,
    recommended_next_action: str,
    verification_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "completion_quality": completion_quality,
        "recommended_next_action": recommended_next_action,
        "verification_evidence": verification_evidence,
    }


def _verification_evidence(verification: Any) -> dict[str, Any]:
    commands_selected = list(getattr(verification, "commands_selected", []))
    commands_executed = list(getattr(verification, "commands_executed", []))
    status = str(getattr(verification, "status", "SKIPPED"))
    tests_detected = bool(commands_selected)
    if status == "PASSED" and commands_executed:
        evidence_level = "STRONG"
    elif status in {"FAILED", "TIMEOUT"} and commands_executed:
        evidence_level = "MEDIUM"
    elif tests_detected:
        evidence_level = "WEAK"
    else:
        evidence_level = "NONE"
    return {
        "commands_executed": commands_executed,
        "tests_detected": tests_detected,
        "commands_selected": commands_selected,
        "stdout_artifacts": list(getattr(verification, "stdout_artifacts", [])),
        "stderr_artifacts": list(getattr(verification, "stderr_artifacts", [])),
        "verification_status": status,
        "evidence_level": evidence_level,
    }


def _empty_verification_evidence(status: str) -> dict[str, Any]:
    return {
        "commands_executed": [],
        "tests_detected": False,
        "commands_selected": [],
        "stdout_artifacts": [],
        "stderr_artifacts": [],
        "verification_status": status,
        "evidence_level": "NONE",
    }


def _consensus_decision(status: str) -> str:
    decisions = {
        "COMPLETED_VERIFIED": "PROJECT_COMPLETED_VERIFIED",
        "COMPLETED_UNVERIFIED": "PROJECT_COMPLETED_UNVERIFIED",
        "NEEDS_TESTS": "PROJECT_NEEDS_TESTS",
        "NEEDS_REVIEW": "PROJECT_NEEDS_REVIEW",
    }
    return decisions.get(status, status)


def _summary_markdown(result: EndToEndProjectResult) -> str:
    warning = ""
    if result.completion_quality != "VERIFIED":
        warning = (
            "\n\n## Verification Warning\n\n"
            "Project generated but not fully verified. Add tests or run project verification before treating this as production-ready.\n"
        )
    return "\n".join(
        [
            "# End-to-End Summary",
            "",
            f"Status: {result.status}",
            f"Completion quality: {result.completion_quality}",
            f"Evidence level: {result.verification_evidence.get('evidence_level', 'NONE')}",
            f"Tests detected: {result.verification_evidence.get('tests_detected', False)}",
            f"Commands executed: {len(result.verification_evidence.get('commands_executed', []))}",
            f"Recommended next action: {result.recommended_next_action}",
            f"Skill evidence used: {result.skill_evidence_used}",
            f"Skill evidence status: {result.skill_evidence_status}",
            f"Skill evidence summary: {result.skill_evidence_summary}",
            f"Execution mode: {result.execution_mode}",
            f"Model routing status: {result.model_routing_status}",
            warning.rstrip(),
            "",
        ]
    )


def _build_optional_skill_evidence(
    *,
    enabled: bool,
    roots: list[str | Path] | None,
    run_dir: Path | None,
) -> SkillEvidenceResult:
    if not enabled:
        return SkillEvidenceResult(
            status="SKIPPED",
            evidence_items=[],
            sources_used=[],
            summary="Skill evidence disabled.",
            recommendations=[],
            risks=[],
            artifacts=[],
            validation_errors=[],
            validation_warnings=[],
        )
    return build_skill_evidence_bundle(roots, run_dir=run_dir)


def _skill_evidence_next_action(next_action: str, skill_evidence: SkillEvidenceResult | None) -> str:
    if skill_evidence is None or skill_evidence.status != "VALID":
        return next_action
    if next_action in {"add_project_tests", "review_generated_patch_set", "review_generated_project"}:
        return f"{next_action}_and_consult_skill_evidence"
    return next_action


def _evidence_markdown(result: EndToEndProjectResult) -> str:
    evidence = result.verification_evidence
    commands = evidence.get("commands_executed", [])
    return "\n".join(
        [
            "# End-to-End Verification Evidence",
            "",
            f"Verification status: {evidence.get('verification_status')}",
            f"Evidence level: {evidence.get('evidence_level')}",
            f"Tests detected: {evidence.get('tests_detected')}",
            "",
            "## Commands Executed",
            *[f"- {' '.join(command)}" for command in commands],
            "",
            "## Stdout Artifacts",
            *[f"- {path}" for path in evidence.get("stdout_artifacts", [])],
            "",
            "## Stderr Artifacts",
            *[f"- {path}" for path in evidence.get("stderr_artifacts", [])],
            "",
        ]
    )


def _summary_dir(project_root: Path) -> Path:
    if project_root.exists() and not _is_ann_repo(project_root):
        return project_root / "outputs" / "end_to_end"
    fallback_root = Path(os.environ.get("ANN_E2E_ORCHESTRATOR_ARTIFACTS_ROOT", Path(__file__).resolve().parents[2] / "outputs" / "end_to_end")).resolve()
    return fallback_root


def _latest_run_dir(project_root: Path) -> Path:
    runs = project_root / "outputs" / "runs"
    candidates = sorted((path for path in runs.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    return candidates[0] if candidates else runs / "manual"


def _is_ann_repo(path: Path) -> bool:
    try:
        resolved = path.resolve()
        repo_root = Path(__file__).resolve().parents[2]
        if _is_allowed_repo_project_root(resolved, repo_root):
            return False
        resolved.relative_to(repo_root)
        return True
    except ValueError:
        return False


def _is_allowed_repo_project_root(path: Path, repo_root: Path) -> bool:
    allowed_roots = [
        repo_root / "generated-projects",
        repo_root / "outputs" / "autonomous_capability_projects",
    ]
    return any(path == allowed.resolve() or _is_relative_to(path, allowed.resolve()) for allowed in allowed_roots)


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
