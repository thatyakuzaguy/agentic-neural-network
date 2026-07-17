import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_network.config import PipelineConfig
from agentic_network.context_agent.runtime import parse_context_sections
from agentic_network.execution_agent.runtime import parse_execution_plan_sections
from agentic_network.architect_agent.runtime import parse_architect_agent_sections
from agentic_network.code_agent.runtime import parse_code_agent_sections
from agentic_network.final_reviewer.runtime import parse_final_reviewer_sections
from agentic_network.fixer_agent.runtime import parse_fixer_agent_sections
from agentic_network.knowledge_agent.runtime import parse_knowledge_capture_sections
from agentic_network.patch_approval_agent.runtime import parse_patch_approval_sections
from agentic_network.patch_apply_agent.runtime import PatchApplyResult
from agentic_network.pipeline.runner import PipelineRunner
from agentic_network.revision_agent.runtime import parse_revision_sections
from agentic_network.reviewer_agent.runtime import parse_reviewer_agent_sections
from agentic_network.security_agent.runtime import parse_security_agent_sections
from agentic_network.test_engineer.runtime import parse_test_engineer_sections

ROLE_BACKEND_ENV_VARS = (
    "PRODUCT_MODEL_BACKEND",
    "ARCHITECT_MODEL_BACKEND",
    "CODE_MODEL_BACKEND",
    "TEST_MODEL_BACKEND",
    "SECURITY_MODEL_BACKEND",
    "REVIEWER_MODEL_BACKEND",
    "FIXER_MODEL_BACKEND",
    "FINAL_REVIEWER_MODEL_BACKEND",
)


@pytest.fixture(autouse=True)
def _allow_tmp_pipeline_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", "/mnt/c,/mnt/d,/mnt/e")
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "")


def _config(tmp_path: Path, *, stage_isolation: str = "inprocess") -> PipelineConfig:
    return PipelineConfig(
        deepseek_gguf_path=None,
        qwen_base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        qwen_adapter_path=Path("training/adapters/qwen-7b-python-expert-v5"),
        output_dir=tmp_path / "runs",
        max_new_tokens=128,
        temperature=0.2,
        top_p=0.85,
        context_length=2048,
        use_4bit=True,
        stage_isolation=stage_isolation,
    )


class _FakeModel:
    def __init__(self, _config: PipelineConfig) -> None:
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "fake model output"

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        return self.generate_text("\n".join(message["content"] for message in messages))


class _FakeProductRuntimeModel(_FakeModel):
    def run_product_instruction(self, instruction: str) -> str:
        self.prompts.append(instruction)
        return """REQUIREMENTS
- Preserve the user request.

AMBIGUITIES
- None.

ASSUMPTIONS
- Existing behavior remains available.

ACCEPTANCE CRITERIA
- Product analysis is available to the next stage.

RISKS
- None.

CONFIDENCE
High"""


class _FakeCodeRuntimeModel(_FakeModel):
    backend_name = "code_v5"

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """FILES TO MODIFY
- Candidate: application entrypoint or route handler.

NEW FILES
- Candidate: focused tests for the requested behavior.

CODE CHANGES
- Add the scoped implementation plan.

TESTS TO ADD
- Cover the requested behavior.

RATIONALE
- Preserve acceptance criteria with minimal changes.

CONFIDENCE
High"""


class _FakeTestEngineerRuntimeModel(_FakeModel):
    backend_name = "test_engineer_v5"

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """TEST SCENARIOS
- Verify the requested behavior succeeds.

TEST CASES
- User completes the intended flow successfully.

EDGE CASES
- Repeated attempts are handled consistently.

REGRESSION TESTS
- Existing behavior around the changed area remains unchanged.

AUTOMATION STRATEGY
- Add behavior-level automated coverage.

RISKS
- Missing negative-path coverage may allow regressions.

CONFIDENCE
High"""


class _FakeSecurityRuntimeModel(_FakeModel):
    backend_name = "security_fast"

    def __init__(self, _config: PipelineConfig, *, mode: str = "fast") -> None:
        super().__init__(_config)
        self.mode = mode

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """SECURITY FINDINGS
- The planned change should preserve existing authorization and input validation behavior.

THREATS
- Attackers may attempt to abuse the new behavior at high volume.

ABUSE SCENARIOS
- A malicious actor repeatedly exercises the new flow to disrupt normal users.

SECURITY TESTS
- Verify the new behavior fails safely when limits are reached.

MITIGATIONS
- Use generic user-facing feedback where sensitive state may be inferred.

RESIDUAL RISKS
- Missing telemetry may reduce the ability to detect abuse.

CONFIDENCE
High"""


class _FakeReviewerRuntimeModel(_FakeModel):
    backend_name = "reviewer_fast"

    def __init__(self, _config: PipelineConfig, *, mode: str = "fast") -> None:
        super().__init__(_config)
        self.mode = mode

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """CONSISTENCY CHECK
- Product, architecture, code, tests, and security artifacts are aligned.

REQUIREMENT GAPS
- No requirement gaps identified.

ARCHITECTURE GAPS
- No architecture gaps identified.

IMPLEMENTATION RISKS
- Keep the implementation scoped to the planned password reset flow.

TEST COVERAGE GAPS
- Add focused coverage for allowed and blocked reset attempts.

SECURITY GAPS
- Preserve generic user feedback for account recovery flows.

RECOMMENDATIONS
- Proceed with implementation after confirming the target files.

APPROVAL STATUS
Approved

CONFIDENCE
High"""


class _FakeFixerRuntimeModel(_FakeModel):
    backend_name = "fixer_fast"

    def __init__(self, _config: PipelineConfig, *, mode: str = "fast") -> None:
        super().__init__(_config)
        self.mode = mode

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """FIX SUMMARY
- No significant fixes are required based on the current review.

REQUIREMENT FIXES
- No requirement changes are required.

ARCHITECTURE FIXES
- No architecture changes are required.

IMPLEMENTATION FIXES
- Continue with planned implementation.

TEST FIXES
- Maintain planned test coverage.

SECURITY FIXES
- Maintain planned security controls.

PRIORITY ORDER
- Proceed with implementation review.

READY FOR RE-REVIEW
Yes

CONFIDENCE
High"""


class _FakeFinalReviewerRuntimeModel(_FakeModel):
    backend_name = "final_fast"

    def __init__(self, _config: PipelineConfig, *, mode: str = "fast") -> None:
        super().__init__(_config)
        self.mode = mode

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return """FINAL ASSESSMENT
- The generated artifacts are internally consistent.

REQUIREMENTS STATUS
- Requirements are sufficiently covered.

ARCHITECTURE STATUS
- Architecture aligns with requirements.

IMPLEMENTATION STATUS
- Implementation plan aligns with architecture.

TEST STATUS
- Test coverage addresses major acceptance criteria.

SECURITY STATUS
- Security concerns have been reviewed.

REVIEW STATUS
- Reviewer findings have been addressed.

FIX STATUS
- No significant unresolved fixes remain.

FINAL DECISION
Approved

REASONING
- No blocking inconsistencies remain across the artifact chain.

CONFIDENCE
High"""


