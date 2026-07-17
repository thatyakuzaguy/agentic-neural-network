import ast
from pathlib import Path

from agentic_network.execution_agent.layer_creation_planner import (
    plan_missing_layers,
    render_creation_patch,
)
from agentic_network.execution_agent.multifile_planner import MultiFilePlanResult


def _plan(missing_layers: list[str]) -> MultiFilePlanResult:
    return MultiFilePlanResult(
        plan_type="RATE_LIMITING_FEATURE",
        selected_files=[],
        file_roles={},
        implementation_order=[],
        rationale=[],
        missing_layers=missing_layers,
        confidence="Medium",
    )


def _context(project_root: Path, files: list[str], directories: list[str]) -> dict[str, object]:
    return {
        "project_root": str(project_root),
        "repository_files": files,
        "repository_directories": directories,
    }


def test_missing_service_layer_proposes_services_file_when_services_dir_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = plan_missing_layers(
        task="Add rate limits to password reset requests.",
        repository_context=_context(repo, ["tests/test_auth.py"], ["app/services", "tests"]),
        multifile_plan=_plan(["SERVICE_LAYER"]),
        artifact_context="Backend password reset abuse prevention.",
        experience_context="",
    )

    assert result.proposed_files == ["app/services/password_reset_rate_limit.py"]
    assert result.proposed_roles["app/services/password_reset_rate_limit.py"] == "SERVICE_LAYER"
    assert result.validation_errors == []


def test_missing_test_file_proposes_pytest_file_when_tests_dir_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = plan_missing_layers(
        task="Add auth rate limits.",
        repository_context=_context(repo, ["tests/test_existing.py"], ["tests"]),
        multifile_plan=_plan(["TEST_FILE"]),
        artifact_context="TESTS TO ADD\n- Cover rate limiting.",
        experience_context="",
    )

    assert result.proposed_files == ["tests/test_auth_rate_limit.py"]
    assert result.proposed_roles["tests/test_auth_rate_limit.py"] == "TEST_FILE"


def test_route_handler_proposed_only_when_routes_dir_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    without_routes = plan_missing_layers(
        task="Add API route for password reset rate limits.",
        repository_context=_context(repo, [], ["app/services"]),
        multifile_plan=_plan(["ROUTE_HANDLER"]),
        artifact_context="",
        experience_context="",
    )
    with_routes = plan_missing_layers(
        task="Add API route for password reset rate limits.",
        repository_context=_context(repo, [], ["app/routes", "app/services"]),
        multifile_plan=_plan(["ROUTE_HANDLER"]),
        artifact_context="",
        experience_context="",
    )

    assert without_routes.proposed_files == []
    assert without_routes.rejected_layers["ROUTE_HANDLER"] == "no_existing_route_or_router_structure"
    assert with_routes.proposed_files == ["app/routes/auth.py"]


def test_no_proposal_under_protected_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = plan_missing_layers(
        task="Document rate limit behavior.",
        repository_context=_context(repo, [], ["memory/docs", "outputs/docs"]),
        multifile_plan=_plan(["DOCUMENTATION"]),
        artifact_context="Documentation only.",
        experience_context="",
    )

    assert result.proposed_files == []
    assert result.rejected_layers["DOCUMENTATION"] == "docs_directory_missing"


def test_path_traversal_from_task_is_sanitized(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = plan_missing_layers(
        task="../escape password reset rate limits",
        repository_context=_context(repo, ["tests/test_existing.py"], ["app/services", "tests"]),
        multifile_plan=_plan(["SERVICE_LAYER"]),
        artifact_context="Backend behavior.",
        experience_context="",
    )

    assert result.proposed_files
    assert all(".." not in Path(path).parts for path in result.proposed_files)
    assert result.validation_errors == []


def test_no_duplicate_if_matching_service_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = plan_missing_layers(
        task="Add rate limits to password reset requests.",
        repository_context=_context(
            repo,
            ["app/services/password_reset_rate_limit.py", "tests/test_auth.py"],
            ["app/services", "tests"],
        ),
        multifile_plan=_plan(["SERVICE_LAYER"]),
        artifact_context="Backend behavior.",
        experience_context="",
    )

    assert result.proposed_files == []
    assert result.rejected_layers["SERVICE_LAYER"] == "matching_service_file_already_exists"


def test_creation_patch_uses_dev_null_and_python_ast_is_valid() -> None:
    patch = render_creation_patch(
        "app/services/password_reset_rate_limit.py",
        "SERVICE_LAYER",
        "Add rate limits to password reset requests.",
    )
    additions = "\n".join(
        line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
    )

    assert patch.startswith("--- /dev/null\n+++ b/app/services/password_reset_rate_limit.py\n@@")
    ast.parse(additions)
