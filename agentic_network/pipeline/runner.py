"""Multi-agent pipeline runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable

from agentic_network.agents import (
    ArchitectAgent,
    CodeAgent,
    FinalReviewerAgent,
    FixerAgent,
    ProductAgent,
    ReviewerAgent,
    SecurityAgent,
    TestEngineerAgent,
)
from agentic_network.architect_agent.runtime import ArchitectAgentRuntimeModel
from agentic_network.autonomous_loop.runtime import (
    AutonomousLoopResult,
    autonomous_loop_summary_fields,
    run_autonomous_engineering_loop,
)
from agentic_network.code_agent.runtime import (
    CodeAgentRuntimeModel,
    parse_code_agent_sections,
    validate_code_agent_response,
)
from agentic_network.config import PipelineConfig, SUPPORTED_MODEL_BACKENDS
from agentic_network.context_agent.runtime import (
    ContextResult,
    build_context as build_context_briefing,
)
from agentic_network.fixer_agent.runtime import (
    FixerAgentRuntimeModel,
    parse_fixer_agent_sections,
    validate_fixer_agent_response,
)
from agentic_network.failure_context.runtime import (
    compile_pipeline_failure_context,
    render_failure_context_markdown,
    write_failure_context_artifacts,
)
from agentic_network.execution_agent.runtime import ExecutionPlanResult, generate_execution_plan
from agentic_network.final_reviewer.runtime import (
    FinalReviewerRuntimeModel,
    parse_final_reviewer_sections,
    validate_final_reviewer_response,
)
from agentic_network.handoff.runtime import HandoffBundleResult, build_handoff_bundle
from agentic_network.human_approval_agent.runtime import (
    HumanApprovalResult,
    authorize_apply,
    human_approval_summary_fields,
)
from agentic_network.knowledge_agent.runtime import (
    KnowledgeCaptureResult,
    capture_knowledge,
)
from agentic_network.memory_agent.runtime import (
    MemoryResult,
    memory_summary_fields,
    record_engineering_experience,
)
from agentic_network.merge_readiness_agent.runtime import (
    MergeReadinessResult,
    evaluate_merge_readiness,
    merge_readiness_summary_fields,
)
from agentic_network.memory_agent.retrieval import memory_retrieval_summary_fields
from agentic_network.models import (
    BaseModelClient,
    DeepSeekGGUFModel,
    DeepSeekUnslothModel,
    DeterministicMockModel,
)
from agentic_network.models import Qwen3Model, QwenUnslothModel
from agentic_network.model_routing.runtime import build_pipeline_routing_plan
from agentic_network.pipeline.artifacts import STAGE_FILES, RunArtifacts
from agentic_network.runtime_engine.loader import get_runtime_metrics
from agentic_network.patch_approval_agent.runtime import PatchApprovalResult, approve_patches
from agentic_network.patch_quality_agent.runtime import (
    PatchQualityResult,
    evaluate_patch_quality,
    patch_quality_summary_fields,
)
from agentic_network.patch_apply_agent.runtime import (
    PatchApplyResult,
    apply_approved_patches,
    patch_apply_summary_fields,
)
from agentic_network.revision_agent.runtime import RevisionResult, apply_revisions
from agentic_network.product_agent.runtime import ProductAgentRuntimeModel
from agentic_network.reviewer_agent.runtime import (
    ReviewerAgentRuntimeModel,
    parse_reviewer_agent_sections,
    validate_reviewer_agent_response,
)
from agentic_network.repository_intelligence_agent.runtime import (
    RepositoryIntelligenceResult,
    build_repository_intelligence,
    repository_intelligence_summary_fields,
)
from agentic_network.repository_intelligence_agent.retrieval import (
    RepositoryContextResult,
    build_repository_context,
    repository_context_summary_fields,
)
from agentic_network.security_agent.runtime import (
    SecurityAgentRuntimeModel,
    parse_security_agent_sections,
    validate_security_agent_response,
)
from agentic_network.self_healing_agent.runtime import (
    SelfHealingResult,
    run_self_healing,
    self_healing_summary_fields,
)
from agentic_network.test_runner_agent.runtime import (
    TestRunnerResult,
    run_tests_for_run,
    test_runner_summary_fields,
)
from agentic_network.test_engineer.runtime import (
    TestEngineerRuntimeModel,
    parse_test_engineer_sections,
    validate_test_engineer_response,
)
from agentic_network.pipeline.static_sanity_checker import (
    StaticSanityInput,
    count_static_sanity_findings,
    has_blocking_static_sanity_findings,
    run_static_sanity_checker,
)

SUPPORTED_STAGES = (
    "context",
    "repository_intelligence",
    "repository_context",
    "product",
    "architect",
    "code",
    "test",
    "security",
    "reviewer",
    "fixer",
    "revision",
    "final",
    "execution",
    "patch_quality",
    "patch_approval",
    "patch_apply",
    "test_runner",
    "self_healing",
    "autonomous_loop",
    "merge_readiness",
    "memory",
    "human_approval",
    "knowledge",
    "handoff",
)
DEFAULT_STAGES = tuple(stage for stage in SUPPORTED_STAGES if stage not in {"patch_apply", "test_runner", "self_healing", "autonomous_loop", "merge_readiness", "memory", "human_approval"})
ROLE_BACKEND_CONFIG = {
    "product": ("PRODUCT_MODEL_BACKEND", "product_model_backend"),
    "architect": ("ARCHITECT_MODEL_BACKEND", "architect_model_backend"),
    "code": ("CODE_MODEL_BACKEND", "code_model_backend"),
    "test": ("TEST_MODEL_BACKEND", "test_model_backend"),
    "security": ("SECURITY_MODEL_BACKEND", "security_model_backend"),
    "reviewer": ("REVIEWER_MODEL_BACKEND", "reviewer_model_backend"),
    "fixer": ("FIXER_MODEL_BACKEND", "fixer_model_backend"),
    "final": ("FINAL_REVIEWER_MODEL_BACKEND", "final_reviewer_model_backend"),
}




@dataclass(frozen=True)
class ApplyOrchestration:
    apply_requested: bool
    approve_patches_flag: bool
    approval_token_provided: bool
    selected_stages: tuple[str, ...]
    valid: bool
    errors: list[str]

@dataclass(frozen=True)
class PipelineResult:
    output_dir: str
    reviewer_status: str
    final_status: str
    stages_run: list[str]
    output_files: dict[str, str]


class PipelineRunner:
    """Runs the local multi-agent pipeline with role-based model routing."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        mock: bool = False,
        mock_changes_required: bool = True,
    ) -> None:
        self.config = config
        self.mock = mock
        self.mock_changes_required = mock_changes_required
        self._models: dict[str, BaseModelClient] = {}
        self._validate_model_backends()

    def run(
        self,
        task: str,
        *,
        stages: Iterable[str] | None = None,
        skip_fixer: bool = False,
        run_tests: bool = False,
        test_timeout_seconds: int = 300,
        approve_apply: bool = False,
        approval_token: str | None = None,
        apply_requested: bool = False,
        approve_patches: bool = False,
        execution_mode: str = "FAST",
    ) -> PipelineResult:
        selected_stages = self._normalize_stages(stages)
        apply_orchestration = _prepare_apply_orchestration(
            selected_stages,
            apply_requested=apply_requested,
            approve_patches=approve_patches,
            approval_token=approval_token,
        )
        selected_stages = apply_orchestration.selected_stages
        artifacts = RunArtifacts.create(
            self.config.output_dir,
            task,
            architect_output=self.config.architect_output,
            security_output=self.config.security_output,
            reviewer_output=self.config.reviewer_output,
            fixer_output=self.config.fixer_output,
            final_output=self.config.final_reviewer_output,
        )
        outputs: dict[str, str] = {"user": task}
        stages_run: list[str] = []
        stage_timings: list[dict[str, object]] = []
        context_result: ContextResult | None = None
        repository_intelligence_result: RepositoryIntelligenceResult | None = None
        repository_context_result: RepositoryContextResult | None = None
        knowledge_result: KnowledgeCaptureResult | None = None
        handoff_result: HandoffBundleResult | None = None
        revision_result: RevisionResult | None = None
        execution_result: ExecutionPlanResult | None = None
        patch_quality_result: PatchQualityResult | None = None
        patch_approval_result: PatchApprovalResult | None = None
        patch_apply_result: PatchApplyResult | None = None
        test_runner_result: TestRunnerResult | None = None
        self_healing_result: SelfHealingResult | None = None
        autonomous_loop_result: AutonomousLoopResult | None = None
        merge_readiness_result: MergeReadinessResult | None = None
        memory_result: MemoryResult | None = None
        human_approval_result: HumanApprovalResult | None = None
        patch_apply_preflight_done = False
        reviewer_status = "NOT RUN"
        final_status = "NOT RUN"

        artifacts.save_stage("user", task)
        routing_plan = build_pipeline_routing_plan(
            list(selected_stages),
            mode=execution_mode,
            run_dir=artifacts.root,
        )
        for index, path in enumerate(routing_plan.artifacts, start=1):
            key = "model_routing_plan" if index == 1 else "model_routing_json" if index == 2 else "model_routing_trace"
            artifacts.output_files[key] = path
        routing_by_stage = {
            str(decision.get("agent_name")): decision
            for decision in routing_plan.decisions
            if isinstance(decision, dict)
        }

        try:
            if not apply_orchestration.valid:
                raise ValueError(
                    "Invalid apply orchestration: "
                    + ", ".join(apply_orchestration.errors)
                )

            for index, stage in enumerate(selected_stages, start=1):
                if stage in {"fixer", "revision", "final", "execution", "patch_quality", "patch_approval", "patch_apply", "test_runner", "self_healing", "autonomous_loop", "merge_readiness", "memory", "human_approval", "knowledge", "handoff"}:
                    continue
                print(f"[{index}/{len(selected_stages)}] Running {self._stage_label(stage)}...")
                if stage == "context":
                    context_result = _run_context_stage(
                        task=task,
                        knowledge_root=self.config.project_root / "knowledge",
                        memory_root=self.config.project_root / "memory",
                        run_dir=artifacts.root,
                        stage_timings=stage_timings,
                    )
                    outputs["context"] = context_result.context_artifact
                    artifacts.save_stage("context", context_result.context_artifact)
                    if context_result.experience_context_result is not None:
                        artifacts.output_files["memory_query"] = str(
                            artifacts.root / "22_memory_query.md"
                        )
                        artifacts.output_files["memory_matches"] = str(
                            artifacts.root / "23_memory_matches.md"
                        )
                        artifacts.output_files["experience_context"] = str(
                            artifacts.root / "24_experience_context.md"
                        )
                    stages_run.append("context")
                    continue
                if stage == "repository_intelligence":
                    repository_intelligence_result = _run_repository_intelligence_stage(
                        project_root=self.config.project_root,
                        run_dir=artifacts.root,
                        stage_timings=stage_timings,
                    )
                    outputs["repository_intelligence"] = _repository_intelligence_brief(
                        repository_intelligence_result
                    )
                    for key, path in repository_intelligence_result.output_files.items():
                        artifacts.output_files[f"repository_intelligence_{key}"] = path
                    stages_run.append("repository_intelligence")
                    continue
                if stage == "repository_context":
                    repository_context_result = _run_repository_context_stage(
                        task=task,
                        run_dir=artifacts.root,
                        stage_timings=stage_timings,
                    )
                    outputs["repository_context"] = Path(
                        repository_context_result.context_artifact
                    ).read_text(encoding="utf-8")
                    artifacts.output_files["repository_context"] = (
                        repository_context_result.context_artifact
                    )
                    artifacts.output_files["repository_context_json"] = (
                        repository_context_result.compact_json_artifact
                    )
                    stages_run.append("repository_context")
                    continue
                if stage == "reviewer" and "static_sanity" not in outputs:
                    output = run_static_sanity_checker(
                        StaticSanityInput(
                            task=outputs.get("user", ""),
                            architecture=outputs.get("architect", ""),
                            code=outputs.get("code", ""),
                            tests=outputs.get("test", ""),
                            security=outputs.get("security", ""),
                        )
                    )
                    outputs["static_sanity"] = output
                    artifacts.save_stage("static_sanity", output)
                output = self._run_stage(
                    stage,
                    outputs,
                    stage_timings,
                    stages_run,
                    artifacts,
                    routing_by_stage,
                )
                outputs[stage] = output
                artifacts.save_stage(stage, output)
                stages_run.append(stage)
                if stage == "reviewer":
                    reviewer_status = extract_status(output)

            explicit_fixer_requested = stages is not None and "fixer" in selected_stages
            should_run_fixer = (
                explicit_fixer_requested
                or (
                    "reviewer" in stages_run
                    and reviewer_status == "CHANGES REQUIRED"
                    and not skip_fixer
                    and stages is None
                )
            )
            if should_run_fixer:
                print("[fixer] Running Fixer Agent...")
                failure_context = _compile_and_save_failure_context(
                    artifacts=artifacts,
                    outputs=outputs,
                    project_root=self.config.project_root,
                )
                outputs["failure_context"] = failure_context
                output = self._run_stage(
                    "fixer",
                    outputs,
                    stage_timings,
                    stages_run,
                    artifacts,
                    routing_by_stage,
                )
                outputs["fixer"] = output
                artifacts.save_stage("fixer", output)
                stages_run.append("fixer")
                post_fix_output = run_static_sanity_checker(
                    StaticSanityInput(
                        task=outputs.get("user", ""),
                        architecture=outputs.get("architect", ""),
                        code=outputs.get("code", ""),
                        tests=outputs.get("test", ""),
                        security=outputs.get("security", ""),
                        reviewer=outputs.get("reviewer", ""),
                        fixer=outputs.get("fixer", ""),
                    )
                )
                outputs["post_fix_static_sanity"] = post_fix_output
                artifacts.save_stage("post_fix_static_sanity", post_fix_output)
                _set_timing_flag(stage_timings, "fixer", "post_fix_sanity_ran", True)
            elif stages is None and "fixer" in selected_stages and "reviewer" in stages_run:
                reason = (
                    "Fixer skipped because --skip-fixer was set."
                    if skip_fixer and reviewer_status == "CHANGES REQUIRED"
                    else "Fixer skipped because reviewer did not require changes."
                )
                output = f"SKIPPED\n{reason}\n"
                outputs["fixer"] = output
                artifacts.save_stage("fixer", output)

            if "revision" in selected_stages and "revision" not in stages_run:
                print("[revision] Running Revision Agent...")
                revision_result = _run_revision_stage(
                    artifacts=artifacts,
                    outputs=outputs,
                    stage_timings=stage_timings,
                )
                outputs["revision"] = revision_result.revision_summary
                outputs["code_revised"] = revision_result.revised_code
                outputs["test_revised"] = revision_result.revised_tests
                outputs["security_revised"] = revision_result.revised_security
                artifacts.output_files["revision"] = revision_result.artifact_path
                artifacts.output_files["code_revised"] = revision_result.code_artifact_path
                artifacts.output_files["test_revised"] = revision_result.test_artifact_path
                artifacts.output_files["security_revised"] = revision_result.security_artifact_path
                stages_run.append("revision")

            if "final" in selected_stages and "final" not in stages_run:
                print("[final] Running Final Reviewer Agent...")
                output = self._run_stage(
                    "final",
                    outputs,
                    stage_timings,
                    stages_run,
                    artifacts,
                    routing_by_stage,
                )
                outputs["final"] = output
                artifacts.save_stage("final", output)
                stages_run.append("final")
                final_status = extract_status(output)
                if _post_fix_blocks_approval(outputs) and final_status == "APPROVED":
                    final_status = "CHANGES REQUIRED"

            if "execution" in selected_stages and "execution" not in stages_run:
                print("[execution] Running Execution Agent...")
                execution_result = _run_execution_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["execution"] = execution_result.execution_plan
                artifacts.output_files["execution"] = execution_result.artifact_path
                for index, patch_path in enumerate(execution_result.patch_paths, start=1):
                    artifacts.output_files[f"execution_patch_{index:03d}"] = patch_path
                stages_run.append("execution")

            if "patch_quality" in selected_stages and "patch_quality" not in stages_run:
                print("[patch_quality] Running Patch Quality Agent...")
                if execution_result is not None:
                    artifacts.save_summary(
                        {
                            "timestamp": artifacts.timestamp,
                            "task": task,
                            "stages_run": stages_run,
                            "reviewer_status": reviewer_status,
                            "final_status": final_status,
                            **_execution_summary_fields(execution_result),
                        }
                    )
                patch_quality_result = _run_patch_quality_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["patch_quality"] = patch_quality_result.report
                artifacts.output_files["patch_quality"] = patch_quality_result.artifact_path
                stages_run.append("patch_quality")

            if "patch_approval" in selected_stages and "patch_approval" not in stages_run:
                print("[patch_approval] Running Patch Approval Agent...")
                patch_approval_result = _run_patch_approval_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["patch_approval"] = patch_approval_result.approval_output
                artifacts.output_files["patch_approval"] = patch_approval_result.artifact_path
                stages_run.append("patch_approval")

            if not apply_requested and "patch_apply" in selected_stages and "patch_apply" not in stages_run:
                print("[patch_apply] Running Patch Apply Agent in dry-run/no-approval mode...")
                _save_patch_apply_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    apply_orchestration=apply_orchestration,
                )
                patch_apply_result = _run_patch_apply_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    approve_patches=False,
                    dry_run=True,
                )
                outputs["patch_apply"] = patch_apply_result.report
                artifacts.output_files["patch_apply"] = patch_apply_result.artifact_path
                stages_run.append("patch_apply")

            if apply_requested and "patch_apply" in selected_stages and not patch_apply_preflight_done:
                print("[patch_apply] Running Patch Apply Agent pre-authorization dry run...")
                _save_patch_apply_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    apply_orchestration=apply_orchestration,
                )
                patch_apply_result = _run_patch_apply_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    approve_patches=True,
                    dry_run=True,
                )
                outputs["patch_apply"] = patch_apply_result.report
                artifacts.output_files["patch_apply"] = patch_apply_result.artifact_path
                patch_apply_preflight_done = True

            if "test_runner" in selected_stages and "test_runner" not in stages_run:
                print("[test_runner] Running Test Runner Agent...")
                _save_test_runner_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                )
                test_runner_result = _run_test_runner_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    run_tests=run_tests,
                    timeout_seconds=test_timeout_seconds,
                )
                outputs["test_runner"] = test_runner_result.report
                artifacts.output_files["test_runner"] = test_runner_result.artifact_path
                stages_run.append("test_runner")

            if "self_healing" in selected_stages and "self_healing" not in stages_run:
                print("[self_healing] Running Self Healing Agent...")
                _save_self_healing_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                    test_runner_result=test_runner_result,
                )
                self_healing_result = _run_self_healing_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["self_healing"] = self_healing_result.report
                artifacts.output_files["self_healing"] = self_healing_result.self_healing_path
                artifacts.output_files["failure_analysis"] = self_healing_result.failure_analysis_path
                artifacts.output_files["root_cause"] = self_healing_result.root_cause_path
                if self_healing_result.retry_patch_path:
                    artifacts.output_files["self_healing_retry_patch"] = self_healing_result.retry_patch_path
                stages_run.append("self_healing")

            if "autonomous_loop" in selected_stages and "autonomous_loop" not in stages_run:
                print("[autonomous_loop] Running Autonomous Engineering Loop...")
                _save_autonomous_loop_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                    test_runner_result=test_runner_result,
                    self_healing_result=self_healing_result,
                )
                autonomous_loop_result = _run_autonomous_loop_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    approve_patches=approve_patches if apply_requested else False,
                    approval_token=approval_token,
                    run_tests=run_tests,
                    timeout_seconds=test_timeout_seconds,
                )
                outputs["autonomous_loop"] = autonomous_loop_result.report
                artifacts.output_files["autonomous_loop"] = autonomous_loop_result.artifact_path
                stages_run.append("autonomous_loop")

            if "merge_readiness" in selected_stages and "merge_readiness" not in stages_run:
                print("[merge_readiness] Running Merge Readiness Agent...")
                _save_merge_readiness_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                    test_runner_result=test_runner_result,
                    self_healing_result=self_healing_result,
                    autonomous_loop_result=autonomous_loop_result,
                )
                merge_readiness_result = _run_merge_readiness_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["merge_readiness"] = merge_readiness_result.report
                artifacts.output_files["merge_readiness"] = merge_readiness_result.artifact_path
                stages_run.append("merge_readiness")

            if "memory" in selected_stages and "memory" not in stages_run:
                print("[memory] Running Memory Agent...")
                _save_memory_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                    test_runner_result=test_runner_result,
                    self_healing_result=self_healing_result,
                    autonomous_loop_result=autonomous_loop_result,
                    merge_readiness_result=merge_readiness_result,
                    memory_result=memory_result,
                )
                memory_result = _run_memory_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["memory"] = str(memory_result.memory_dir)
                artifacts.output_files["memory"] = memory_result.memory_dir
                stages_run.append("memory")

            if "human_approval" in selected_stages and "human_approval" not in stages_run:
                print("[human_approval] Running Human Approval Agent...")
                _save_human_approval_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    patch_apply_result=patch_apply_result,
                    test_runner_result=test_runner_result,
                    self_healing_result=self_healing_result,
                    autonomous_loop_result=autonomous_loop_result,
                    merge_readiness_result=merge_readiness_result,
                )
                human_approval_result = _run_human_approval_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    approve_apply=approve_apply or (apply_requested and approve_patches),
                    approval_token=approval_token,
                )
                outputs["human_approval"] = human_approval_result.report
                artifacts.output_files["human_approval"] = human_approval_result.artifact_path
                stages_run.append("human_approval")

            if apply_requested and "patch_apply" in selected_stages and "patch_apply" not in stages_run:
                print("[patch_apply] Running Patch Apply Agent in approved apply mode...")
                _save_patch_apply_prerequisite_summary(
                    artifacts=artifacts,
                    task=task,
                    stages_run=stages_run,
                    reviewer_status=reviewer_status,
                    final_status=final_status,
                    stage_timings=stage_timings,
                    outputs=outputs,
                    patch_approval_result=patch_approval_result,
                    apply_orchestration=apply_orchestration,
                    merge_readiness_result=merge_readiness_result,
                    human_approval_result=human_approval_result,
                    self_healing_result=self_healing_result,
                    memory_result=memory_result,
                )
                patch_apply_result = _run_patch_apply_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                    approve_patches=approve_patches if apply_requested else False,
                    dry_run=not apply_requested,
                )
                outputs["patch_apply"] = patch_apply_result.report
                artifacts.output_files["patch_apply"] = patch_apply_result.artifact_path
                stages_run.append("patch_apply")

        except Exception as exc:
            error_output = (
                "Pipeline failed while running stages.\n\n"
                f"ERROR:\n{format_exception(exc)}\n"
            )
            error_path = artifacts.root / "error.md"
            error_path.write_text(error_output, encoding="utf-8")
            artifacts.output_files["error"] = str(error_path)
            raise
        finally:
            if final_status == "NOT RUN" and "final" in outputs:
                final_status = extract_status(outputs["final"])
            summary = {
                "timestamp": artifacts.timestamp,
                "task": task,
                "stages_run": stages_run,
                "reviewer_status": reviewer_status,
                "final_status": final_status,
                "stage_timings": stage_timings,
                **_model_routing_summary_fields(routing_plan),
                **_runtime_engine_summary_fields(),
                **_code_summary_fields(artifacts, outputs),
                **_test_summary_fields(artifacts, outputs),
                **_security_summary_fields(artifacts, outputs, stage_timings),
                **_reviewer_summary_fields(artifacts, outputs, stage_timings),
                **_fixer_summary_fields(artifacts, outputs, stage_timings),
                **_failure_context_summary_fields(artifacts),
                **_revision_summary_fields(revision_result),
                **_final_summary_fields(artifacts, outputs, stage_timings),
                **_execution_summary_fields(execution_result),
                **_repository_intelligence_summary_fields(repository_intelligence_result),
                **_repository_context_summary_fields(repository_context_result),
                **_patch_quality_summary_fields(patch_quality_result),
                **_patch_approval_summary_fields(patch_approval_result),
                **_patch_apply_summary_fields(patch_apply_result),
                **_test_runner_summary_fields(test_runner_result),
                **_self_healing_summary_fields(self_healing_result),
                **_autonomous_loop_summary_fields(autonomous_loop_result),
                **_merge_readiness_summary_fields(merge_readiness_result),
                **_memory_summary_fields(memory_result),
                **_human_approval_summary_fields(human_approval_result),
                **_apply_orchestration_summary_fields(apply_orchestration),
                **_post_fix_summary_fields(artifacts, outputs, stages_run),
                **_context_summary_fields(context_result, artifacts),
            }
            artifacts.save_summary(summary)
            if (
                "knowledge" in selected_stages
                and "knowledge" not in stages_run
                and "error" not in artifacts.output_files
            ):
                knowledge_result = _run_knowledge_stage(
                    artifacts=artifacts,
                    stage_timings=stage_timings,
                )
                outputs["knowledge"] = Path(knowledge_result.artifact_path).read_text(
                    encoding="utf-8"
                )
                artifacts.output_files["knowledge"] = knowledge_result.artifact_path
                stages_run.append("knowledge")
                summary = {
                    **summary,
                    "stages_run": stages_run,
                    "stage_timings": stage_timings,
                    **_model_routing_summary_fields(routing_plan),
                    **_runtime_engine_summary_fields(),
                    **_knowledge_summary_fields(knowledge_result),
                    **_apply_orchestration_summary_fields(apply_orchestration),
                }
                artifacts.save_summary(summary)
            if (
                "handoff" in selected_stages
                and "handoff" not in stages_run
                and "error" not in artifacts.output_files
            ):
                handoff_result = _run_handoff_stage(
                    artifacts=artifacts,
                    task=task,
                    stage_timings=stage_timings,
                )
                outputs["handoff"] = Path(handoff_result.artifact_path).read_text(
                    encoding="utf-8"
                )
                artifacts.output_files["handoff"] = handoff_result.artifact_path
                stages_run.append("handoff")
                summary = {
                    **summary,
                    "stages_run": stages_run,
                    "stage_timings": stage_timings,
                    **_model_routing_summary_fields(routing_plan),
                    **_runtime_engine_summary_fields(),
                    **_handoff_summary_fields(handoff_result),
                    **_apply_orchestration_summary_fields(apply_orchestration),
                }
            artifacts.save_summary(summary)
            print_timing_table(stage_timings)

        return PipelineResult(
            output_dir=str(artifacts.root),
            reviewer_status=reviewer_status,
            final_status=final_status,
            stages_run=stages_run,
            output_files=artifacts.output_files,
        )

    def _run_stage(
        self,
        stage: str,
        outputs: dict[str, str],
        stage_timings: list[dict[str, object]],
        stages_run: list[str],
        artifacts: RunArtifacts,
        routing_by_stage: dict[str, dict[str, object]],
    ) -> str:
        started_at = _utc_now()
        started = perf_counter()
        input_text = _product_input(outputs) if stage == "product" else build_context(outputs)
        if self._should_isolate_stage(stage):
            output, model_backend, diagnostics = self._run_isolated_stage(
                stage,
                outputs,
                artifacts,
            )
        else:
            agent = self._agent_for_stage(stage)
            output = agent.run(input_text)
            model_backend = _model_backend_name(agent.model)
            diagnostics = _model_diagnostics(agent.model)
        ended = perf_counter()
        ended_at = _utc_now()
        stage_timings.append(
            {
                "stage": stage,
                "stage_name": self._stage_label(stage),
                "model_backend": model_backend,
                "started_at": _format_utc(started_at),
                "ended_at": _format_utc(ended_at),
                "duration_seconds": round(ended - started, 3),
                "input_char_count": len(input_text),
                "output_char_count": len(output),
                "gpu_config": _gpu_config_from_diagnostics(diagnostics),
                "device_info": _device_info_from_diagnostics(diagnostics),
                "static_sanity_ran": "static_sanity" in outputs,
                "fixer_ran": stage == "fixer" or "fixer" in stages_run,
                "post_fix_sanity_ran": "post_fix_static_sanity" in outputs,
                "model_route": routing_by_stage.get(stage) or {},
            }
        )
        return output

    def _should_isolate_stage(self, stage: str) -> bool:
        if self.mock or self.config.stage_isolation != "subprocess":
            return False
        if stage not in {
            "product",
            "architect",
            "code",
            "test",
            "security",
            "reviewer",
            "fixer",
            "final",
        }:
            return False
        if _stage_runtime_model_is_patched(stage):
            return False
        backend = self._backend_for_stage(stage)
        return backend in {"qwen3", "qwen_v5", "deepseek_unsloth", "deepseek"}

    def _run_isolated_stage(
        self,
        stage: str,
        outputs: dict[str, str],
        artifacts: RunArtifacts,
    ) -> tuple[str, str, dict[str, object]]:
        stage_output_path = artifacts.root / artifacts.stage_files[stage]
        stdout_path = artifacts.root / f"{stage}_subprocess_stdout.log"
        stderr_path = artifacts.root / f"{stage}_subprocess_stderr.log"
        command = self._isolated_stage_command(stage, outputs, stage_output_path)
        completed = subprocess.run(
            command,
            cwd=self.config.project_root,
            env=_isolated_subprocess_env(self.config.project_root),
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        artifacts.output_files[f"{stage}_subprocess_stdout"] = str(stdout_path)
        artifacts.output_files[f"{stage}_subprocess_stderr"] = str(stderr_path)
        if stage in {"code", "test", "security", "reviewer", "fixer", "final"}:
            validation_path = stage_output_path.with_suffix(".validation.json")
            if validation_path.exists():
                artifacts.output_files[f"{stage}_validation"] = str(validation_path)
        if completed.returncode not in {0, 2}:
            raise RuntimeError(
                f"Isolated {self._stage_label(stage)} failed with exit code "
                f"{completed.returncode}. See {stderr_path}."
            )
        if not stage_output_path.exists():
            raise RuntimeError(
                f"Isolated {self._stage_label(stage)} did not create {stage_output_path}."
            )
        output = stage_output_path.read_text(encoding="utf-8").strip()
        diagnostics = {
            "backend_name": self._isolated_backend_name(stage),
            "loaded_backend_type": "subprocess",
            "stage_isolation": "subprocess",
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }
        return output, self._isolated_backend_name(stage), diagnostics

    def _isolated_stage_command(
        self,
        stage: str,
        outputs: dict[str, str],
        stage_output_path: Path,
    ) -> list[str]:
        user_request = _product_input(outputs) if stage == "product" else outputs.get("user", "")
        if stage == "product":
            return [
                sys.executable,
                "-m",
                "agentic_network.product_agent.run",
                "--config",
                str(self.config.product_agent_config_path),
                "--max-new-tokens",
                str(self.config.product_max_new_tokens),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "architect":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            if not product_path.exists():
                product_path.write_text(
                    outputs.get("product", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            return [
                sys.executable,
                "-m",
                "agentic_network.architect_agent.run",
                "--mode",
                self.config.architect_mode,
                "--product-requirements-file",
                str(product_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "code":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            if not product_path.exists():
                product_path.write_text(
                    outputs.get("product", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            if not architecture_path.exists():
                architecture_path.write_text(
                    outputs.get("architect", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            return [
                sys.executable,
                "-m",
                "agentic_network.code_agent.run",
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "test":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            code_path = stage_output_path.parent / STAGE_FILES["code"]
            if not product_path.exists():
                product_path.write_text(
                    outputs.get("product", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            if not architecture_path.exists():
                architecture_path.write_text(
                    outputs.get("architect", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            if not code_path.exists():
                code_path.write_text(
                    outputs.get("code", "").rstrip() + "\n",
                    encoding="utf-8",
                )
            return [
                sys.executable,
                "-m",
                "agentic_network.test_engineer.run",
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--code-plan-file",
                str(code_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "security":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            code_path = stage_output_path.parent / STAGE_FILES["code"]
            test_path = stage_output_path.parent / STAGE_FILES["test"]
            for artifact_path, output_key in (
                (product_path, "product"),
                (architecture_path, "architect"),
                (code_path, "code"),
                (test_path, "test"),
            ):
                if not artifact_path.exists():
                    artifact_path.write_text(
                        outputs.get(output_key, "").rstrip() + "\n",
                        encoding="utf-8",
                    )
            return [
                sys.executable,
                "-m",
                "agentic_network.security_agent.run",
                "--mode",
                self.config.security_mode,
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--code-plan-file",
                str(code_path),
                "--test-plan-file",
                str(test_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "reviewer":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            code_path = _preferred_artifact_path(
                stage_output_path.parent, STAGE_FILES["code_revised"], STAGE_FILES["code"]
            )
            test_path = _preferred_artifact_path(
                stage_output_path.parent, STAGE_FILES["test_revised"], STAGE_FILES["test"]
            )
            security_path = _preferred_artifact_path(
                stage_output_path.parent,
                STAGE_FILES["security_revised"],
                self.config.security_output,
            )
            for artifact_path, output_key in (
                (product_path, "product"),
                (architecture_path, "architect"),
                (code_path, "code"),
                (test_path, "test"),
                (security_path, "security"),
            ):
                if not artifact_path.exists():
                    artifact_path.write_text(
                        outputs.get(output_key, "").rstrip() + "\n",
                        encoding="utf-8",
                    )
            return [
                sys.executable,
                "-m",
                "agentic_network.reviewer_agent.run",
                "--mode",
                self.config.reviewer_mode,
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--code-plan-file",
                str(code_path),
                "--test-plan-file",
                str(test_path),
                "--security-review-file",
                str(security_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "fixer":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            code_path = stage_output_path.parent / STAGE_FILES["code"]
            test_path = stage_output_path.parent / STAGE_FILES["test"]
            security_path = stage_output_path.parent / self.config.security_output
            reviewer_path = stage_output_path.parent / self.config.reviewer_output
            failure_context_path = stage_output_path.parent / STAGE_FILES["failure_context"]
            for artifact_path, output_key in (
                (product_path, "product"),
                (architecture_path, "architect"),
                (code_path, "code"),
                (test_path, "test"),
                (security_path, "security"),
                (reviewer_path, "reviewer"),
                (failure_context_path, "failure_context"),
            ):
                if not artifact_path.exists():
                    artifact_path.write_text(
                        outputs.get(output_key, "").rstrip() + "\n",
                        encoding="utf-8",
                    )
            return [
                sys.executable,
                "-m",
                "agentic_network.fixer_agent.run",
                "--mode",
                self.config.fixer_mode,
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--code-plan-file",
                str(code_path),
                "--test-plan-file",
                str(test_path),
                "--security-review-file",
                str(security_path),
                "--reviewer-report-file",
                str(reviewer_path),
                "--failure-context-file",
                str(failure_context_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        if stage == "final":
            product_path = stage_output_path.parent / STAGE_FILES["product"]
            architecture_path = stage_output_path.parent / self.config.architect_output
            code_path = _preferred_artifact_path(
                stage_output_path.parent, STAGE_FILES["code_revised"], STAGE_FILES["code"]
            )
            test_path = _preferred_artifact_path(
                stage_output_path.parent, STAGE_FILES["test_revised"], STAGE_FILES["test"]
            )
            security_path = _preferred_artifact_path(
                stage_output_path.parent,
                STAGE_FILES["security_revised"],
                self.config.security_output,
            )
            reviewer_path = stage_output_path.parent / self.config.reviewer_output
            fixer_path = stage_output_path.parent / self.config.fixer_output
            for artifact_path, output_key in (
                (product_path, "product"),
                (architecture_path, "architect"),
                (code_path, "code"),
                (test_path, "test"),
                (security_path, "security"),
                (reviewer_path, "reviewer"),
                (fixer_path, "fixer"),
            ):
                if not artifact_path.exists():
                    artifact_path.write_text(
                        outputs.get(output_key, "").rstrip() + "\n",
                        encoding="utf-8",
                    )
            return [
                sys.executable,
                "-m",
                "agentic_network.final_reviewer.run",
                "--mode",
                self.config.final_reviewer_mode,
                "--product-requirements-file",
                str(product_path),
                "--architecture-plan-file",
                str(architecture_path),
                "--code-plan-file",
                str(code_path),
                "--test-plan-file",
                str(test_path),
                "--security-review-file",
                str(security_path),
                "--reviewer-report-file",
                str(reviewer_path),
                "--fix-plan-file",
                str(fixer_path),
                "--output",
                str(stage_output_path),
                user_request,
            ]
        raise ValueError(f"Unsupported isolated stage: {stage}")

    def _isolated_backend_name(self, stage: str) -> str:
        if stage == "architect":
            return f"architect_{self.config.architect_mode}_subprocess"
        if stage == "security":
            return f"security_{self.config.security_mode}_subprocess"
        if stage == "reviewer":
            return f"reviewer_{self.config.reviewer_mode}_subprocess"
        if stage == "fixer":
            return f"fixer_{self.config.fixer_mode}_subprocess"
        if stage == "final":
            return f"final_{self.config.final_reviewer_mode}_subprocess"
        return f"{self._backend_for_stage(stage)}_subprocess"

    def _agent_for_stage(self, stage: str):
        model = self._model_for_stage(stage)
        if stage == "product":
            return ProductAgent(model)
        if stage == "architect":
            return ArchitectAgent(model)
        if stage == "code":
            return CodeAgent(model)
        if stage == "test":
            return TestEngineerAgent(model)
        if stage == "security":
            return SecurityAgent(model)
        if stage == "reviewer":
            return ReviewerAgent(model)
        if stage == "fixer":
            return FixerAgent(model)
        if stage == "final":
            return FinalReviewerAgent(model)
        raise ValueError(f"Unsupported stage: {stage}")

    def _model_for_stage(self, stage: str) -> BaseModelClient:
        if stage == "architect":
            return self._architect_model()
        if stage == "code" and not self.mock:
            return self._code_model()
        if stage == "test" and not self.mock:
            return self._test_model()
        if stage == "security" and not self.mock:
            return self._security_model()
        if stage == "reviewer" and not self.mock:
            return self._reviewer_model()
        if stage == "fixer" and not self.mock:
            return self._fixer_model()
        if stage == "final" and not self.mock:
            return self._final_model()
        backend = self._backend_for_stage(stage)
        cache_key = "product:qwen3" if stage == "product" and backend == "qwen3" else backend
        return self._model_for_backend(backend, cache_key=cache_key, stage=stage)

    def _backend_for_stage(self, stage: str) -> str:
        if self.mock:
            return "mock"
        if stage == "architect":
            if self.config.architect_mode == "deep":
                return "deepseek"
            return "qwen3"
        if stage == "security":
            if self.config.security_mode == "deep":
                return self.config.security_model_backend
            return "qwen3"
        if stage == "reviewer":
            if self.config.reviewer_mode == "deep":
                return self.config.reviewer_model_backend
            return "qwen3"
        if stage == "fixer":
            if self.config.fixer_mode == "deep":
                return self.config.fixer_model_backend
            return "qwen3"
        if stage == "final":
            if self.config.final_reviewer_mode == "deep":
                return self.config.final_reviewer_model_backend
            return "qwen3"
        env_name, attr_name = ROLE_BACKEND_CONFIG[stage]
        backend = str(getattr(self.config, attr_name)).strip().lower()
        if backend not in SUPPORTED_MODEL_BACKENDS:
            raise ValueError(f"Unsupported model backend for {env_name}: {backend}")
        return backend

    def _architect_model(self) -> BaseModelClient:
        if self.mock:
            return self._model_for_backend("mock", cache_key="mock", stage="architect")
        cache_key = f"architect:{self.config.architect_mode}"
        if cache_key not in self._models:
            self._models[cache_key] = ArchitectAgentRuntimeModel(
                self.config,
                repo_root=self.config.project_root,
            )
        return self._models[cache_key]

    def _code_model(self) -> BaseModelClient:
        cache_key = "code:v5"
        if cache_key not in self._models:
            self._models[cache_key] = CodeAgentRuntimeModel(self.config)
        return self._models[cache_key]

    def _test_model(self) -> BaseModelClient:
        cache_key = "test:v5"
        if cache_key not in self._models:
            self._models[cache_key] = TestEngineerRuntimeModel(self.config)
        return self._models[cache_key]

    def _security_model(self) -> BaseModelClient:
        cache_key = f"security:{self.config.security_mode}"
        if cache_key not in self._models:
            self._models[cache_key] = SecurityAgentRuntimeModel(
                self.config,
                mode=self.config.security_mode,
            )
        return self._models[cache_key]

    def _reviewer_model(self) -> BaseModelClient:
        cache_key = f"reviewer:{self.config.reviewer_mode}"
        if cache_key not in self._models:
            self._models[cache_key] = ReviewerAgentRuntimeModel(
                self.config,
                mode=self.config.reviewer_mode,
            )
        return self._models[cache_key]

    def _fixer_model(self) -> BaseModelClient:
        cache_key = f"fixer:{self.config.fixer_mode}"
        if cache_key not in self._models:
            self._models[cache_key] = FixerAgentRuntimeModel(
                self.config,
                mode=self.config.fixer_mode,
            )
        return self._models[cache_key]

    def _final_model(self) -> BaseModelClient:
        cache_key = f"final:{self.config.final_reviewer_mode}"
        if cache_key not in self._models:
            self._models[cache_key] = FinalReviewerRuntimeModel(
                self.config,
                mode=self.config.final_reviewer_mode,
            )
        return self._models[cache_key]

    def _model_for_backend(
        self,
        backend: str,
        *,
        cache_key: str | None = None,
        stage: str | None = None,
    ) -> BaseModelClient:
        cache_key = cache_key or backend
        if cache_key not in self._models:
            config = self._config_for_model(backend, stage)
            if backend == "mock":
                model: BaseModelClient = DeterministicMockModel(
                    "mock", self.mock_changes_required
                )
            elif backend == "deepseek":
                model = DeepSeekGGUFModel(config)
            elif backend == "deepseek_unsloth":
                model = DeepSeekUnslothModel(config)
            elif backend == "qwen_v5":
                model = QwenUnslothModel(config)
            elif backend == "qwen3":
                model = (
                    ProductAgentRuntimeModel(config)
                    if stage == "product"
                    else Qwen3Model(config)
                )
            else:
                raise ValueError(f"Unsupported model backend: {backend}")
            setattr(model, "backend_name", backend)
            self._models[cache_key] = model
        return self._models[cache_key]

    def _config_for_model(self, backend: str, stage: str | None) -> PipelineConfig:
        if stage == "product" and backend == "qwen3":
            return replace(
                self.config,
                max_new_tokens=self.config.product_max_new_tokens,
                temperature=self.config.product_temperature,
                top_p=self.config.product_top_p,
            )
        return self.config

    def _validate_model_backends(self) -> None:
        if self.mock:
            return
        for _stage, (env_name, attr_name) in ROLE_BACKEND_CONFIG.items():
            backend = str(getattr(self.config, attr_name)).strip().lower()
            if backend not in SUPPORTED_MODEL_BACKENDS:
                raise ValueError(f"Unsupported model backend for {env_name}: {backend}")

    @staticmethod
    def _normalize_stages(stages: Iterable[str] | None) -> list[str]:
        if stages is None:
            return list(DEFAULT_STAGES)
        normalized = [stage.strip().lower() for stage in stages if stage.strip()]
        invalid = sorted(set(normalized) - set(SUPPORTED_STAGES))
        if invalid:
            raise ValueError(f"Unsupported stages: {', '.join(invalid)}")
        return [stage for stage in SUPPORTED_STAGES if stage in normalized]

    @staticmethod
    def _stage_label(stage: str) -> str:
        labels = {
            "product": "Product Agent",
            "architect": "Architect Agent",
            "code": "Code Agent",
            "test": "Test Engineer Agent",
            "security": "Security Agent",
            "reviewer": "Reviewer Agent",
            "fixer": "Fixer Agent",
            "revision": "Revision Agent",
            "context": "Context Agent",
            "repository_intelligence": "Repository Intelligence Agent",
            "repository_context": "Repository Context Retrieval",
            "final": "Final Reviewer Agent",
            "execution": "Execution Agent",
            "patch_quality": "Patch Quality Agent",
            "patch_approval": "Patch Approval Agent",
            "patch_apply": "Patch Apply Agent",
            "test_runner": "Test Runner Agent",
            "self_healing": "Self Healing Agent",
            "merge_readiness": "Merge Readiness Agent",
            "memory": "Memory Agent",
            "human_approval": "Human Approval Agent",
            "knowledge": "Knowledge Agent",
            "handoff": "Handoff Bundle",
        }
        return labels[stage]




def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _prepare_apply_orchestration(
    selected_stages: tuple[str, ...],
    *,
    apply_requested: bool,
    approve_patches: bool,
    approval_token: str | None,
) -> ApplyOrchestration:
    errors: list[str] = []
    stages = list(selected_stages)
    if apply_requested:
        if not approve_patches:
            errors.append("approve_patches_flag_missing")
        if not (approval_token or "").strip():
            errors.append("approval_token_missing")
        if "patch_apply" in stages:
            self_healing_requested = "self_healing" in stages
            memory_requested = "memory" in stages
            stages = [
                stage
                for stage in stages
                if stage not in {"test_runner", "self_healing", "merge_readiness", "memory", "human_approval"}
            ]
            patch_apply_index = stages.index("patch_apply")
            dependencies = ["test_runner", "merge_readiness", "human_approval"]
            if self_healing_requested:
                dependencies.insert(1, "self_healing")
            if memory_requested:
                dependencies.insert(dependencies.index("human_approval"), "memory")
            for dependency in dependencies:
                stages.insert(patch_apply_index, dependency)
                patch_apply_index += 1
    return ApplyOrchestration(
        apply_requested=apply_requested,
        approve_patches_flag=approve_patches,
        approval_token_provided=bool((approval_token or "").strip()),
        selected_stages=tuple(stages),
        valid=not errors,
        errors=_dedupe(errors),
    )


def _apply_orchestration_summary_fields(orchestration: ApplyOrchestration) -> dict[str, object]:
    return {
        "apply_requested": orchestration.apply_requested,
        "approve_patches_flag": orchestration.approve_patches_flag,
        "approval_token_provided": orchestration.approval_token_provided,
        "apply_orchestration_valid": orchestration.valid,
        "apply_orchestration_errors": orchestration.errors,
    }


def build_context(outputs: dict[str, str]) -> str:
    ordered = [
        ("USER REQUEST", outputs.get("user")),
        ("CONTEXT", outputs.get("context")),
        ("REPOSITORY INTELLIGENCE", outputs.get("repository_intelligence")),
        ("REPOSITORY CONTEXT", outputs.get("repository_context")),
        ("PRODUCT REQUIREMENTS", outputs.get("product")),
        ("ARCHITECTURE", outputs.get("architect")),
        ("CODE", _preferred_output(outputs, "code")),
        ("TESTS", _preferred_output(outputs, "test")),
        ("SECURITY REVIEW", _preferred_output(outputs, "security")),
        ("STATIC SANITY CHECK FINDINGS", outputs.get("static_sanity")),
        ("REVIEWER", outputs.get("reviewer")),
        ("FAILURE CONTEXT", outputs.get("failure_context")),
        ("FIXES", outputs.get("fixer")),
        ("POST-FIX STATIC SANITY CHECK FINDINGS", outputs.get("post_fix_static_sanity")),
        ("REVISION SUMMARY", outputs.get("revision")),
        ("EXECUTION", outputs.get("execution")),
        ("PATCH APPROVAL", outputs.get("patch_approval")),
        ("PATCH APPLY", outputs.get("patch_apply")),
        ("TEST RUNNER", outputs.get("test_runner")),
        ("MERGE READINESS", outputs.get("merge_readiness")),
        ("HUMAN APPROVAL", outputs.get("human_approval")),
    ]
    return "\n\n".join(f"{title}\n{'=' * len(title)}\n{value}" for title, value in ordered if value)


def _compile_and_save_failure_context(
    *,
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    project_root: Path,
) -> str:
    context = compile_pipeline_failure_context(
        project_root=project_root,
        outputs=outputs,
        artifact_paths=artifacts.output_files,
    )
    json_path, markdown_path = write_failure_context_artifacts(artifacts.root, context)
    artifacts.output_files["failure_context_json"] = json_path
    artifacts.output_files["failure_context"] = markdown_path
    return render_failure_context_markdown(context)


def _preferred_output(outputs: dict[str, str], key: str) -> str | None:
    return outputs.get(f"{key}_revised") or outputs.get(key)


def _product_input(outputs: dict[str, str]) -> str:
    task = outputs.get("user", "").strip()
    context = outputs.get("context", "").strip()
    repository_context = outputs.get("repository_context", "").strip()
    if not context and not repository_context:
        return task
    supporting = "\n\n".join(value for value in (context, repository_context) if value)
    return (
        "SUPPORTING CONTEXT\n"
        "------------------\n"
        f"{supporting}\n\n"
        "USER TASK\n"
        "---------\n"
        f"{task}"
    )


def extract_status(output: str) -> str:
    lines = output.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == "APPROVAL STATUS":
            for status_line in lines[index + 1 :]:
                status = status_line.strip().upper()
                if not status:
                    continue
                if status == "APPROVED":
                    return "APPROVED"
                if status == "NEEDS FIXES":
                    return "CHANGES REQUIRED"
                break
        if stripped == "FINAL DECISION":
            for status_line in lines[index + 1 :]:
                status = status_line.strip().upper()
                if not status:
                    continue
                if status == "APPROVED":
                    return "APPROVED"
                if status == "REJECTED":
                    return "CHANGES REQUIRED"
                break
        if stripped.startswith("STATUS:"):
            value = stripped.split(":", 1)[1].strip()
            if value.startswith("CHANGES REQUIRED"):
                return "CHANGES REQUIRED"
            if value.startswith("APPROVED"):
                return "APPROVED"
        if stripped == "CHANGES REQUIRED":
            return "CHANGES REQUIRED"
        if stripped == "APPROVED":
            return "APPROVED"
    return "UNKNOWN"


def format_exception(exc: Exception) -> str:
    message = str(exc) or "<no message>"
    return f"{type(exc).__name__}: {message}"


def _preferred_artifact_path(run_dir: Path, revised_filename: str, original_filename: str) -> Path:
    revised_path = run_dir / revised_filename
    if revised_path.exists():
        return revised_path
    return run_dir / original_filename


def _post_fix_blocks_approval(outputs: dict[str, str]) -> bool:
    return has_blocking_static_sanity_findings(outputs.get("post_fix_static_sanity", ""))


def _post_fix_summary_fields(
    artifacts: RunArtifacts, outputs: dict[str, str], stages_run: list[str]
) -> dict[str, object]:
    if "fixer" not in stages_run:
        return {}
    post_fix_output = outputs.get("post_fix_static_sanity", "")
    return {
        "post_fix_static_sanity_file": artifacts.output_files.get("post_fix_static_sanity"),
        "post_fix_static_sanity_findings_count": count_static_sanity_findings(
            post_fix_output
        ),
    }


def _run_context_stage(
    *,
    task: str,
    knowledge_root: Path,
    memory_root: Path,
    run_dir: Path,
    stage_timings: list[dict[str, object]],
) -> ContextResult:
    started_at = _utc_now()
    started = perf_counter()
    result = build_context_briefing(
        task,
        knowledge_root,
        memory_root=memory_root,
        run_dir=run_dir,
    )
    ended = perf_counter()
    ended_at = _utc_now()
    stage_timings.append(
        {
            "stage": "context",
            "stage_name": "Context Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": len(task)
            + _knowledge_source_chars(knowledge_root)
            + _memory_source_chars(memory_root),
            "output_char_count": len(result.context_artifact),
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": False,
            "fixer_ran": False,
            "post_fix_sanity_ran": False,
        }
    )
    return result


def _knowledge_source_chars(knowledge_root: Path) -> int:
    if not knowledge_root.exists():
        return 0
    total = 0
    for path in knowledge_root.rglob("*.json"):
        if path.is_file():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _memory_source_chars(memory_root: Path) -> int:
    if not memory_root.exists():
        return 0
    total = 0
    for path in memory_root.glob("*.json"):
        if path.is_file():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _context_summary_fields(
    result: ContextResult | None,
    artifacts: RunArtifacts,
) -> dict[str, object]:
    if result is None:
        return {}
    return {
        "context_status": "VALID" if not result.validation_errors else "INVALID",
        "context_artifact": artifacts.output_files.get("context"),
        "context_patterns_found": result.matched_patterns,
        "context_lessons_found": result.matched_lessons,
        "context_runs_found": result.matched_runs,
        "context_validation_passed": not result.validation_errors,
        "context_validation_warnings": result.warnings,
        "context_validation_errors": result.validation_errors,
        **memory_retrieval_summary_fields(result.experience_context_result),
    }


def _run_repository_intelligence_stage(
    *,
    project_root: Path,
    run_dir: Path,
    stage_timings: list[dict[str, object]],
) -> RepositoryIntelligenceResult:
    started_at = _utc_now()
    started = perf_counter()
    result = build_repository_intelligence(
        project_root=_resolve_repository_scan_root(project_root),
        output_dir=run_dir / "repository_intelligence",
    )
    ended = perf_counter()
    ended_at = _utc_now()
    stage_timings.append(
        {
            "stage": "repository_intelligence",
            "stage_name": "Repository Intelligence Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": result.files_scanned,
            "output_char_count": _repository_intelligence_output_chars(result),
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": False,
            "fixer_ran": False,
            "post_fix_sanity_ran": False,
        }
    )
    return result


def _repository_intelligence_output_chars(result: RepositoryIntelligenceResult) -> int:
    total = 0
    for path_text in result.output_files.values():
        path = Path(path_text)
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _resolve_repository_scan_root(project_root: Path) -> Path:
    text = str(project_root).replace("\\", "/")
    if text.lower().endswith("/mnt/d/agenticengineeringnetwork"):
        return Path(__file__).resolve().parents[2]
    if project_root.exists():
        return project_root
    return project_root


def _repository_intelligence_brief(result: RepositoryIntelligenceResult) -> str:
    return "\n".join(
        [
            f"Repository intelligence indexed {result.files_scanned} files.",
            f"Functions: {result.functions}.",
            f"Classes: {result.classes}.",
            f"Routes: {result.routes}.",
            f"Tests: {result.tests}.",
            "Languages: " + ", ".join(result.languages_detected or ["None"]) + ".",
            f"Output directory: {result.output_dir}.",
        ]
    )


def _repository_intelligence_summary_fields(
    result: RepositoryIntelligenceResult | None,
) -> dict[str, object]:
    return repository_intelligence_summary_fields(result)


def _run_repository_context_stage(
    *,
    task: str,
    run_dir: Path,
    stage_timings: list[dict[str, object]],
) -> RepositoryContextResult:
    started_at = _utc_now()
    started = perf_counter()
    result = build_repository_context(task, run_dir)
    ended = perf_counter()
    ended_at = _utc_now()
    stage_timings.append(
        {
            "stage": "repository_context",
            "stage_name": "Repository Context Retrieval",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _repository_intelligence_output_chars_for_run(run_dir),
            "output_char_count": _repository_context_output_chars(result),
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": False,
            "fixer_ran": False,
            "post_fix_sanity_ran": False,
        }
    )
    return result


def _repository_intelligence_output_chars_for_run(run_dir: Path) -> int:
    total = 0
    intelligence_dir = run_dir / "repository_intelligence"
    if intelligence_dir.exists():
        for path in sorted(intelligence_dir.glob("*.json")):
            total += len(path.read_text(encoding="utf-8"))
    return total


def _repository_context_output_chars(result: RepositoryContextResult) -> int:
    total = 0
    for path_text in (result.context_artifact, result.compact_json_artifact):
        path = Path(path_text)
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _repository_context_summary_fields(
    result: RepositoryContextResult | None,
) -> dict[str, object]:
    return repository_context_summary_fields(result)


def _run_revision_stage(
    *,
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    stage_timings: list[dict[str, object]],
) -> RevisionResult:
    started_at = _utc_now()
    started = perf_counter()
    result = apply_revisions(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    stage_timings.append(
        {
            "stage": "revision",
            "stage_name": "Revision Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _revision_input_chars(artifacts.root),
            "output_char_count": len(result.revision_summary),
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": "static_sanity" in outputs,
            "fixer_ran": "fixer" in outputs,
            "post_fix_sanity_ran": "post_fix_static_sanity" in outputs,
        }
    )
    return result


def _revision_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "03_code.md",
        "04_tests.md",
        "05_security.md",
        "06_review.md",
        "07_fix_plan.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _revision_summary_fields(result: RevisionResult | None) -> dict[str, object]:
    if result is None:
        return {}
    return {
        "revision_status": "VALID" if result.validation_passed else "INVALID",
        "revision_validation_passed": result.validation_passed,
        "revision_validation_warnings": result.warnings,
        "revision_validation_errors": result.validation_errors,
        "revision_artifacts_generated": result.artifacts_generated,
    }


def _run_execution_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> ExecutionPlanResult:
    started_at = _utc_now()
    started = perf_counter()
    result = generate_execution_plan(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "execution",
            "stage_name": "Execution Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _execution_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _execution_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "24_experience_context.md",
        "03_code_revised.md",
        "04_tests_revised.md",
        "05_security_revised.md",
        "08_final_review.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    intelligence_dir = run_dir / "repository_intelligence"
    compact_context = (run_dir / "26_repository_context.md", run_dir / "26_repository_context.json")
    if any(path.exists() for path in compact_context):
        for path in compact_context:
            if path.exists():
                total += len(path.read_text(encoding="utf-8"))
    elif intelligence_dir.exists():
        for filename in ("routes.json", "call_graph.json", "dependency_graph.json"):
            path = intelligence_dir / filename
            if path.exists():
                total += len(path.read_text(encoding="utf-8"))
    return total


def _execution_summary_fields(result: ExecutionPlanResult | None) -> dict[str, object]:
    if result is None:
        return {}
    if result.refused:
        status = "REFUSED"
    elif result.validation_passed and result.patch_count == 0:
        status = "NO_APPLICABLE_TARGETS"
    else:
        status = "VALID" if result.validation_passed else "INVALID"
    return {
        "execution_status": status,
        "execution_artifact": result.artifact_path,
        "execution_patch_count": result.patch_count,
        "execution_source_aware": result.source_aware,
        "execution_applicable_patch_count": result.applicable_patch_count,
        "execution_no_target_reason": result.no_target_reason,
        "execution_candidate_files": result.candidate_files or [],
        "execution_synthesizer_used": result.synthesizer_used,
        "execution_synthesizer_strategy": result.synthesizer_strategy,
        "execution_synthesizer_fallback_reason": result.synthesizer_fallback_reason,
        "execution_behavior_synthesized": result.behavior_synthesized,
        "execution_behavior_strategy": result.behavior_strategy,
        "execution_real_implementation": result.real_implementation,
        "execution_memory_used": result.memory_used,
        "execution_memory_patterns_used": result.memory_patterns_used or [],
        "execution_repository_intelligence_used": result.repository_intelligence_used,
        "execution_route_detected": result.route_detected,
        "execution_dependency_path_found": result.dependency_path_found,
        "execution_repository_context_used": result.repository_context_used,
        "execution_repository_context_files": result.repository_context_files,
        "execution_repository_context_routes": result.repository_context_routes,
        "execution_repository_context_functions": result.repository_context_functions,
        "execution_repository_context_tests": result.repository_context_tests,
        "execution_repository_context_chars": result.repository_context_chars,
        "execution_target_selection_used": result.target_selection_used,
        "execution_selected_targets": result.selected_targets or [],
        "execution_rejected_targets": result.rejected_targets or [],
        "execution_target_classes": result.target_classes or {},
        "execution_target_selection_reasons": result.target_selection_reasons or {},
        "execution_target_selection_confidence": result.target_selection_confidence,
        "execution_multifile_plan_used": result.multifile_plan_used,
        "execution_multifile_plan_type": result.multifile_plan_type,
        "execution_multifile_selected_files": result.multifile_selected_files or [],
        "execution_multifile_file_roles": result.multifile_file_roles or {},
        "execution_multifile_implementation_order": result.multifile_implementation_order or [],
        "execution_multifile_missing_layers": result.multifile_missing_layers or [],
        "execution_multifile_confidence": result.multifile_confidence,
        "execution_multifile_rationale": result.multifile_rationale or [],
        "execution_layer_creation_used": result.layer_creation_used,
        "execution_layer_proposed_files": result.layer_proposed_files or [],
        "execution_layer_rejected_layers": result.layer_rejected_layers or {},
        "execution_layer_creation_rationale": result.layer_creation_rationale or [],
        "execution_layer_creation_validation_passed": not (result.layer_creation_validation_errors or []),
        "execution_layer_creation_validation_errors": result.layer_creation_validation_errors or [],
        "execution_layer_creation_confidence": result.layer_creation_confidence,
        "execution_validation_passed": result.validation_passed,
        "execution_validation_errors": result.validation_errors,
        "execution_validation_warnings": result.warnings,
    }


def _run_patch_quality_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> PatchQualityResult:
    started_at = _utc_now()
    started = perf_counter()
    result = evaluate_patch_quality(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "patch_quality",
            "stage_name": "Patch Quality Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _patch_quality_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _patch_quality_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "11_execution_plan.md",
        "03_code_revised.md",
        "04_tests_revised.md",
        "05_security_revised.md",
        "08_final_review.md",
        "24_experience_context.md",
        "summary.json",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        for path in sorted(patches_dir.glob("*.diff")):
            total += len(path.read_text(encoding="utf-8"))
    return total


def _patch_quality_summary_fields(result: PatchQualityResult | None) -> dict[str, object]:
    return patch_quality_summary_fields(result)


def _run_patch_approval_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> PatchApprovalResult:
    started_at = _utc_now()
    started = perf_counter()
    result = approve_patches(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "patch_approval",
            "stage_name": "Patch Approval Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _patch_approval_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _patch_approval_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in ("11_execution_plan.md", "08_final_review.md"):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        for path in sorted(patches_dir.glob("*.diff")):
            total += len(path.read_text(encoding="utf-8"))
    return total


def _patch_approval_summary_fields(result: PatchApprovalResult | None) -> dict[str, object]:
    if result is None:
        return {}
    return {
        "patch_approval_status": "VALID" if result.validation_passed else "INVALID",
        "patch_approval_decision": result.decision,
        "patch_approval_validation_passed": result.validation_passed,
        "patch_approval_validation_errors": result.validation_errors,
        "patch_approval_validation_warnings": result.warnings,
    }



def _save_patch_apply_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    apply_orchestration: ApplyOrchestration,
    merge_readiness_result: MergeReadinessResult | None = None,
    human_approval_result: HumanApprovalResult | None = None,
    self_healing_result: SelfHealingResult | None = None,
    memory_result: MemoryResult | None = None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_self_healing_summary_fields(self_healing_result),
        **_merge_readiness_summary_fields(merge_readiness_result),
        **_memory_summary_fields(memory_result),
        **_human_approval_summary_fields(human_approval_result),
        **_apply_orchestration_summary_fields(apply_orchestration),
    }
    artifacts.save_summary(summary)


def _run_patch_apply_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
    approve_patches: bool,
    dry_run: bool,
) -> PatchApplyResult:
    started_at = _utc_now()
    started = perf_counter()
    result = apply_approved_patches(
        artifacts.root,
        approve_patches=approve_patches,
        dry_run=dry_run,
    )
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "patch_apply",
            "stage_name": "Patch Apply Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _patch_apply_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _patch_apply_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in ("summary.json", "12_patch_approval.md"):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        for path in sorted(patches_dir.glob("*.diff")):
            total += len(path.read_text(encoding="utf-8"))
    return total


def _patch_apply_summary_fields(result: PatchApplyResult | None) -> dict[str, object]:
    return patch_apply_summary_fields(result)



def _save_test_runner_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
    }
    artifacts.save_summary(summary)


def _run_test_runner_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
    run_tests: bool,
    timeout_seconds: int,
) -> TestRunnerResult:
    started_at = _utc_now()
    started = perf_counter()
    result = run_tests_for_run(
        artifacts.root,
        run_tests=run_tests,
        timeout_seconds=timeout_seconds,
    )
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "test_runner",
            "stage_name": "Test Runner Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _test_runner_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _test_runner_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in ("summary.json", "13_patch_apply.md"):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _test_runner_summary_fields(result: TestRunnerResult | None) -> dict[str, object]:
    return test_runner_summary_fields(result)


def _save_self_healing_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
    test_runner_result: TestRunnerResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
        **_test_runner_summary_fields(test_runner_result),
    }
    artifacts.save_summary(summary)


def _run_self_healing_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> SelfHealingResult:
    started_at = _utc_now()
    started = perf_counter()
    result = run_self_healing(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.self_healing_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "self_healing",
            "stage_name": "Self Healing Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _self_healing_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _self_healing_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "summary.json",
        "11_execution_plan.md",
        "12_patch_approval.md",
        "13_patch_apply.md",
        "14_test_run.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        for path in sorted(patches_dir.glob("*.diff")):
            total += len(path.read_text(encoding="utf-8"))
    return total


def _self_healing_summary_fields(result: SelfHealingResult | None) -> dict[str, object]:
    return self_healing_summary_fields(result)


def _save_autonomous_loop_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
    test_runner_result: TestRunnerResult | None,
    self_healing_result: SelfHealingResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
        **_test_runner_summary_fields(test_runner_result),
        **_self_healing_summary_fields(self_healing_result),
    }
    artifacts.save_summary(summary)


def _run_autonomous_loop_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
    approve_patches: bool,
    approval_token: str | None,
    run_tests: bool,
    timeout_seconds: int,
) -> AutonomousLoopResult:
    started_at = _utc_now()
    started = perf_counter()
    result = run_autonomous_engineering_loop(
        artifacts.root,
        max_attempts=3,
        approve_patches=approve_patches,
        approval_token=approval_token,
        run_tests=run_tests,
        timeout_seconds=timeout_seconds,
    )
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "autonomous_loop",
            "stage_name": "Autonomous Engineering Loop",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _autonomous_loop_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _autonomous_loop_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "summary.json",
        "13_patch_apply.md",
        "14_test_run.md",
        "17_failure_analysis.md",
        "18_root_cause.md",
        "21_self_healing.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _autonomous_loop_summary_fields(result: AutonomousLoopResult | None) -> dict[str, object]:
    return autonomous_loop_summary_fields(result)



def _save_merge_readiness_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
    test_runner_result: TestRunnerResult | None,
    self_healing_result: SelfHealingResult | None,
    autonomous_loop_result: AutonomousLoopResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
        **_test_runner_summary_fields(test_runner_result),
        **_self_healing_summary_fields(self_healing_result),
        **_autonomous_loop_summary_fields(autonomous_loop_result),
    }
    artifacts.save_summary(summary)


def _run_merge_readiness_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> MergeReadinessResult:
    started_at = _utc_now()
    started = perf_counter()
    result = evaluate_merge_readiness(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "merge_readiness",
            "stage_name": "Merge Readiness Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _merge_readiness_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _merge_readiness_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "summary.json",
        "12_patch_approval.md",
        "13_patch_apply.md",
        "14_test_run.md",
        "08_final_review.md",
        "11_execution_plan.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _merge_readiness_summary_fields(result: MergeReadinessResult | None) -> dict[str, object]:
    return merge_readiness_summary_fields(result)


def _save_memory_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
    test_runner_result: TestRunnerResult | None,
    self_healing_result: SelfHealingResult | None,
    autonomous_loop_result: AutonomousLoopResult | None,
    merge_readiness_result: MergeReadinessResult | None,
    memory_result: MemoryResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
        **_test_runner_summary_fields(test_runner_result),
        **_self_healing_summary_fields(self_healing_result),
        **_autonomous_loop_summary_fields(autonomous_loop_result),
        **_merge_readiness_summary_fields(merge_readiness_result),
        **_memory_summary_fields(memory_result),
    }
    artifacts.save_summary(summary)


def _run_memory_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> MemoryResult:
    started_at = _utc_now()
    started = perf_counter()
    result = record_engineering_experience(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    stage_timings.append(
        {
            "stage": "memory",
            "stage_name": "Memory Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _memory_input_chars(artifacts.root),
            "output_char_count": _memory_output_chars(result),
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _memory_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "summary.json",
        "17_failure_analysis.md",
        "18_root_cause.md",
        "21_self_healing.md",
        "27_autonomous_loop.md",
        "15_merge_readiness.md",
        "12_patch_approval.md",
        "13_patch_apply.md",
        "14_test_run.md",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _memory_output_chars(result: MemoryResult) -> int:
    total = 0
    for artifact in result.artifacts:
        path = Path(artifact)
        if path.exists() and path.is_file():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _memory_summary_fields(result: MemoryResult | None) -> dict[str, object]:
    return memory_summary_fields(result)



def _save_human_approval_prerequisite_summary(
    *,
    artifacts: RunArtifacts,
    task: str,
    stages_run: list[str],
    reviewer_status: str,
    final_status: str,
    stage_timings: list[dict[str, object]],
    outputs: dict[str, str],
    patch_approval_result: PatchApprovalResult | None,
    patch_apply_result: PatchApplyResult | None,
    test_runner_result: TestRunnerResult | None,
    self_healing_result: SelfHealingResult | None,
    autonomous_loop_result: AutonomousLoopResult | None,
    merge_readiness_result: MergeReadinessResult | None,
) -> None:
    summary = {
        "timestamp": artifacts.timestamp,
        "task": task,
        "stages_run": stages_run,
        "reviewer_status": reviewer_status,
        "final_status": final_status,
        "stage_timings": stage_timings,
        **_final_summary_fields(artifacts, outputs, stage_timings),
        **_patch_approval_summary_fields(patch_approval_result),
        **_patch_apply_summary_fields(patch_apply_result),
        **_test_runner_summary_fields(test_runner_result),
        **_self_healing_summary_fields(self_healing_result),
        **_autonomous_loop_summary_fields(autonomous_loop_result),
        **_merge_readiness_summary_fields(merge_readiness_result),
    }
    artifacts.save_summary(summary)


def _run_human_approval_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
    approve_apply: bool,
    approval_token: str | None,
) -> HumanApprovalResult:
    started_at = _utc_now()
    started = perf_counter()
    result = authorize_apply(
        artifacts.root,
        approval_token=approval_token,
        approve_apply=approve_apply,
    )
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "human_approval",
            "stage_name": "Human Approval Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _human_approval_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": (artifacts.root / artifacts.stage_files["static_sanity"]).exists(),
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _human_approval_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in ("summary.json", "12_patch_approval.md", "15_merge_readiness.md"):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _human_approval_summary_fields(result: HumanApprovalResult | None) -> dict[str, object]:
    return human_approval_summary_fields(result)


def _run_knowledge_stage(
    *,
    artifacts: RunArtifacts,
    stage_timings: list[dict[str, object]],
) -> KnowledgeCaptureResult:
    started_at = _utc_now()
    started = perf_counter()
    result = capture_knowledge(artifacts.root)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "knowledge",
            "stage_name": "Knowledge Agent",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _knowledge_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": True,
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _knowledge_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "01_product_requirements.md",
        "02_architecture_plan.md",
        "03_code.md",
        "04_tests.md",
        "05_security.md",
        "06_review.md",
        "07_fix_plan.md",
        "08_final_review.md",
        "17_failure_analysis.md",
        "18_root_cause.md",
        "21_self_healing.md",
        "27_autonomous_loop.md",
        "09_handoff_bundle.md",
        "summary.json",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _knowledge_summary_fields(result: KnowledgeCaptureResult) -> dict[str, object]:
    return {
        "knowledge_status": "VALID" if not result.validation_errors else "INVALID",
        "knowledge_artifact": result.artifact_path,
        "knowledge_patterns_found": result.reusable_patterns,
        "knowledge_lessons_found": result.lessons,
        "knowledge_future_reuse_score": result.future_reuse_score,
        "knowledge_validation_passed": not result.validation_errors,
        "knowledge_validation_warnings": result.warnings,
        "knowledge_validation_errors": result.validation_errors,
    }


def _run_handoff_stage(
    *,
    artifacts: RunArtifacts,
    task: str,
    stage_timings: list[dict[str, object]],
) -> HandoffBundleResult:
    started_at = _utc_now()
    started = perf_counter()
    result = build_handoff_bundle(artifacts.root, task=task)
    ended = perf_counter()
    ended_at = _utc_now()
    output_chars = len(Path(result.artifact_path).read_text(encoding="utf-8"))
    stage_timings.append(
        {
            "stage": "handoff",
            "stage_name": "Handoff Bundle",
            "model_backend": "none",
            "started_at": _format_utc(started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(ended - started, 3),
            "input_char_count": _handoff_input_chars(artifacts.root),
            "output_char_count": output_chars,
            "gpu_config": {},
            "device_info": {},
            "static_sanity_ran": True,
            "fixer_ran": (artifacts.root / artifacts.stage_files["fixer"]).exists(),
            "post_fix_sanity_ran": (
                artifacts.root / artifacts.stage_files["post_fix_static_sanity"]
            ).exists(),
        }
    )
    return result


def _handoff_input_chars(run_dir: Path) -> int:
    total = 0
    for filename in (
        "01_product_requirements.md",
        "02_architecture_plan.md",
        "03_code.md",
        "04_tests.md",
        "05_security.md",
        "06_review.md",
        "07_fix_plan.md",
        "08_final_review.md",
        "10_knowledge_capture.md",
        "17_failure_analysis.md",
        "18_root_cause.md",
        "21_self_healing.md",
        "27_autonomous_loop.md",
        "summary.json",
    ):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _handoff_summary_fields(result: HandoffBundleResult) -> dict[str, object]:
    return {
        "handoff_status": "VALID" if not result.validation_errors else "INVALID",
        "handoff_artifact": result.artifact_path,
        "handoff_included_artifacts": result.included_artifacts,
        "handoff_missing_artifacts": result.missing_artifacts,
        "handoff_validation_passed": not result.validation_errors,
        "handoff_validation_warnings": result.warnings,
        "handoff_validation_errors": result.validation_errors,
    }


def _model_routing_summary_fields(routing_plan: object) -> dict[str, object]:
    to_dict = getattr(routing_plan, "to_dict", None)
    payload = to_dict() if callable(to_dict) else {}
    return {
        "execution_mode": payload.get("mode", "FAST"),
        "model_routing_status": payload.get("status", "UNKNOWN"),
        "model_routing_vram_policy": payload.get("vram_policy", "SEQUENTIAL"),
        "model_routing_sequential_required": True,
        "model_routing_decisions": payload.get("decisions", []),
        "model_routing_artifacts": payload.get("artifacts", []),
        "model_routing_warnings": payload.get("warnings", []),
        "model_routing_errors": payload.get("errors", []),
    }


def _runtime_engine_summary_fields() -> dict[str, object]:
    metrics = get_runtime_metrics()
    return {
        "runtime_engine_status": "READY",
        "runtime_engine_vram_policy": "SEQUENTIAL",
        "runtime_engine_max_loaded_models": 1,
        "runtime_engine_active_models": metrics.get("active_models", 0),
        "runtime_engine_parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "runtime_engine_peak_vram_mb": metrics.get("peak_vram_mb", 0),
    }


def _fixer_summary_fields(
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    stage_timings: list[dict[str, object]],
) -> dict[str, object]:
    fixer_output = outputs.get("fixer", "")
    if not fixer_output or fixer_output.startswith("SKIPPED"):
        return {}
    sidecar_fields = _fixer_validation_sidecar_fields(artifacts)
    validation_fields: dict[str, object]
    if sidecar_fields:
        validation_fields = sidecar_fields
    else:
        parsed_sections = parse_fixer_agent_sections(fixer_output)
        warnings, validation_errors = validate_fixer_agent_response(
            fix_plan_output=fixer_output,
            parsed_sections=parsed_sections,
        )
        ready_for_rereview = str(parsed_sections.get("ready_for_rereview", ""))
        validation_fields = {
            "fixer_status": "VALID" if not validation_errors else "INVALID",
            "fixer_validation_passed": not validation_errors,
            "fixer_validation_warnings": warnings,
            "fixer_validation_errors": validation_errors,
            "fixer_fallback_used": any(
                warning.startswith("model_output_replaced_after_validation_errors")
                for warning in warnings
            ),
            "fixer_ready_for_rereview": ready_for_rereview,
        }
    return {
        "fixer_model": _stage_timing_backend(stage_timings, "fixer"),
        "fixer_input_chars": len(build_context({**outputs, "fixer": ""})),
        "fixer_output_chars": len(fixer_output),
        **validation_fields,
    }


def _fixer_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("fixer_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    validation_errors = list(payload.get("validation_errors", []))
    return {
        "fixer_status": "VALID" if not validation_errors else "INVALID",
        "fixer_validation_passed": bool(payload.get("validation_passed", False)),
        "fixer_validation_warnings": list(payload.get("warnings", [])),
        "fixer_validation_errors": validation_errors,
        "fixer_fallback_used": bool(payload.get("fallback_used", False)),
        "fixer_ready_for_rereview": str(payload.get("ready_for_rereview", "")),
    }


def _final_summary_fields(
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    stage_timings: list[dict[str, object]],
) -> dict[str, object]:
    final_output = outputs.get("final", "")
    if not final_output:
        return {}
    sidecar_fields = _final_validation_sidecar_fields(artifacts)
    validation_fields: dict[str, object]
    if sidecar_fields:
        validation_fields = sidecar_fields
    else:
        parsed_sections = parse_final_reviewer_sections(final_output)
        warnings, validation_errors = validate_final_reviewer_response(
            final_review_output=final_output,
            parsed_sections=parsed_sections,
        )
        final_decision = str(parsed_sections.get("final_decision", ""))
        validation_fields = {
            "final_validation_passed": not validation_errors,
            "final_validation_warnings": warnings,
            "final_validation_errors": validation_errors,
            "final_fallback_used": any(
                warning.startswith("model_output_replaced_after_validation_errors")
                for warning in warnings
            ),
            "final_decision": final_decision,
        }
    return {
        "final_model": _stage_timing_backend(stage_timings, "final"),
        "final_input_chars": len(build_context({**outputs, "final": ""})),
        "final_output_chars": len(final_output),
        **validation_fields,
    }


def _final_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("final_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    return {
        "final_validation_passed": bool(payload.get("validation_passed", False)),
        "final_validation_warnings": list(payload.get("warnings", [])),
        "final_validation_errors": list(payload.get("validation_errors", [])),
        "final_fallback_used": bool(payload.get("fallback_used", False)),
        "final_decision": str(payload.get("final_decision", "")),
    }


def _code_summary_fields(artifacts: RunArtifacts, outputs: dict[str, str]) -> dict[str, object]:
    code_output = outputs.get("code", "")
    if not code_output:
        return {}
    sidecar_fields = _code_validation_sidecar_fields(artifacts)
    if sidecar_fields:
        return sidecar_fields
    parsed_sections = parse_code_agent_sections(code_output)
    warnings, validation_errors = validate_code_agent_response(
        generated_code_plan=code_output,
        parsed_sections=parsed_sections,
        architecture_plan=outputs.get("architect", ""),
    )
    return {
        "code_validation_passed": not validation_errors,
        "code_validation_warnings": warnings,
        "code_validation_errors": validation_errors,
    }


def _code_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("code_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    return {
        "code_validation_passed": bool(payload.get("validation_passed", False)),
        "code_validation_warnings": list(payload.get("warnings", [])),
        "code_validation_errors": list(payload.get("validation_errors", [])),
    }


def _test_summary_fields(artifacts: RunArtifacts, outputs: dict[str, str]) -> dict[str, object]:
    test_output = outputs.get("test", "")
    if not test_output:
        return {}
    sidecar_fields = _test_validation_sidecar_fields(artifacts)
    if sidecar_fields:
        return sidecar_fields
    parsed_sections = parse_test_engineer_sections(test_output)
    warnings, validation_errors = validate_test_engineer_response(
        generated_test_plan=test_output,
        parsed_sections=parsed_sections,
    )
    return {
        "test_engineer_status": "VALID" if not validation_errors else "INVALID",
        "test_validation_passed": not validation_errors,
        "test_validation_warnings": warnings,
        "test_validation_errors": validation_errors,
        "test_fallback_used": any(
            warning.startswith("model_output_replaced_after_validation_errors")
            for warning in warnings
        ),
    }


def _test_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("test_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    validation_errors = list(payload.get("validation_errors", []))
    return {
        "test_engineer_status": "VALID" if not validation_errors else "INVALID",
        "test_validation_passed": bool(payload.get("validation_passed", False)),
        "test_validation_warnings": list(payload.get("warnings", [])),
        "test_validation_errors": validation_errors,
        "test_fallback_used": bool(payload.get("fallback_used", False)),
    }


def _failure_context_summary_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("failure_context_json")
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    test_validity = payload.get("test_validity")
    if not isinstance(test_validity, dict):
        return {}
    return {
        "test_validity_status": test_validity.get("status", ""),
        "test_validity_classification": test_validity.get("classification", ""),
        "test_validity_confidence": test_validity.get("confidence"),
        "test_validity_reasons": list(test_validity.get("reasons", [])),
        "test_validity_recommended_next_action": test_validity.get("recommended_next_action", ""),
        "test_validity_fix_policy": test_validity.get("fix_policy", {}),
    }


def _security_summary_fields(
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    stage_timings: list[dict[str, object]],
) -> dict[str, object]:
    security_output = outputs.get("security", "")
    if not security_output:
        return {}
    sidecar_fields = _security_validation_sidecar_fields(artifacts)
    validation_fields: dict[str, object]
    if sidecar_fields:
        validation_fields = sidecar_fields
    else:
        parsed_sections = parse_security_agent_sections(security_output)
        warnings, validation_errors = validate_security_agent_response(
            generated_security_review=security_output,
            parsed_sections=parsed_sections,
        )
        validation_fields = {
            "security_status": "VALID" if not validation_errors else "INVALID",
            "security_validation_passed": not validation_errors,
            "security_validation_warnings": warnings,
            "security_validation_errors": validation_errors,
            "security_fallback_used": any(
                warning.startswith("model_output_replaced_after_validation_errors")
                for warning in warnings
            ),
        }
    return {
        "security_model": _stage_timing_backend(stage_timings, "security"),
        "security_input_chars": len(build_context({**outputs, "security": ""})),
        "security_output_chars": len(security_output),
        **validation_fields,
    }


def _security_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("security_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    validation_errors = list(payload.get("validation_errors", []))
    return {
        "security_status": "VALID" if not validation_errors else "INVALID",
        "security_validation_passed": bool(payload.get("validation_passed", False)),
        "security_validation_warnings": list(payload.get("warnings", [])),
        "security_validation_errors": validation_errors,
        "security_fallback_used": bool(payload.get("fallback_used", False)),
    }


def _reviewer_summary_fields(
    artifacts: RunArtifacts,
    outputs: dict[str, str],
    stage_timings: list[dict[str, object]],
) -> dict[str, object]:
    reviewer_output = outputs.get("reviewer", "")
    if not reviewer_output:
        return {}
    sidecar_fields = _reviewer_validation_sidecar_fields(artifacts)
    validation_fields: dict[str, object]
    if sidecar_fields:
        validation_fields = sidecar_fields
    else:
        parsed_sections = parse_reviewer_agent_sections(reviewer_output)
        warnings, validation_errors = validate_reviewer_agent_response(
            review_output=reviewer_output,
            parsed_sections=parsed_sections,
        )
        approval_status = str(parsed_sections.get("approval_status", ""))
        validation_fields = {
            "reviewer_validation_passed": not validation_errors,
            "reviewer_validation_warnings": warnings,
            "reviewer_validation_errors": validation_errors,
            "reviewer_fallback_used": any(
                warning.startswith("model_output_replaced_after_validation_errors")
                for warning in warnings
            ),
            "reviewer_approval_status": approval_status,
        }
    return {
        "reviewer_model": _stage_timing_backend(stage_timings, "reviewer"),
        "reviewer_input_chars": len(build_context({**outputs, "reviewer": ""})),
        "reviewer_output_chars": len(reviewer_output),
        **validation_fields,
    }


def _reviewer_validation_sidecar_fields(artifacts: RunArtifacts) -> dict[str, object]:
    path_value = artifacts.output_files.get("reviewer_validation")
    if not path_value:
        return {}
    validation_path = Path(path_value)
    if not validation_path.exists():
        return {}
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    return {
        "reviewer_validation_passed": bool(payload.get("validation_passed", False)),
        "reviewer_validation_warnings": list(payload.get("warnings", [])),
        "reviewer_validation_errors": list(payload.get("validation_errors", [])),
        "reviewer_fallback_used": bool(payload.get("fallback_used", False)),
        "reviewer_approval_status": str(payload.get("approval_status", "")),
    }


def _stage_timing_backend(stage_timings: list[dict[str, object]], stage: str) -> str:
    for record in reversed(stage_timings):
        if record.get("stage") == stage:
            return str(record.get("model_backend", ""))
    return ""


def print_timing_table(stage_timings: list[dict[str, object]]) -> None:
    """Print a compact timing table for the completed run."""

    if not stage_timings:
        return

    headers = (
        "Stage",
        "Model",
        "Seconds",
        "Input chars",
        "Output chars",
        "Sanity",
        "Fixer",
        "Post-fix",
    )
    rows = [
        (
            str(record["stage_name"]),
            str(record["model_backend"]),
            f"{float(record['duration_seconds']):.3f}",
            str(record["input_char_count"]),
            str(record["output_char_count"]),
            _yes_no(bool(record["static_sanity_ran"])),
            _yes_no(bool(record["fixer_ran"])),
            _yes_no(bool(record["post_fix_sanity_ran"])),
        )
        for record in stage_timings
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("\nTiming table")
    print(_format_timing_row(headers, widths))
    print(_format_timing_row(tuple("-" * width for width in widths), widths))
    for row in rows:
        print(_format_timing_row(row, widths))


def _format_timing_row(values: tuple[str, ...], widths: list[int]) -> str:
    return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))


def _set_timing_flag(
    stage_timings: list[dict[str, object]], stage: str, flag: str, value: bool
) -> None:
    for record in reversed(stage_timings):
        if record.get("stage") == stage:
            record[flag] = value
            return


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _model_backend_name(model: BaseModelClient) -> str:
    backend = getattr(model, "backend_name", "")
    if backend:
        return str(backend)
    name = getattr(model, "name", "")
    if name:
        return f"{type(model).__name__}({name})"
    return type(model).__name__


def _model_gpu_config(model: BaseModelClient) -> dict[str, object]:
    return _gpu_config_from_diagnostics(_model_diagnostics(model))


def _gpu_config_from_diagnostics(diagnostics: dict[str, object]) -> dict[str, object]:
    return {
        key: diagnostics[key]
        for key in ("gpu_layers", "main_gpu")
        if key in diagnostics and diagnostics[key] is not None
    }


def _model_device_info(model: BaseModelClient) -> dict[str, object]:
    return _device_info_from_diagnostics(_model_diagnostics(model))


def _device_info_from_diagnostics(diagnostics: dict[str, object]) -> dict[str, object]:
    return {
        key: diagnostics[key]
        for key in (
            "backend_name",
            "loaded_backend_type",
            "model_path",
            "adapter_path",
            "device_mode",
            "device",
            "cuda_available",
            "load_in_4bit",
            "max_seq_length",
            "stage_isolation",
            "stdout_log",
            "stderr_log",
        )
        if key in diagnostics
    }


def _model_diagnostics(model: BaseModelClient) -> dict[str, object]:
    diagnostics = getattr(model, "diagnostics", None)
    if diagnostics is None:
        return {}
    return dict(diagnostics())


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _isolated_subprocess_env(project_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    temp_root = project_root / "tests" / ".tmp" / "temp"
    hf_cache = project_root / "data" / "tool-caches" / "huggingface"
    torch_cache = project_root / "data" / "tool-caches" / "torch"
    for path in (temp_root, hf_cache, torch_cache):
        path.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "TMPDIR": str(temp_root),
            "TMP": str(temp_root),
            "TEMP": str(temp_root),
            "HF_HOME": str(hf_cache),
            "TRANSFORMERS_CACHE": str(hf_cache),
            "TORCH_HOME": str(torch_cache),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def _stage_runtime_model_is_patched(stage: str) -> bool:
    expected_modules = {
        "product": "agentic_network.product_agent.runtime",
        "architect": "agentic_network.architect_agent.runtime",
        "code": "agentic_network.code_agent.runtime",
        "test": "agentic_network.test_engineer.runtime",
        "security": "agentic_network.security_agent.runtime",
        "reviewer": "agentic_network.reviewer_agent.runtime",
        "fixer": "agentic_network.fixer_agent.runtime",
        "final": "agentic_network.final_reviewer.runtime",
    }
    runtime_classes = {
        "product": ProductAgentRuntimeModel,
        "architect": ArchitectAgentRuntimeModel,
        "code": CodeAgentRuntimeModel,
        "test": TestEngineerRuntimeModel,
        "security": SecurityAgentRuntimeModel,
        "reviewer": ReviewerAgentRuntimeModel,
        "fixer": FixerAgentRuntimeModel,
        "final": FinalReviewerRuntimeModel,
    }
    runtime_class = runtime_classes.get(stage)
    expected_module = expected_modules.get(stage)
    return runtime_class is not None and expected_module is not None and runtime_class.__module__ != expected_module
