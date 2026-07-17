import json
from pathlib import Path

from agentic_network.execution_agent.runtime import (
    EXECUTION_PLAN_OUTPUT_FILE,
    TARGET_CONFIG_SETTINGS,
    TARGET_MIDDLEWARE,
    TARGET_ROUTE_HANDLER,
    TARGET_SERVICE_LAYER,
    TARGET_TEST_FILE,
    TARGET_UI_COMPONENT,
    classify_patch_target,
    generate_execution_plan,
    parse_execution_plan_sections,
    select_patch_targets_from_repository_context,
    validate_execution_plan,
)
from agentic_network.patch_approval_agent.runtime import approve_patches
from agentic_network.patch_apply_agent.runtime import (
    APPLY_STATUS_APPLIED,
    APPLY_STATUS_DRY_RUN_PASSED,
    apply_approved_patches,
)
from agentic_network.repository_intelligence_agent.runtime import build_repository_intelligence


def _write_repo(repo: Path) -> Path:
    target = repo / "app" / "auth" / "password_reset.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def send_password_reset(user_email):\n"
        "    return True\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_password_reset.py").write_text(
        "def test_password_reset_allowed():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    protected = repo / "training" / "datasets"
    protected.mkdir(parents=True, exist_ok=True)
    (protected / "secret.jsonl").write_text("{}\n", encoding="utf-8")
    return target


def _write_run(run_dir: Path, *, decision: str = "Approved", file_hint: str | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    modify_item = file_hint or "Candidate: password reset request handling module."
    (run_dir / "03_code_revised.md").write_text(
        "FILES TO MODIFY\n"
        f"- {modify_item}\n\n"
        "NEW FILES\n"
        "- Candidate: tests for password reset rate-limit behavior.\n\n"
        "CODE CHANGES\n"
        "- Add configurable retry windows.\n"
        "- Add escalation thresholds for repeated or severe cases.\n"
        "- Account for identifier rotation handling.\n\n"
        "TESTS TO ADD\n"
        "- Verify excessive reset attempts are blocked.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "04_tests_revised.md").write_text(
        "TEST SCENARIOS\n"
        "- Verify excessive reset attempts are blocked.\n"
        "- Verify legitimate reset attempts are allowed.\n\n"
        "TEST CASES\n"
        "- User reaches the configured reset limit and receives clear feedback.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "05_security_revised.md").write_text(
        "SECURITY FINDINGS\n"
        "- Password reset abuse should be mitigated.\n\n"
        "MITIGATIONS\n"
        "- Preserve generic user-facing feedback for sensitive flows.\n\n"
        "RESIDUAL RISKS\n"
        "- Distributed abuse may still require monitoring.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "08_final_review.md").write_text(
        "FINAL ASSESSMENT\n"
        "- Artifacts are internally consistent.\n\n"
        "FINAL DECISION\n"
        f"{decision}\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )


def _target_selection_context() -> dict[str, object]:
    return {
        "recommended_patch_targets": [
            "app/ui/password_reset_form.tsx",
            "app/middleware/rate_limit.py",
            "app/routes/auth.py",
            "app/services/reset_service.py",
            "app/core/config.py",
            "tests/test_auth.py",
        ],
        "matched_files": [
            "app/ui/password_reset_form.tsx",
            "app/middleware/rate_limit.py",
            "app/routes/auth.py",
            "app/services/reset_service.py",
            "app/core/config.py",
            "tests/test_auth.py",
            "app/unrelated.py",
        ],
        "matched_routes": [
            {
                "path": "/password/reset",
                "method": "POST",
                "handler": "password_reset",
                "file": "app/routes/auth.py",
            }
        ],
        "matched_functions": [
            {"name": "password_reset", "file": "app/routes/auth.py"},
            {"name": "check_password_reset_rate_limit", "file": "app/services/reset_service.py"},
        ],
        "matched_classes": [],
        "matched_tests": ["tests/test_auth.py"],
        "dependency_paths": ["app/services/reset_service.py", "app/core/config.py"],
    }


def test_target_classification_layers() -> None:
    route_files = {"app/routes/auth.py"}

    assert classify_patch_target("app/routes/auth.py", route_files=route_files) == TARGET_ROUTE_HANDLER
    assert classify_patch_target("app/services/reset_service.py") == TARGET_SERVICE_LAYER
    assert classify_patch_target("app/core/config.py") == TARGET_CONFIG_SETTINGS
    assert classify_patch_target("app/middleware/rate_limit.py") == TARGET_MIDDLEWARE
    assert classify_patch_target("app/ui/password_reset_form.tsx") == TARGET_UI_COMPONENT
    assert classify_patch_target("tests/test_auth.py") == TARGET_TEST_FILE


def test_repository_context_selector_prefers_service_route_config_over_ui_for_backend_task() -> None:
    result = select_patch_targets_from_repository_context(
        "Add rate limits to password reset requests",
        _target_selection_context(),
        "Password reset abuse prevention should reuse config constants.",
    )

    assert result.confidence == "High"
    assert "app/services/reset_service.py" in result.selected_targets
    assert "app/core/config.py" in result.selected_targets
    assert "app/ui/password_reset_form.tsx" in result.rejected_targets
    assert "app/middleware/rate_limit.py" in result.rejected_targets
    assert result.target_classes["app/services/reset_service.py"] == TARGET_SERVICE_LAYER
    assert result.target_classes["app/core/config.py"] == TARGET_CONFIG_SETTINGS


def test_repository_context_selector_allows_middleware_when_explicitly_requested() -> None:
    result = select_patch_targets_from_repository_context(
        "Add password reset rate limits in middleware",
        _target_selection_context(),
        "The architecture requires middleware throttling.",
    )

    assert "app/middleware/rate_limit.py" in result.selected_targets
    assert "app/middleware/rate_limit.py" not in result.rejected_targets


def test_repository_context_selector_rejects_frontend_for_backend_task() -> None:
    result = select_patch_targets_from_repository_context(
        "Add abuse prevention for password reset",
        _target_selection_context(),
        "Backend security mitigation only.",
    )

    assert "app/ui/password_reset_form.tsx" in result.rejected_targets
    assert "app/ui/password_reset_form.tsx" not in result.selected_targets


def test_repository_context_selector_can_select_tests_for_test_strategy() -> None:
    result = select_patch_targets_from_repository_context(
        "Add rate limits to password reset requests and tests",
        _target_selection_context(),
        "TESTS TO ADD\n- Add pytest regression coverage.",
    )

    assert "tests/test_auth.py" in result.selected_targets
    assert result.target_classes["tests/test_auth.py"] == TARGET_TEST_FILE


def test_approved_run_generates_source_aware_execution_plan(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    (run_dir / "00_user_request.md").write_text(
        "Add rate limits to password reset requests.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.refused is False
    assert result.final_decision == "Approved"
    assert result.validation_errors == []
    assert result.validation_passed is True
    assert result.source_aware is True
    assert result.patch_count >= 1
    assert result.applicable_patch_count == result.patch_count
    assert "app/auth/password_reset.py" in result.candidate_files
    assert (run_dir / EXECUTION_PLAN_OUTPUT_FILE).exists()
    parsed = parse_execution_plan_sections(result.execution_plan)
    assert parsed["execution_confidence"] == "High"
    assert parsed["execution_summary"]


def test_execution_agent_uses_experience_context_constants(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = repo / "agentic_network" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("APP_NAME = 'ANN'\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved", file_hint="agentic_network/config.py")
    (run_dir / "24_experience_context.md").write_text(
        "EXPERIENCE CONTEXT\n"
        "- Retrieved engineering experience for: Add rate limits.\n\n"
        "REUSABLE PATTERNS\n"
        "- nameerror_missing_constant\n\n"
        "REUSABLE CONSTANTS\n"
        "- WINDOW_SECONDS=7200\n"
        "- MAX_ATTEMPTS=7\n"
        "- THRESHOLD=11\n\n"
        "RELEVANT REPAIRS\n"
        "- Add rate limits using add_constant\n\n"
        "RECOMMENDED REUSE\n"
        "- Prefer retrieved constants.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.validation_errors == []
    assert result.memory_used is True
    assert result.memory_patterns_used == ["nameerror_missing_constant"]
    patch_text = "\n".join(Path(path).read_text(encoding="utf-8") for path in result.patch_paths)
    assert "+PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 7" in patch_text
    assert "+PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 7200" in patch_text
    assert "+PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD = 11" in patch_text


def test_execution_agent_uses_repository_intelligence_for_routes_and_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    route = repo / "app" / "routes" / "auth.py"
    route.parent.mkdir(parents=True)
    route.write_text(
        "from app.services.reset_service import send_reset_email\n\n"
        "def password_reset(email):\n"
        "    send_reset_email(email)\n"
        "    return {'accepted': True}\n",
        encoding="utf-8",
    )
    service = repo / "app" / "services" / "reset_service.py"
    service.parent.mkdir(parents=True)
    service.write_text(
        "def send_reset_email(email):\n"
        "    return None\n",
        encoding="utf-8",
    )
    tests = repo / "tests" / "test_auth.py"
    tests.parent.mkdir()
    tests.write_text(
        "def test_password_reset():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    intelligence_dir = run_dir / "repository_intelligence"
    build_repository_intelligence(repo, intelligence_dir)
    routes = json.loads((intelligence_dir / "routes.json").read_text(encoding="utf-8"))
    routes.append(
        {
            "path": "/password/reset",
            "method": "POST",
            "handler": "password_reset",
            "file": "app/routes/auth.py",
            "line": 3,
            "router": "router",
        }
    )
    (intelligence_dir / "routes.json").write_text(json.dumps(routes, indent=2), encoding="utf-8")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.repository_intelligence_used is True
    assert result.route_detected is True
    assert result.dependency_path_found is True
    assert result.candidate_files[:2] == [
        "app/routes/auth.py",
        "app/services/reset_service.py",
    ]
    assert "tests/test_auth.py" in result.candidate_files


def test_execution_summary_uses_repository_aware_target_selection(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)

    def _write(relative: str, content: str) -> None:
        (repo / relative).write_text(content, encoding="utf-8")

    (repo / "app" / "routes").mkdir(parents=True, exist_ok=True)
    _write("app/routes/auth.py", "def password_reset(email):\n    return {'accepted': True}\n")
    (repo / "app" / "services").mkdir(parents=True, exist_ok=True)
    _write("app/services/reset_service.py", "def check_password_reset_rate_limit(email):\n    return {'allowed': True}\n")
    (repo / "app" / "core").mkdir(parents=True, exist_ok=True)
    _write("app/core/config.py", "APP_NAME = 'test'\n")
    (repo / "app" / "ui").mkdir(parents=True, exist_ok=True)
    _write("app/ui/password_reset_form.tsx", "export function PasswordResetForm() { return null }\n")
    (repo / "app" / "middleware").mkdir(parents=True, exist_ok=True)
    _write("app/middleware/rate_limit.py", "def middleware(request):\n    return request\n")
    _write("tests/test_auth.py", "def test_password_reset():\n    assert True\n")
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    (run_dir / "00_user_request.md").write_text(
        "Add rate limits to password reset requests.\n",
        encoding="utf-8",
    )
    (run_dir / "26_repository_context.json").write_text(
        json.dumps(_target_selection_context(), indent=2),
        encoding="utf-8",
    )
    (run_dir / "26_repository_context.md").write_text("REPOSITORY CONTEXT\nCONFIDENCE High\n", encoding="utf-8")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.target_selection_used is True
    assert result.target_selection_confidence == "High"
    assert set(result.selected_targets or []) <= set(result.candidate_files or [])
    assert result.multifile_plan_used is True
    assert result.multifile_plan_type == "RATE_LIMITING_FEATURE"
    assert result.multifile_missing_layers == []
    assert result.multifile_file_roles == {
        "app/core/config.py": "CONFIG_SETTINGS",
        "app/services/reset_service.py": "SERVICE_LAYER",
        "app/routes/auth.py": "ROUTE_HANDLER",
        "tests/test_auth.py": "TEST_FILE",
    }
    assert result.multifile_implementation_order == [
        "app/core/config.py",
        "app/services/reset_service.py",
        "app/routes/auth.py",
        "tests/test_auth.py",
    ]
    assert result.candidate_files == result.multifile_implementation_order
    assert "app/services/reset_service.py" in result.selected_targets
    assert "app/core/config.py" in result.selected_targets
    assert "app/ui/password_reset_form.tsx" in result.rejected_targets
    assert "app/middleware/rate_limit.py" in result.rejected_targets
    assert result.target_classes["app/ui/password_reset_form.tsx"] == TARGET_UI_COMPONENT


def test_execution_agent_writes_files_to_create_for_layer_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def _write(relative: str, content: str) -> None:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _write("app/routes/auth.py", "def password_reset(email):\n    return {'accepted': True}\n")
    (repo / "app" / "services").mkdir(parents=True, exist_ok=True)
    _write("app/core/config.py", "APP_NAME = 'test'\n")
    _write("tests/test_auth.py", "def test_password_reset():\n    assert True\n")
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    (run_dir / "00_user_request.md").write_text(
        "Add rate limits to password reset requests.\n",
        encoding="utf-8",
    )
    (run_dir / "26_repository_context.json").write_text(
        json.dumps(
            {
                "recommended_patch_targets": [
                    "app/core/config.py",
                    "app/routes/auth.py",
                    "tests/test_auth.py",
                ],
                "matched_files": [
                    "app/core/config.py",
                    "app/routes/auth.py",
                    "tests/test_auth.py",
                ],
                "matched_routes": [
                    {
                        "path": "/password/reset",
                        "method": "POST",
                        "handler": "password_reset",
                        "file": "app/routes/auth.py",
                    }
                ],
                "matched_tests": ["tests/test_auth.py"],
                "dependency_paths": ["app/core/config.py"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)
    parsed = parse_execution_plan_sections(result.execution_plan)
    patch_text = "\n".join(Path(path).read_text(encoding="utf-8") for path in result.patch_paths)

    assert result.validation_errors == []
    assert result.layer_creation_used is True
    assert result.layer_proposed_files == ["app/services/password_reset_rate_limit.py"]
    assert "app/services/password_reset_rate_limit.py" in parsed["files_to_create"]
    assert "--- /dev/null\n+++ b/app/services/password_reset_rate_limit.py" in patch_text
    assert not (repo / "app" / "services" / "password_reset_rate_limit.py").exists()


def test_rejected_run_refuses_generation(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Rejected")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.refused is True
    assert result.patch_paths == []
    assert "final_decision_not_approved" in result.validation_errors
    assert "Refused patch proposal generation" in result.execution_plan
    assert (run_dir / EXECUTION_PLAN_OUTPUT_FILE).exists()
    assert not (run_dir / "patches").exists()


def test_patch_files_are_created_under_run_directory_with_real_paths(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    patch_contents = []
    for patch_path_value in result.patch_paths:
        patch_path = Path(patch_path_value)
        assert run_dir in patch_path.parents
        assert patch_path.parent == run_dir / "patches"
        content = patch_path.read_text(encoding="utf-8")
        patch_contents.append(content)
        assert "--- old" not in content
        assert "+++ new" not in content
        assert content.startswith("--- a/")
        assert "\n+++ b/" in content
    source_patch = "\n".join(patch_contents)
    assert "--- a/app/auth/password_reset.py" in source_patch
    assert "+++ b/app/auth/password_reset.py" in source_patch
    assert "def send_password_reset(user_email):" in source_patch
    assert "def send_password_reset(user_email):" in target.read_text(encoding="utf-8")
    assert sorted(path.name for path in (run_dir / "patches").glob("*.diff"))


def test_patch_validation_rejects_commands_and_forbidden_paths(tmp_path: Path) -> None:
    plan = """EXECUTION SUMMARY
- Safe summary.

FILES TO MODIFY
- Candidate: module.

FILES TO CREATE
- None

FILES TO REVIEW
- Candidate: module.

PATCH STRATEGY
- Keep proposal reviewable.

EXPECTED TEST IMPACT
- Review behavior tests.

SECURITY CONSIDERATIONS
- Avoid sensitive output.

EXECUTION CONFIDENCE
High"""
    parsed = parse_execution_plan_sections(plan)

    errors = validate_execution_plan(
        execution_plan=plan + "\n- sudo rm /mnt/c/tmp/file",
        parsed_sections=parsed,
        patch_texts=["--- a/app/safe.py\n+++ b/app/safe.py\n@@ -1,1 +1,2 @@\n+ chmod 777 /mnt/e/outside"],
        project_root=tmp_path,
    )

    assert "executable_command_present" in errors
    assert "forbidden_c_path_present" in errors
    assert any(error.startswith("path_outside_project_root:") for error in errors)


def test_protected_paths_are_excluded_from_candidates(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved", file_hint="training/datasets/secret.jsonl")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert all("training/datasets" not in candidate for candidate in (result.candidate_files or []))
    for patch_path in result.patch_paths:
        assert "training/datasets" not in Path(patch_path).read_text(encoding="utf-8")


def test_no_applicable_target_produces_safe_no_patch_status(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("Project notes\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved", file_hint="Candidate: orbital mechanics rendering module.")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.validation_passed is True
    assert result.patch_paths == []
    assert result.applicable_patch_count == 0
    assert result.no_target_reason == "no_safe_repository_target_matched_artifacts"
    assert not (run_dir / "patches").exists()


def test_patch_approval_accepts_source_aware_safe_patch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)
    monkeypatch.setattr("agentic_network.patch_approval_agent.runtime._project_root", lambda: repo)

    generate_execution_plan(run_dir)
    result = approve_patches(run_dir)

    assert result.decision == "Approved"
    assert result.validation_errors == []




def _write_patch_apply_summary(run_dir: Path) -> None:
    (run_dir / "summary.json").write_text(
        '{"final_decision":"Approved","patch_approval_decision":"Approved",'
        '"patch_approval_validation_passed":true,"human_approval_decision":"Approved",'
        '"human_approval_validation_passed":true}',
        encoding="utf-8",
    )
    (run_dir / "16_human_approval.md").write_text(
        "AUTHORIZATION DECISION\nApproved\n",
        encoding="utf-8",
    )


def test_patch_apply_dry_run_validates_source_aware_patch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)
    monkeypatch.setattr("agentic_network.patch_approval_agent.runtime._project_root", lambda: repo)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    generate_execution_plan(run_dir)
    approval = approve_patches(run_dir)
    assert approval.validation_passed is True
    _write_patch_apply_summary(run_dir)
    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=True)

    assert result.status == APPLY_STATUS_DRY_RUN_PASSED
    assert result.validation_errors == []
    assert "ANN patch proposal" not in (repo / "app" / "auth" / "password_reset.py").read_text(encoding="utf-8")


def test_patch_apply_approved_path_can_apply_in_sandbox(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)
    monkeypatch.setattr("agentic_network.patch_approval_agent.runtime._project_root", lambda: repo)
    monkeypatch.setattr("agentic_network.patch_apply_agent.runtime._project_root", lambda: repo)

    generate_execution_plan(run_dir)
    approval = approve_patches(run_dir)
    assert approval.validation_passed is True
    _write_patch_apply_summary(run_dir)

    result = apply_approved_patches(run_dir, approve_patches=True, dry_run=False)

    assert result.status == APPLY_STATUS_APPLIED
    assert result.validation_errors == []
    applied_source = target.read_text(encoding="utf-8")
    assert "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS" in applied_source
    assert "check_password_reset_rate_limit" in applied_source
    assert len(result.backups_created) >= 1


def test_execution_agent_does_not_modify_repository_files(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _write_repo(repo)
    before = target.read_text(encoding="utf-8")
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.validation_passed is True
    assert target.read_text(encoding="utf-8") == before


def test_execution_agent_has_no_model_runtime_dependency(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    run_dir = tmp_path / "run"
    _write_run(run_dir, decision="Approved")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    def explode(*_args, **_kwargs):
        raise AssertionError("Execution Agent must not load a model")

    monkeypatch.setattr("agentic_network.pipeline.runner.Qwen3Model", explode, raising=False)
    monkeypatch.setattr("agentic_network.pipeline.runner.QwenUnslothModel", explode, raising=False)

    result = generate_execution_plan(run_dir)

    assert result.validation_passed is True