class _ExplodingModel:
    def __init__(self, _config: PipelineConfig) -> None:
        raise AssertionError("real model loader should not be called in mock mode")


def _clear_role_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ROLE_BACKEND_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.delenv("ANN_SECURITY_MODE", raising=False)
    monkeypatch.delenv("ANN_REVIEWER_MODE", raising=False)
    monkeypatch.delenv("ANN_FIXER_MODE", raising=False)
    monkeypatch.delenv("ANN_FINAL_REVIEWER_MODE", raising=False)


def test_default_routing_map(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_role_backend_env(monkeypatch)
    monkeypatch.delenv("ANN_ARCHITECT_MODE", raising=False)
    config = PipelineConfig.from_env()
    runner = PipelineRunner(config, mock=False)

    assert runner._backend_for_stage("product") == "qwen3"
    assert runner._backend_for_stage("architect") == "qwen3"
    assert runner._backend_for_stage("code") == "qwen_v5"
    assert runner._backend_for_stage("test") == "qwen_v5"
    assert runner._backend_for_stage("security") == "qwen3"
    assert runner._backend_for_stage("reviewer") == "qwen3"
    assert runner._backend_for_stage("fixer") == "qwen3"
    assert runner._backend_for_stage("final") == "qwen3"


def test_env_override_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_role_backend_env(monkeypatch)
    monkeypatch.setenv("PRODUCT_MODEL_BACKEND", "deepseek_unsloth")
    monkeypatch.setenv("ANN_ARCHITECT_MODE", "deep")
    monkeypatch.setenv("ARCHITECT_MODEL_BACKEND", "deepseek")
    monkeypatch.setenv("CODE_MODEL_BACKEND", "mock")
    monkeypatch.setenv("TEST_MODEL_BACKEND", "deepseek")
    monkeypatch.setenv("ANN_SECURITY_MODE", "deep")
    monkeypatch.setenv("SECURITY_MODEL_BACKEND", "deepseek_unsloth")
    monkeypatch.setenv("ANN_REVIEWER_MODE", "deep")
    monkeypatch.setenv("REVIEWER_MODEL_BACKEND", "deepseek_unsloth")
    monkeypatch.setenv("ANN_FIXER_MODE", "deep")
    monkeypatch.setenv("FIXER_MODEL_BACKEND", "mock")
    monkeypatch.setenv("ANN_FINAL_REVIEWER_MODE", "deep")
    monkeypatch.setenv("FINAL_REVIEWER_MODEL_BACKEND", "deepseek_unsloth")

    runner = PipelineRunner(PipelineConfig.from_env(), mock=False)

    assert runner._backend_for_stage("product") == "deepseek_unsloth"
    assert runner._backend_for_stage("architect") == "deepseek"
    assert runner._backend_for_stage("code") == "mock"
    assert runner._backend_for_stage("test") == "deepseek"
    assert runner._backend_for_stage("security") == "deepseek_unsloth"
    assert runner._backend_for_stage("reviewer") == "deepseek_unsloth"
    assert runner._backend_for_stage("fixer") == "mock"
    assert runner._backend_for_stage("final") == "deepseek_unsloth"


def test_unsupported_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_role_backend_env(monkeypatch)
    monkeypatch.setenv("PRODUCT_MODEL_BACKEND", "not_a_backend")

    with pytest.raises(
        ValueError,
        match="Unsupported model backend for PRODUCT_MODEL_BACKEND: not_a_backend",
    ):
        PipelineConfig.from_env()


def test_mock_mode_bypasses_real_model_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("agentic_network.pipeline.runner.DeepSeekGGUFModel", _ExplodingModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.DeepSeekUnslothModel", _ExplodingModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", _ExplodingModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", _ExplodingModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.ProductAgentRuntimeModel", _ExplodingModel)

    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run("Create a mock-only pipeline run", stages=["product", "code"])

    assert result.stages_run == ["product", "code"]


def test_stage_timings_report_selected_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("agentic_network.pipeline.runner.DeepSeekGGUFModel", _FakeModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.DeepSeekUnslothModel", _FakeModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", _FakeModel)
    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", _FakeModel)
    monkeypatch.setattr("agentic_network.architect_agent.runtime.Qwen3Model", _FakeModel)
    monkeypatch.setattr("agentic_network.architect_agent.runtime.DeepSeekGGUFModel", _FakeModel)
    monkeypatch.setattr("agentic_network.architect_agent.runtime.DeepSeekUnslothModel", _FakeModel)
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.CodeAgentRuntimeModel",
        _FakeCodeRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.TestEngineerRuntimeModel",
        _FakeTestEngineerRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.SecurityAgentRuntimeModel",
        _FakeSecurityRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.ReviewerAgentRuntimeModel",
        _FakeReviewerRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.FixerAgentRuntimeModel",
        _FakeFixerRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.FinalReviewerRuntimeModel",
        _FakeFinalReviewerRuntimeModel,
    )
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.ProductAgentRuntimeModel",
        _FakeProductRuntimeModel,
    )
    runner = PipelineRunner(_config(tmp_path), mock=False)

    result = runner.run(
        "Create a routed fake run",
        stages=[
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
            "knowledge",
            "handoff",
        ],
    )

    summary = json.loads((Path(result.output_dir) / "summary.json").read_text(encoding="utf-8"))
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["context"]["model_backend"] == "none"
    assert by_stage["repository_intelligence"]["model_backend"] == "none"
    assert by_stage["repository_context"]["model_backend"] == "none"
    assert by_stage["product"]["model_backend"] == "qwen3"
    assert by_stage["product"]["input_char_count"] > len("Create a routed fake run")
    assert by_stage["architect"]["model_backend"] == "architect_fast"
    assert by_stage["code"]["model_backend"] == "code_v5"
    assert by_stage["test"]["model_backend"] == "test_engineer_v5"
    assert by_stage["security"]["model_backend"] == "security_fast"
    assert by_stage["reviewer"]["model_backend"] == "reviewer_fast"
    assert by_stage["fixer"]["model_backend"] == "fixer_fast"
    assert by_stage["final"]["model_backend"] == "final_fast"
    assert by_stage["context"]["model_backend"] == "none"
    assert by_stage["revision"]["model_backend"] == "none"
    assert by_stage["execution"]["model_backend"] == "none"
    assert by_stage["patch_quality"]["model_backend"] == "none"
    assert by_stage["patch_approval"]["model_backend"] == "none"
    assert by_stage["knowledge"]["model_backend"] == "none"
    assert by_stage["handoff"]["model_backend"] == "none"
    assert summary["context_status"] == "VALID"
    assert summary["context_validation_passed"] is True
    assert summary["context_validation_errors"] == []
    assert isinstance(summary["context_patterns_found"], list)
    assert summary["repository_intelligence_enabled"] is True
    assert summary["repository_intelligence_validation_passed"] is True
    assert summary["repository_intelligence_files_scanned"] > 0
    assert summary["repository_context_enabled"] is True
    assert summary["repository_context_validation_passed"] is True
    assert summary["repository_context_chars"] > 0
    assert summary["code_validation_passed"] is True
    assert summary["code_validation_errors"] == []
    assert summary["test_engineer_status"] == "VALID"
    assert summary["test_validation_errors"] == []
    assert summary["security_status"] == "VALID"
    assert summary["security_validation_errors"] == []
    assert summary["reviewer_validation_passed"] is True
    assert summary["reviewer_validation_errors"] == []
    assert summary["reviewer_approval_status"] == "Approved"
    assert summary["fixer_status"] == "VALID"
    assert summary["fixer_validation_errors"] == []
    assert summary["fixer_ready_for_rereview"] == "Yes"
    assert summary["revision_status"] == "VALID"
    assert summary["revision_validation_passed"] is True
    assert summary["revision_validation_errors"] == []
    assert "03_code_revised.md" in summary["revision_artifacts_generated"]
    assert summary["final_validation_passed"] is True
    assert summary["final_validation_errors"] == []
    assert summary["final_decision"] == "Approved"
    assert summary["execution_status"] == "VALID"
    assert summary["execution_validation_passed"] is True
    assert summary["execution_validation_errors"] == []
    assert summary["execution_patch_count"] >= 1
    assert summary["execution_target_selection_used"] in {True, False}
    assert isinstance(summary["execution_selected_targets"], list)
    assert isinstance(summary["execution_rejected_targets"], list)
    assert isinstance(summary["execution_target_classes"], dict)
    assert isinstance(summary["execution_target_selection_reasons"], dict)
    assert summary["execution_target_selection_confidence"] in {"", "Low", "Medium", "High"}
    assert summary["execution_multifile_plan_used"] is True
    assert summary["execution_multifile_plan_type"] in {
        "RATE_LIMITING_FEATURE",
        "PAGINATION_FEATURE",
        "AUTH_GUARD_FEATURE",
        "DOCUMENTATION_ONLY",
        "UNKNOWN_FEATURE",
    }
    assert isinstance(summary["execution_multifile_selected_files"], list)
    assert isinstance(summary["execution_multifile_file_roles"], dict)
    assert isinstance(summary["execution_multifile_missing_layers"], list)
    assert summary["execution_multifile_confidence"] in {"Low", "Medium", "High"}
    assert summary["execution_layer_creation_used"] in {True, False}
    assert isinstance(summary["execution_layer_proposed_files"], list)
    assert isinstance(summary["execution_layer_rejected_layers"], dict)
    assert isinstance(summary["execution_layer_creation_rationale"], list)
    assert summary["execution_layer_creation_validation_passed"] in {True, False}
    assert isinstance(summary["execution_layer_creation_validation_errors"], list)
    assert summary["execution_layer_creation_confidence"] in {"", "Low", "Medium", "High"}
    assert summary["patch_quality_status"] == "VALID"
    assert summary["patch_quality_decision"] in {
        "IMPLEMENTATION_READY",
        "NEEDS_RELOCATION",
        "NEEDS_REVISION",
        "LOW_VALUE_COMMENT_ONLY",
        "UNCONNECTED_LOGIC",
        "REJECTED",
    }
    assert isinstance(summary["patch_quality_score"], int)
    assert summary["patch_quality_validation_passed"] in {True, False}
    assert summary["patch_approval_status"] == "VALID"
    assert summary["patch_approval_decision"] == "Approved"
    assert summary["patch_approval_validation_passed"] is True
    assert summary["patch_approval_validation_errors"] == []
    assert summary["knowledge_status"] == "VALID"
    assert summary["knowledge_validation_passed"] is True
    assert summary["knowledge_future_reuse_score"] in {"Low", "Medium", "High"}
    assert summary["handoff_status"] == "VALID"
    assert summary["handoff_validation_passed"] is True
    assert summary["handoff_missing_artifacts"] == []


