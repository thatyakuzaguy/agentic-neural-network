from pathlib import Path

from agentic_network.execution_agent.runtime import (
    generate_execution_plan,
    parse_execution_plan_sections,
    validate_execution_plan,
)
from agentic_network.execution_agent.synthesizer import (
    STRATEGY_FASTAPI_ROUTE_EXTENSION,
    STRATEGY_PYTEST_IMPLEMENTATION,
    STRATEGY_PYTHON_AUTH_GUARD,
    STRATEGY_PYTHON_PAGINATION,
    STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION,
    STRATEGY_REJECTED,
    synthesize_patch,
)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _context(*items: str) -> str:
    return "\n".join(items)


def test_rate_limit_behavior_patch_reuses_memory_constants(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "app" / "auth" / "password_reset.py", "def send_password_reset(email):\n    return True\n")

    result = synthesize_patch(
        target,
        artifact_context=_context(
            "Add password reset rate limits with max attempts and reset expiration.",
            "REUSABLE CONSTANTS",
            "- MAX_ATTEMPTS=7",
            "- WINDOW_SECONDS=7200",
            "- THRESHOLD=11",
        ),
        repository_context={"project_root": str(repo)},
    )

    assert result.success is True
    assert result.strategy == STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION
    assert result.unified_diff.startswith("--- a/app/auth/password_reset.py\n+++ b/app/auth/password_reset.py")
    assert "+PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 7" in result.unified_diff
    assert "+PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 7200" in result.unified_diff
    assert "+PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD = 11" in result.unified_diff
    assert "hashlib.sha256" in result.unified_diff
    assert "If an account exists" in result.unified_diff
    assert target.read_text(encoding="utf-8") == "def send_password_reset(email):\n    return True\n"


def test_auth_guard_behavior_patch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "app" / "auth" / "guards.py", "class User:\n    pass\n")

    result = synthesize_patch(
        target,
        artifact_context="Add auth guard permission checks, failed login counters, and session expiration logic.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is True
    assert result.strategy == STRATEGY_PYTHON_AUTH_GUARD
    assert "+def require_permission(permission):" in result.unified_diff
    assert "+def record_failed_login(identifier, now=None):" in result.unified_diff
    assert "+def session_is_active(session, now=None):" in result.unified_diff


def test_pagination_behavior_patch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "app" / "catalog.py", "def list_products():\n    return []\n")

    result = synthesize_patch(
        target,
        artifact_context="Implement pagination with page, page_size, max_page_size, next_cursor, previous_cursor.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is True
    assert result.strategy == STRATEGY_PYTHON_PAGINATION
    assert "+def paginate_items(items, page=1, page_size=20, max_page_size=100):" in result.unified_diff
    assert '+        "next_cursor": next_cursor' in result.unified_diff
    assert '+        "previous_cursor": previous_cursor' in result.unified_diff


def test_fastapi_route_extension_preserves_route_style(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(
        repo / "app" / "routes.py",
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
    )

    result = synthesize_patch(
        target,
        artifact_context="Extend FastAPI routes with request schemas, response schemas, and validation blocks.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is True
    assert result.strategy == STRATEGY_FASTAPI_ROUTE_EXTENSION
    assert "+class PasswordResetRequest(BaseModel):" in result.unified_diff
    assert '+@app.post("/password-reset", response_model=PasswordResetResponse)' in result.unified_diff
    assert "+def create_password_reset(request: PasswordResetRequest):" in result.unified_diff


def test_pytest_generation_patch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "tests" / "test_password_reset.py", "def test_existing():\n    assert True\n")

    result = synthesize_patch(
        target,
        artifact_context="Generate pytest tests for happy path, edge cases, invalid inputs, security tests, regression tests.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is True
    assert result.strategy == STRATEGY_PYTEST_IMPLEMENTATION
    assert "+def test_password_reset_rate_limit_happy_path():" in result.unified_diff
    assert "+def test_password_reset_rejects_invalid_identifier():" in result.unified_diff
    assert "+def test_password_reset_uses_generic_security_response():" in result.unified_diff
    assert "+def test_password_reset_regression_window_is_positive():" in result.unified_diff


def test_execution_runtime_marks_real_behavior_and_memory_use(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _write(repo / "app" / "auth" / "password_reset.py", "def send_password_reset(email):\n    return True\n")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "03_code_revised.md").write_text(
        "FILES TO MODIFY\n"
        "- app/auth/password_reset.py\n\n"
        "NEW FILES\n"
        "- None\n\n"
        "CODE CHANGES\n"
        "- Add password reset rate limits with max attempts, windows, expiration, and generic responses.\n\n"
        "TESTS TO ADD\n"
        "- Verify rate limited requests are blocked.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    (run_dir / "04_tests_revised.md").write_text("TEST SCENARIOS\n- Rate limit edge cases.\n\nCONFIDENCE\nHigh\n", encoding="utf-8")
    (run_dir / "05_security_revised.md").write_text("SECURITY FINDINGS\n- Preserve generic responses.\n\nCONFIDENCE\nHigh\n", encoding="utf-8")
    (run_dir / "08_final_review.md").write_text("FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh\n", encoding="utf-8")
    (run_dir / "24_experience_context.md").write_text(
        "EXPERIENCE CONTEXT\n"
        "- Retrieved engineering experience.\n\n"
        "REUSABLE PATTERNS\n"
        "- rate_limiting_engineering_experience\n\n"
        "REUSABLE CONSTANTS\n"
        "- MAX_ATTEMPTS=7\n"
        "- WINDOW_SECONDS=7200\n"
        "- THRESHOLD=11\n\n"
        "RELEVANT REPAIRS\n"
        "- Previous rate limiting repair.\n\n"
        "RECOMMENDED REUSE\n"
        "- Prefer stored constants.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.validation_errors == []
    assert result.behavior_synthesized is True
    assert result.behavior_strategy == STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION
    assert result.real_implementation is True
    assert result.memory_used is True
    assert result.memory_patterns_used == ["rate_limiting_engineering_experience"]


def test_invalid_python_target_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "app" / "broken.py", "def broken(:\n    pass\n")

    result = synthesize_patch(
        target,
        artifact_context="Implement pagination with page_size and next_cursor.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert result.fallback_reason == "invalid_python_before"
    assert result.unified_diff == ""


def test_forbidden_commands_are_rejected_by_execution_validation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write(repo / "app" / "safe.py", "VALUE = 1\n")
    plan = """EXECUTION SUMMARY
- Safe summary.

FILES TO MODIFY
- app/safe.py

FILES TO CREATE
- None

FILES TO REVIEW
- app/safe.py

PATCH STRATEGY
- Review unified diffs only.

EXPECTED TEST IMPACT
- Tests remain review-only.

SECURITY CONSIDERATIONS
- Avoid dangerous commands.

EXECUTION CONFIDENCE
High"""
    patch = "--- a/app/safe.py\n+++ b/app/safe.py\n@@ -1,1 +1,2 @@\n VALUE = 1\n+os.system('echo unsafe')\n"

    errors = validate_execution_plan(
        execution_plan=plan,
        parsed_sections=parse_execution_plan_sections(plan),
        patch_texts=[patch],
        project_root=repo,
    )

    assert "executable_command_present" in errors


def test_protected_path_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _write(repo / "training" / "datasets" / "generated.py", "VALUE = 1\n")

    result = synthesize_patch(
        target,
        artifact_context="Implement pagination with page_size and next_cursor.",
        repository_context={"project_root": str(repo)},
    )

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert "protected_path_modified" in result.fallback_reason