def test_mock_pipeline_writes_all_artifacts_and_runs_fixer(tmp_path: Path, capsys) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=True)

    result = runner.run("Create a hello world FastAPI endpoint")
    stdout = capsys.readouterr().out

    output_dir = Path(result.output_dir)
    assert output_dir.exists()
    assert result.reviewer_status == "CHANGES REQUIRED"
    assert result.final_status == "CHANGES REQUIRED"
    assert "fixer" in result.stages_run

    expected_files = [
        "00_user_request.md",
        "00_context.md",
        "repository_intelligence/project_summary.json",
        "26_repository_context.md",
        "26_repository_context.json",
        "01_product_requirements.md",
        "02_architecture_plan.md",
        "03_code.md",
        "04_tests.md",
        "05_security.md",
        "06_review.md",
        "06a_failure_context.json",
        "06a_failure_context.md",
        "07_fix_plan.md",
        "07a_post_fix_static_sanity.md",
        "03_code_revised.md",
        "04_tests_revised.md",
        "05_security_revised.md",
        "10_revision_summary.md",
        "08_final_review.md",
        "11_execution_plan.md",
        "25_patch_quality.md",
        "12_patch_approval.md",
        "10_knowledge_capture.md",
        "09_handoff_bundle.md",
        "summary.json",
    ]
    for filename in expected_files:
        assert (output_dir / filename).exists(), filename

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["reviewer_status"] == "CHANGES REQUIRED"
    assert summary["final_status"] == "CHANGES REQUIRED"
    assert "06a_failure_context.md" in summary["output_files"]["failure_context"]
    assert "06a_failure_context.json" in summary["output_files"]["failure_context_json"]
    assert "07_fix_plan.md" in summary["output_files"]["fixer"]
    assert "07a_post_fix_static_sanity.md" in summary["post_fix_static_sanity_file"]
    assert summary["post_fix_static_sanity_findings_count"] == 0
    assert summary["test_engineer_status"] == "VALID"
    assert summary["test_validation_passed"] is True
    assert summary["test_validation_errors"] == []
    assert summary["test_fallback_used"] is False
    assert summary["security_status"] == "VALID"
    assert summary["security_validation_passed"] is True
    assert summary["security_validation_errors"] == []
    assert summary["security_fallback_used"] is False
    assert summary["reviewer_validation_passed"] is True
    assert summary["reviewer_validation_errors"] == []
    assert summary["reviewer_fallback_used"] is False
    assert summary["reviewer_approval_status"] == "Needs Fixes"
    assert summary["fixer_status"] == "VALID"
    assert summary["fixer_validation_passed"] is True
    assert summary["fixer_validation_errors"] == []
    assert summary["fixer_fallback_used"] is False
    assert summary["fixer_ready_for_rereview"] == "No"
    assert summary["final_validation_passed"] is True
    assert summary["final_validation_errors"] == []
    assert summary["final_fallback_used"] is False
    assert summary["final_decision"] == "Rejected"
    assert summary["execution_status"] == "REFUSED"
    assert summary["execution_validation_passed"] is False
    assert "final_decision_not_approved" in summary["execution_validation_errors"]
    assert summary["execution_patch_count"] == 0
    assert summary["patch_approval_status"] == "INVALID"
    assert summary["patch_approval_decision"] == "Rejected"
    assert "patch_files_missing" in summary["patch_approval_validation_errors"]
    assert summary["context_status"] == "VALID"
    assert summary["context_validation_passed"] is True
    assert summary["context_validation_errors"] == []
    assert isinstance(summary["context_patterns_found"], list)
    assert summary["repository_intelligence_enabled"] is True
    assert summary["repository_intelligence_validation_passed"] is True
    assert summary["repository_intelligence_files_scanned"] > 0
    assert summary["repository_context_enabled"] is True
    assert summary["repository_context_validation_passed"] is True
    assert summary["repository_context_chars"] > 0
    assert summary["knowledge_status"] == "VALID"
    assert summary["knowledge_validation_passed"] is True
    assert summary["knowledge_future_reuse_score"] in {"Low", "Medium", "High"}
    assert summary["handoff_status"] == "VALID"
    assert summary["handoff_validation_passed"] is True
    assert summary["handoff_missing_artifacts"] == []
    assert "07a_post_fix_static_sanity.md" in summary["output_files"]["post_fix_static_sanity"]
    assert "Timing table" in stdout
    assert "Product Agent" in stdout
    assert "Final Reviewer Agent" in stdout

    stage_timings = summary["stage_timings"]
    assert [record["stage"] for record in stage_timings] == [
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
        "knowledge",
        "handoff",
    ]
    required_timing_fields = {
        "stage",
        "stage_name",
        "model_backend",
        "started_at",
        "ended_at",
        "duration_seconds",
        "input_char_count",
        "output_char_count",
        "gpu_config",
        "device_info",
        "static_sanity_ran",
        "fixer_ran",
        "post_fix_sanity_ran",
    }
    for record in stage_timings:
        assert required_timing_fields <= set(record)
        assert record["started_at"].endswith("Z")
        assert record["ended_at"].endswith("Z")
        assert record["duration_seconds"] >= 0
        assert record["input_char_count"] > 0
        assert record["output_char_count"] > 0

    by_stage = {record["stage"]: record for record in stage_timings}
    assert {record["model_backend"] for record in stage_timings} == {"mock", "none"}
    assert by_stage["context"]["model_backend"] == "none"
    assert by_stage["repository_intelligence"]["model_backend"] == "none"
    assert by_stage["repository_context"]["model_backend"] == "none"
    assert by_stage["product"]["static_sanity_ran"] is False
    assert by_stage["reviewer"]["static_sanity_ran"] is True
    assert by_stage["fixer"]["fixer_ran"] is True
    assert by_stage["fixer"]["post_fix_sanity_ran"] is True
    assert by_stage["revision"]["model_backend"] == "none"
    assert by_stage["revision"]["post_fix_sanity_ran"] is True
    assert by_stage["final"]["post_fix_sanity_ran"] is True
    assert by_stage["execution"]["model_backend"] == "none"
    assert by_stage["execution"]["post_fix_sanity_ran"] is True
    assert by_stage["patch_approval"]["model_backend"] == "none"
    assert by_stage["patch_approval"]["post_fix_sanity_ran"] is True
    assert by_stage["context"]["model_backend"] == "none"
    assert by_stage["execution"]["model_backend"] == "none"
    assert by_stage["patch_approval"]["model_backend"] == "none"
    assert by_stage["knowledge"]["model_backend"] == "none"
    assert by_stage["handoff"]["model_backend"] == "none"


def test_mock_pipeline_product_architect_code_test_security_reviewer_fixer_final_writes_artifacts(
    tmp_path: Path,
) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Create a minimal module",
        stages=[
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
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    assert result.stages_run == [
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
        "knowledge",
        "handoff",
    ]
    assert result.reviewer_status == "APPROVED"
    assert result.final_status == "APPROVED"
    assert (output_dir / "00_context.md").exists()
    assert (output_dir / "repository_intelligence" / "project_summary.json").exists()
    assert (output_dir / "26_repository_context.md").exists()
    assert (output_dir / "26_repository_context.json").exists()
    assert (output_dir / "01_product_requirements.md").exists()
    assert (output_dir / "02_architecture_plan.md").exists()
    assert (output_dir / "03_code.md").exists()
    assert (output_dir / "04_tests.md").exists()
    assert (output_dir / "05_security.md").exists()
    assert (output_dir / "06_review.md").exists()
    assert (output_dir / "07_fix_plan.md").exists()
    assert (output_dir / "03_code_revised.md").exists()
    assert (output_dir / "04_tests_revised.md").exists()
    assert (output_dir / "05_security_revised.md").exists()
    assert (output_dir / "10_revision_summary.md").exists()
    assert (output_dir / "08_final_review.md").exists()
    assert (output_dir / "11_execution_plan.md").exists()
    assert (output_dir / "12_patch_approval.md").exists()
    assert (output_dir / "10_knowledge_capture.md").exists()
    assert (output_dir / "09_handoff_bundle.md").exists()

    context = (output_dir / "00_context.md").read_text(encoding="utf-8")
    parsed_context = parse_context_sections(context)
    assert parsed_context["context_confidence"] == "High"
    architecture = (output_dir / "02_architecture_plan.md").read_text(encoding="utf-8")
    parsed = parse_architect_agent_sections(architecture)
    assert parsed["confidence"] == "High"
    assert parsed["handoff_to_code_agent"]

    code_plan = (output_dir / "03_code.md").read_text(encoding="utf-8")
    parsed_code = parse_code_agent_sections(code_plan)
    assert parsed_code["confidence"] == "High"
    assert parsed_code["code_changes"]
    test_plan = (output_dir / "04_tests.md").read_text(encoding="utf-8")
    parsed_test = parse_test_engineer_sections(test_plan)
    assert parsed_test["confidence"] == "High"
    assert parsed_test["test_scenarios"]
    security_review = (output_dir / "05_security.md").read_text(encoding="utf-8")
    parsed_security = parse_security_agent_sections(security_review)
    assert parsed_security["confidence"] == "High"
    assert parsed_security["security_findings"]
    reviewer_review = (output_dir / "06_review.md").read_text(encoding="utf-8")
    parsed_reviewer = parse_reviewer_agent_sections(reviewer_review)
    assert parsed_reviewer["confidence"] == "High"
    assert parsed_reviewer["approval_status"] == "Approved"
    assert parsed_reviewer["consistency_check"]
    fix_plan = (output_dir / "07_fix_plan.md").read_text(encoding="utf-8")
    parsed_fixer = parse_fixer_agent_sections(fix_plan)
    assert parsed_fixer["confidence"] == "High"
    assert parsed_fixer["ready_for_rereview"] == "Yes"
    assert parsed_fixer["fix_summary"]
    revision_summary = (output_dir / "10_revision_summary.md").read_text(encoding="utf-8")
    parsed_revision = parse_revision_sections(revision_summary)
    assert parsed_revision["confidence"] == "High"
    assert parsed_revision["revision_summary"]
    final_review = (output_dir / "08_final_review.md").read_text(encoding="utf-8")
    parsed_final = parse_final_reviewer_sections(final_review)
    assert parsed_final["confidence"] == "High"
    assert parsed_final["final_decision"] == "Approved"
    assert parsed_final["final_assessment"]
    execution_plan = (output_dir / "11_execution_plan.md").read_text(encoding="utf-8")
    parsed_execution = parse_execution_plan_sections(execution_plan)
    assert parsed_execution["execution_confidence"] == "High"
    assert parsed_execution["execution_summary"]
    assert (output_dir / "patches" / "patch_001.diff").exists()
    patch_approval = (output_dir / "12_patch_approval.md").read_text(encoding="utf-8")
    parsed_patch_approval = parse_patch_approval_sections(patch_approval)
    assert parsed_patch_approval["approval_decision"] == "Approved"
    assert parsed_patch_approval["confidence"] == "High"
    knowledge_capture = (output_dir / "10_knowledge_capture.md").read_text(encoding="utf-8")
    parsed_knowledge = parse_knowledge_capture_sections(knowledge_capture)
    assert parsed_knowledge["confidence"] == "High"
    assert parsed_knowledge["future_reuse_score"] in {"Low", "Medium", "High"}
    handoff_bundle = (output_dir / "09_handoff_bundle.md").read_text(encoding="utf-8")
    assert "# ANN Handoff Bundle" in handoff_bundle
    assert "## 00 Context" in handoff_bundle
    assert "## 08 Final Review" in handoff_bundle
    assert "## 11 Execution Plan" in handoff_bundle
    assert "## 12 Patch Approval" in handoff_bundle
    assert "## 10 Knowledge Capture" in handoff_bundle
    assert "- Final decision: Approved" in handoff_bundle
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["context_status"] == "VALID"
    assert summary["context_validation_passed"] is True
    assert summary["context_validation_errors"] == []
    assert isinstance(summary["context_patterns_found"], list)
    assert summary["code_validation_passed"] is True
    assert summary["code_validation_errors"] == []
    assert summary["test_engineer_status"] == "VALID"
    assert summary["test_validation_errors"] == []
    assert summary["security_status"] == "VALID"
    assert summary["security_validation_errors"] == []
    assert summary["reviewer_validation_passed"] is True
    assert summary["reviewer_validation_errors"] == []
    assert summary["reviewer_approval_status"] == "Approved"
    assert summary["fixer_status"] == "VALID"
    assert summary["fixer_validation_errors"] == []
    assert summary["fixer_ready_for_rereview"] == "Yes"
    assert summary["revision_status"] == "VALID"
    assert summary["revision_validation_passed"] is True
    assert summary["revision_validation_errors"] == []
    assert "03_code_revised.md" in summary["revision_artifacts_generated"]
    assert summary["final_validation_passed"] is True
    assert summary["final_validation_errors"] == []
    assert summary["final_decision"] == "Approved"
    assert summary["execution_status"] == "VALID"
    assert summary["execution_validation_passed"] is True
    assert summary["execution_validation_errors"] == []
    assert summary["execution_patch_count"] >= 1
    assert summary["patch_approval_status"] == "VALID"
    assert summary["patch_approval_decision"] == "Approved"
    assert summary["patch_approval_validation_passed"] is True
    assert summary["patch_approval_validation_errors"] == []
    assert summary["knowledge_status"] == "VALID"
    assert summary["knowledge_validation_errors"] == []
    assert summary["handoff_status"] == "VALID"
    assert summary["handoff_validation_errors"] == []
    assert "00_context.md" in summary["handoff_included_artifacts"]
    assert "08_final_review.md" in summary["handoff_included_artifacts"]
    assert "11_execution_plan.md" in summary["handoff_included_artifacts"]
    assert "12_patch_approval.md" in summary["handoff_included_artifacts"]
    assert "10_knowledge_capture.md" in summary["handoff_included_artifacts"]


def test_real_product_architect_code_test_security_reviewer_and_fixer_stages_use_subprocess_isolation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> SimpleNamespace:
        calls.append(command)
        output_path = Path(command[command.index("--output") + 1])
        if "agentic_network.product_agent.run" in command:
            output_path.write_text(
                "REQUIREMENTS\n"
                "- Add rate limits to password reset requests.\n\n"
                "AMBIGUITIES\n"
                "- Exact threshold is unspecified.\n\n"
                "ASSUMPTIONS\n"
                "- Use existing settings patterns.\n\n"
                "ACCEPTANCE CRITERIA\n"
                "- Repeated requests are limited.\n\n"
                "RISKS\n"
                "- Misconfigured limits can block legitimate users.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.architect_agent.run" in command:
            output_path.write_text(
                "TECHNICAL SUMMARY\n"
                "- Add a minimal rate-limit plan.\n\n"
                "AFFECTED AREAS\n"
                "- Password reset flow.\n\n"
                "FILES TO INSPECT\n"
                "- apps/api/app/api/routes.py\n\n"
                "IMPLEMENTATION PLAN\n"
                "- Inspect the existing route before editing.\n\n"
                "DATA OR STATE CHANGES\n"
                "- No migration expected.\n\n"
                "TEST STRATEGY\n"
                "- Test allowed and blocked repeated requests.\n\n"
                "RISKS\n"
                "- Thresholds may need tuning.\n\n"
                "HANDOFF TO CODE AGENT\n"
                "- Implement only the scoped route and tests.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.code_agent.run" in command:
            output_path.write_text(
                "FILES TO MODIFY\n"
                "- apps/api/app/api/routes.py\n\n"
                "NEW FILES\n"
                "- Candidate: tests for password reset rate-limit behavior.\n\n"
                "CODE CHANGES\n"
                "- Add configurable rate limit policy.\n"
                "- Block excessive requests with user-facing feedback.\n\n"
                "TESTS TO ADD\n"
                "- Verify limits are enforced.\n"
                "- Verify legitimate resets still work.\n\n"
                "RATIONALE\n"
                "- Prevent abuse while preserving usability.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.test_engineer.run" in command:
            output_path.write_text(
                "TEST SCENARIOS\n"
                "- Verify password reset rate limits prevent repeated abuse.\n\n"
                "TEST CASES\n"
                "- User reaches the configured reset limit and receives clear feedback.\n"
                "- User remains below the limit and receives reset instructions normally.\n\n"
                "EDGE CASES\n"
                "- Multiple reset attempts occur close together.\n\n"
                "REGRESSION TESTS\n"
                "- Existing successful password reset behavior remains unchanged.\n\n"
                "AUTOMATION STRATEGY\n"
                "- Add behavior-level tests for allowed and blocked reset flows.\n\n"
                "RISKS\n"
                "- Poorly controlled time windows may make tests flaky.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.security_agent.run" in command:
            output_path.write_text(
                "SECURITY FINDINGS\n"
                "- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.\n\n"
                "THREATS\n"
                "- Automated reset abuse may overwhelm users or email systems.\n\n"
                "ABUSE SCENARIOS\n"
                "- An attacker repeatedly triggers reset messages for a target user.\n\n"
                "SECURITY TESTS\n"
                "- Verify excessive reset attempts are limited without revealing account existence.\n\n"
                "MITIGATIONS\n"
                "- Use generic feedback for reset requests and limit events.\n\n"
                "RESIDUAL RISKS\n"
                "- Highly distributed abuse may still bypass simple limits.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.reviewer_agent.run" in command:
            output_path.write_text(
                "CONSISTENCY CHECK\n"
                "- Product, architecture, code, tests, and security artifacts are aligned.\n\n"
                "REQUIREMENT GAPS\n"
                "- No requirement gaps identified.\n\n"
                "ARCHITECTURE GAPS\n"
                "- No architecture gaps identified.\n\n"
                "IMPLEMENTATION RISKS\n"
                "- Keep implementation scoped to the planned password reset flow.\n\n"
                "TEST COVERAGE GAPS\n"
                "- Add focused coverage for allowed and blocked reset attempts.\n\n"
                "SECURITY GAPS\n"
                "- Preserve generic feedback for account recovery flows.\n\n"
                "RECOMMENDATIONS\n"
                "- Proceed with implementation after confirming the target files.\n\n"
                "APPROVAL STATUS\n"
                "Approved\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.fixer_agent.run" in command:
            output_path.write_text(
                "FIX SUMMARY\n"
                "- No significant fixes are required based on the current review.\n\n"
                "REQUIREMENT FIXES\n"
                "- No requirement changes are required.\n\n"
                "ARCHITECTURE FIXES\n"
                "- No architecture changes are required.\n\n"
                "IMPLEMENTATION FIXES\n"
                "- Continue with planned implementation.\n\n"
                "TEST FIXES\n"
                "- Maintain planned test coverage.\n\n"
                "SECURITY FIXES\n"
                "- Maintain planned security controls.\n\n"
                "PRIORITY ORDER\n"
                "- Proceed with implementation review.\n\n"
                "READY FOR RE-REVIEW\n"
                "Yes\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        elif "agentic_network.final_reviewer.run" in command:
            assert "03_code_revised.md" in command[command.index("--code-plan-file") + 1]
            assert "04_tests_revised.md" in command[command.index("--test-plan-file") + 1]
            assert "05_security_revised.md" in command[command.index("--security-review-file") + 1]
            output_path.write_text(
                "FINAL ASSESSMENT\n"
                "- The generated artifacts are internally consistent.\n\n"
                "REQUIREMENTS STATUS\n"
                "- Requirements are sufficiently covered.\n\n"
                "ARCHITECTURE STATUS\n"
                "- Architecture aligns with requirements.\n\n"
                "IMPLEMENTATION STATUS\n"
                "- Implementation plan aligns with architecture.\n\n"
                "TEST STATUS\n"
                "- Test coverage addresses major acceptance criteria.\n\n"
                "SECURITY STATUS\n"
                "- Security concerns have been reviewed.\n\n"
                "REVIEW STATUS\n"
                "- Reviewer findings have been addressed.\n\n"
                "FIX STATUS\n"
                "- No significant unresolved fixes remain.\n\n"
                "FINAL DECISION\n"
                "Approved\n\n"
                "REASONING\n"
                "- No blocking inconsistencies remain across the artifact chain.\n\n"
                "CONFIDENCE\n"
                "High\n",
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0, stdout="captured stdout", stderr="")

    monkeypatch.setattr("agentic_network.pipeline.runner.subprocess.run", fake_run)
    runner = PipelineRunner(_config(tmp_path, stage_isolation="subprocess"), mock=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    assert result.stages_run == [
        "context",
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
        "patch_approval",
        "knowledge",
        "handoff",
    ]
    assert (output_dir / "00_context.md").exists()
    assert (output_dir / "01_product_requirements.md").exists()
    assert (output_dir / "02_architecture_plan.md").exists()
    assert (output_dir / "03_code.md").exists()
    assert (output_dir / "04_tests.md").exists()
    assert (output_dir / "05_security.md").exists()
    assert (output_dir / "06_review.md").exists()
    assert (output_dir / "07_fix_plan.md").exists()
    assert (output_dir / "03_code_revised.md").exists()
    assert (output_dir / "04_tests_revised.md").exists()
    assert (output_dir / "05_security_revised.md").exists()
    assert (output_dir / "10_revision_summary.md").exists()
    assert (output_dir / "08_final_review.md").exists()
    assert (output_dir / "11_execution_plan.md").exists()
    assert (output_dir / "12_patch_approval.md").exists()
    assert (output_dir / "10_knowledge_capture.md").exists()
    assert (output_dir / "09_handoff_bundle.md").exists()
    assert (output_dir / "product_subprocess_stdout.log").exists()
    assert (output_dir / "architect_subprocess_stdout.log").exists()
    assert (output_dir / "code_subprocess_stdout.log").exists()
    assert (output_dir / "test_subprocess_stdout.log").exists()
    assert (output_dir / "security_subprocess_stdout.log").exists()
    assert (output_dir / "reviewer_subprocess_stdout.log").exists()
    assert (output_dir / "fixer_subprocess_stdout.log").exists()
    assert not (output_dir / "revision_subprocess_stdout.log").exists()
    assert (output_dir / "final_subprocess_stdout.log").exists()
    assert not (output_dir / "execution_subprocess_stdout.log").exists()
    assert not (output_dir / "patch_approval_subprocess_stdout.log").exists()
    assert not (output_dir / "context_subprocess_stdout.log").exists()
    assert not (output_dir / "knowledge_subprocess_stdout.log").exists()
    assert not (output_dir / "handoff_subprocess_stdout.log").exists()
    assert not any("agentic_network.context_agent.run" in command for command in calls)
    assert any("agentic_network.product_agent.run" in command for command in calls)
    assert any("agentic_network.architect_agent.run" in command for command in calls)
    assert any("agentic_network.code_agent.run" in command for command in calls)
    assert any("agentic_network.test_engineer.run" in command for command in calls)
    assert any("agentic_network.security_agent.run" in command for command in calls)
    assert any("agentic_network.reviewer_agent.run" in command for command in calls)
    assert any("agentic_network.fixer_agent.run" in command for command in calls)
    assert not any("agentic_network.revision_agent.run" in command for command in calls)
    assert any("agentic_network.final_reviewer.run" in command for command in calls)
    assert not any("agentic_network.execution_agent.run" in command for command in calls)
    assert not any("agentic_network.patch_approval_agent.run" in command for command in calls)
    assert not any("agentic_network.knowledge_agent.run" in command for command in calls)
    assert not any("agentic_network.handoff.run" in command for command in calls)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["context_status"] == "VALID"
    assert summary["context_validation_passed"] is True
    assert summary["context_validation_errors"] == []
    assert isinstance(summary["context_patterns_found"], list)
    assert summary["code_validation_passed"] is True
    assert summary["code_validation_errors"] == []
    assert summary["test_engineer_status"] == "VALID"
    assert summary["test_validation_errors"] == []
    assert summary["security_status"] == "VALID"
    assert summary["security_validation_errors"] == []
    assert summary["reviewer_validation_passed"] is True
    assert summary["reviewer_validation_errors"] == []
    assert summary["reviewer_approval_status"] == "Approved"
    assert summary["fixer_status"] == "VALID"
    assert summary["fixer_validation_errors"] == []
    assert summary["fixer_ready_for_rereview"] == "Yes"
    assert summary["revision_status"] == "VALID"
    assert summary["revision_validation_passed"] is True
    assert summary["revision_validation_errors"] == []
    assert "03_code_revised.md" in summary["revision_artifacts_generated"]
    assert summary["final_validation_passed"] is True
    assert summary["final_validation_errors"] == []
    assert summary["final_decision"] == "Approved"
    assert summary["execution_status"] == "VALID"
    assert summary["execution_validation_passed"] is True
    assert summary["execution_validation_errors"] == []
    assert summary["execution_patch_count"] >= 1
    assert summary["patch_approval_status"] == "VALID"
    assert summary["patch_approval_decision"] == "Approved"
    assert summary["patch_approval_validation_passed"] is True
    assert summary["patch_approval_validation_errors"] == []
    assert summary["knowledge_status"] == "VALID"
    assert summary["knowledge_validation_passed"] is True
    assert summary["knowledge_future_reuse_score"] in {"Low", "Medium", "High"}
    assert summary["handoff_status"] == "VALID"
    assert summary["handoff_validation_passed"] is True
    assert summary["handoff_missing_artifacts"] == []
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["context"]["model_backend"] == "none"
    assert by_stage["execution"]["model_backend"] == "none"
    assert by_stage["patch_approval"]["model_backend"] == "none"
    assert by_stage["knowledge"]["model_backend"] == "none"
    assert by_stage["handoff"]["model_backend"] == "none"


def test_mock_pipeline_writes_skipped_fixer_artifact_when_approved(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run("Create an approved mock module")

    output_dir = Path(result.output_dir)
    fixes = (output_dir / "07_fix_plan.md").read_text(encoding="utf-8")
    assert result.reviewer_status == "APPROVED"
    assert result.final_status == "APPROVED"
    assert "fixer" not in result.stages_run
    assert "SKIPPED" in fixes



def test_explicit_mock_pipeline_patch_apply_writes_skipped_artifact(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert result.stages_run == [
        "context",
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
        "patch_approval",
        "patch_apply",
        "knowledge",
        "handoff",
    ]
    assert (output_dir / "13_patch_apply.md").exists()
    assert not (output_dir / "backups").exists()
    assert summary["patch_apply_status"] == "SKIPPED"
    assert summary["patch_apply_dry_run"] is True
    assert summary["patch_apply_approved_flag"] is False
    assert "approve_patches_flag_missing" in summary["patch_apply_validation_errors"]
    assert "13_patch_apply.md" in summary["handoff_included_artifacts"]
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["patch_apply"]["model_backend"] == "none"
    assert by_stage["patch_apply"]["post_fix_sanity_ran"] is True



def test_explicit_mock_pipeline_test_runner_skips_without_run_tests(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert (output_dir / "14_test_run.md").exists()
    assert summary["test_runner_status"] == "SKIPPED"
    assert summary["test_runner_run_tests_flag"] is False
    assert summary["test_runner_commands_executed"] == []
    assert "14_test_run.md" in summary["handoff_included_artifacts"]
    test_run = (output_dir / "14_test_run.md").read_text(encoding="utf-8")
    assert "TEST STATUS\nSkipped" in test_run
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["test_runner"]["model_backend"] == "none"


def test_explicit_mock_pipeline_self_healing_skips_after_skipped_test_runner(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "self_healing",
            "merge_readiness",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert (output_dir / "21_self_healing.md").exists()
    assert (output_dir / "17_failure_analysis.md").exists()
    assert (output_dir / "18_root_cause.md").exists()
    assert summary["test_runner_status"] == "SKIPPED"
    assert summary["self_healing_status"] == "SKIPPED"
    assert summary["self_healing_last_patch"] == ""
    assert summary["self_healing_validation_passed"] is True
    assert "21_self_healing.md" in summary["handoff_included_artifacts"]
    assert "17_failure_analysis.md" in summary["handoff_included_artifacts"]
    assert "18_root_cause.md" in summary["handoff_included_artifacts"]
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["self_healing"]["model_backend"] == "none"
    assert result.stages_run.index("test_runner") < result.stages_run.index("self_healing")
    assert result.stages_run.index("self_healing") < result.stages_run.index("merge_readiness")


def test_explicit_mock_pipeline_autonomous_loop_skips_without_run_tests(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "self_healing",
            "autonomous_loop",
            "merge_readiness",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert (output_dir / "27_autonomous_loop.md").exists()
    assert summary["autonomous_loop_status"] == "SKIPPED"
    assert summary["autonomous_loop_validation_passed"] is True
    assert "27_autonomous_loop.md" in summary["handoff_included_artifacts"]
    assert result.stages_run.index("self_healing") < result.stages_run.index("autonomous_loop")
    assert result.stages_run.index("autonomous_loop") < result.stages_run.index("merge_readiness")
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["autonomous_loop"]["model_backend"] == "none"


def test_explicit_mock_pipeline_memory_records_after_merge_readiness(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "self_healing",
            "memory",
            "merge_readiness",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    context_text = (output_dir / "00_context.md").read_text(encoding="utf-8")
    assert summary["memory_enabled"] is True
    assert summary["memory_patterns_recorded"] >= 0
    assert summary["memory_successful_repairs"] >= 0
    assert summary["memory_last_domain"] == "rate_limiting"
    assert summary["memory_validation_passed"] is True
    assert (output_dir / "22_memory_query.md").exists()
    assert (output_dir / "23_memory_matches.md").exists()
    assert (output_dir / "24_experience_context.md").exists()
    assert "Experience Memory" in context_text
    assert summary["memory_retrieval_enabled"] is True
    assert summary["memory_query"] == "Add rate limits to password reset requests."
    assert summary["memory_context_injected"] is True
    assert summary["memory_retrieval_validation_passed"] is True
    assert "memory_query" in summary["output_files"]
    assert "memory_matches" in summary["output_files"]
    assert "experience_context" in summary["output_files"]
    if summary["memory_matches_found"] > 0:
        assert summary["execution_memory_used"] is True
    assert result.stages_run.index("merge_readiness") < result.stages_run.index("memory")
    assert result.stages_run.index("memory") < result.stages_run.index("knowledge")
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["memory"]["model_backend"] == "none"


def test_explicit_mock_pipeline_test_runner_can_use_mocked_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="mocked tests passed\n", stderr="")

    monkeypatch.setattr("agentic_network.test_runner_agent.runtime.subprocess.run", fake_run)
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
        ],
        run_tests=True,
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["test_runner_status"] == "PASSED"
    assert summary["test_runner_run_tests_flag"] is True
    assert summary["test_runner_commands_selected"] == [["python", "-m", "pytest"]]
    assert summary["test_runner_commands_executed"] == [["python", "-m", "pytest"]]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == "/mnt/d/AgenticEngineeringNetwork"



def test_explicit_mock_pipeline_merge_readiness_ready_to_apply(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "merge_readiness",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert (output_dir / "15_merge_readiness.md").exists()
    assert summary["merge_readiness_status"] == "VALID"
    assert summary["merge_readiness_decision"] == "READY TO APPLY"
    assert summary["merge_readiness_validation_passed"] is True
    assert "15_merge_readiness.md" in summary["handoff_included_artifacts"]
    merge_readiness = (output_dir / "15_merge_readiness.md").read_text(encoding="utf-8")
    assert "MERGE DECISION\nREADY TO APPLY" in merge_readiness
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["merge_readiness"]["model_backend"] == "none"



def test_explicit_mock_pipeline_human_approval_denied_by_default(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "merge_readiness",
            "human_approval",
            "knowledge",
            "handoff",
        ],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert (output_dir / "16_human_approval.md").exists()
    assert summary["human_approval_status"] == "VALID"
    assert summary["human_approval_decision"] == "Denied"
    assert summary["human_approval_token_status"] == "missing"
    assert summary["human_approval_validation_passed"] is True
    assert "16_human_approval.md" in summary["handoff_included_artifacts"]
    human_approval = (output_dir / "16_human_approval.md").read_text(encoding="utf-8")
    assert "AUTHORIZATION DECISION\nDenied" in human_approval
    by_stage = {record["stage"]: record for record in summary["stage_timings"]}
    assert by_stage["human_approval"]["model_backend"] == "none"


def _fake_patch_apply_stage_factory(calls: list[tuple[bool, bool]]):
    def fake_patch_apply_stage(*, artifacts, stage_timings, approve_patches: bool, dry_run: bool):
        calls.append((approve_patches, dry_run))
        status = "DRY_RUN_PASSED" if dry_run else "APPLIED"
        report = (
            "PATCH APPLY SUMMARY\n"
            f"- Status: {status}.\n\n"
            "APPROVAL STATUS\n"
            f"- Approved flag: {approve_patches}.\n\n"
            "PATCHES PROCESSED\n"
            "- patch_001.diff\n\n"
            "FILES MODIFIED\n"
            "- None\n\n"
            "BACKUPS CREATED\n"
            "- None\n\n"
            "VALIDATION\n"
            "- Passed\n\n"
            "PATCH APPLY STATUS\n"
            f"{status}\n\n"
            "CONFIDENCE\n"
            "High\n"
        )
        artifact_path = Path(artifacts.root) / "13_patch_apply.md"
        artifact_path.write_text(report, encoding="utf-8")
        stage_timings.append(
            {
                "stage": "patch_apply",
                "stage_name": "Patch Apply Agent",
                "model_backend": "none",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:00Z",
                "duration_seconds": 0.0,
                "input_char_count": 1,
                "output_char_count": len(report),
                "gpu_config": {},
                "device_info": {},
                "static_sanity_ran": False,
                "fixer_ran": False,
                "post_fix_sanity_ran": False,
            }
        )
        return PatchApplyResult(
            run_dir=str(artifacts.root),
            status=status,
            artifact_path=str(artifact_path),
            patch_paths=[str(Path(artifacts.root) / "patches" / "patch_001.diff")],
            files_modified=[] if dry_run else [str(Path(artifacts.root) / "mock_safe_target.txt")],
            backups_created=[] if dry_run else [str(Path(artifacts.root) / "backups" / "mock_safe_target.txt")],
            warnings=[],
            validation_errors=[],
            dry_run=dry_run,
            approved_flag=approve_patches,
            report=report,
        )

    return fake_patch_apply_stage


def test_apply_without_approve_patches_fails_fast(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    with pytest.raises(ValueError, match="approve_patches_flag_missing"):
        runner.run(
            "Apply without approval flag",
            stages=["patch_apply"],
            apply_requested=True,
            approve_patches=False,
            approval_token="I_APPROVE_PATCH_APPLICATION",
        )

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert not (run_dir / "13_patch_apply.md").exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["apply_requested"] is True
    assert summary["approve_patches_flag"] is False
    assert summary["approval_token_provided"] is True
    assert summary["apply_orchestration_valid"] is False
    assert "approve_patches_flag_missing" in summary["apply_orchestration_errors"]
    assert summary["stages_run"] == []


def test_apply_without_approval_token_fails_fast(tmp_path: Path) -> None:
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    with pytest.raises(ValueError, match="approval_token_missing"):
        runner.run(
            "Apply without token",
            stages=["patch_apply"],
            apply_requested=True,
            approve_patches=True,
        )

    run_dir = sorted((tmp_path / "runs").iterdir())[0]
    assert not (run_dir / "13_patch_apply.md").exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["apply_requested"] is True
    assert summary["approve_patches_flag"] is True
    assert summary["approval_token_provided"] is False
    assert summary["apply_orchestration_valid"] is False
    assert "approval_token_missing" in summary["apply_orchestration_errors"]


def test_apply_reorders_human_approval_before_real_patch_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        "agentic_network.pipeline.runner._run_patch_apply_stage",
        _fake_patch_apply_stage_factory(calls),
    )
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Apply with human approval after patch apply in requested stage order",
        stages=[
            "context",
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
            "patch_approval",
            "patch_apply",
            "test_runner",
            "merge_readiness",
            "human_approval",
            "knowledge",
            "handoff",
        ],
        apply_requested=True,
        approve_patches=True,
        approval_token="I_APPROVE_PATCH_APPLICATION",
    )

    assert calls == [(True, True), (True, False)]
    assert result.stages_run.index("test_runner") < result.stages_run.index("merge_readiness")
    assert result.stages_run.index("merge_readiness") < result.stages_run.index("human_approval")
    assert result.stages_run.index("human_approval") < result.stages_run.index("patch_apply")
    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["apply_requested"] is True
    assert summary["approve_patches_flag"] is True
    assert summary["approval_token_provided"] is True
    assert summary["apply_orchestration_valid"] is True
    assert summary["apply_orchestration_errors"] == []
    assert summary["human_approval_decision"] == "Approved"
    assert summary["patch_apply_status"] == "APPLIED"


def test_no_apply_keeps_patch_apply_dry_run_no_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        "agentic_network.pipeline.runner._run_patch_apply_stage",
        _fake_patch_apply_stage_factory(calls),
    )
    runner = PipelineRunner(_config(tmp_path), mock=True, mock_changes_required=False)

    result = runner.run(
        "Dry-run patch apply only",
        stages=["final", "execution", "patch_approval", "patch_apply", "test_runner", "merge_readiness"],
    )

    assert calls == [(False, True)]
    assert result.stages_run.index("patch_apply") < result.stages_run.index("test_runner")
    summary = json.loads((Path(result.output_dir) / "summary.json").read_text(encoding="utf-8"))
    assert summary["apply_requested"] is False
    assert summary["approve_patches_flag"] is False
    assert summary["approval_token_provided"] is False
    assert summary["apply_orchestration_valid"] is True
    assert summary["patch_apply_status"] == "DRY_RUN_PASSED"
