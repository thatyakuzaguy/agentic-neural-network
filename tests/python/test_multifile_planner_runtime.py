from agentic_network.execution_agent.multifile_planner import (
    PLAN_AUTH_GUARD,
    PLAN_PAGINATION,
    PLAN_RATE_LIMITING,
    ROLE_CONFIG_SETTINGS,
    ROLE_MIDDLEWARE,
    ROLE_ROUTE_HANDLER,
    ROLE_SERVICE_LAYER,
    ROLE_TEST_FILE,
    ROLE_UI_COMPONENT,
    plan_multifile_implementation,
)


def _context() -> dict[str, object]:
    return {
        "recommended_patch_targets": [
            "app/ui/password_reset_form.tsx",
            "app/middleware/auth_guard.py",
            "app/routes/auth.py",
            "app/services/auth_service.py",
            "app/core/settings.py",
            "tests/test_auth.py",
            "app/routes/products.py",
            "app/services/product_search.py",
            "tests/test_products.py",
        ],
        "matched_files": [
            "app/ui/password_reset_form.tsx",
            "app/middleware/auth_guard.py",
            "app/routes/auth.py",
            "app/services/auth_service.py",
            "app/core/settings.py",
            "tests/test_auth.py",
            "app/routes/products.py",
            "app/services/product_search.py",
            "tests/test_products.py",
        ],
        "matched_routes": [
            {"path": "/password/reset", "file": "app/routes/auth.py", "handler": "password_reset"},
            {"path": "/products", "file": "app/routes/products.py", "handler": "search_products"},
        ],
        "matched_functions": [
            {"name": "send_password_reset", "file": "app/services/auth_service.py"},
            {"name": "search_products", "file": "app/services/product_search.py"},
        ],
        "matched_tests": ["tests/test_auth.py", "tests/test_products.py"],
        "dependency_paths": ["app/services/auth_service.py", "app/core/settings.py"],
    }


def test_rate_limiting_plan_selects_config_service_route_and_tests() -> None:
    result = plan_multifile_implementation(
        task="Add rate limits to password reset requests",
        repository_context=_context(),
        artifact_context="Password reset abuse prevention needs settings and tests.",
        experience_context="REUSABLE CONSTANTS\n- WINDOW_SECONDS=7200\n",
    )

    assert result.plan_type == PLAN_RATE_LIMITING
    assert result.confidence == "High"
    assert result.missing_layers == []
    assert result.file_roles["app/core/settings.py"] == ROLE_CONFIG_SETTINGS
    assert result.file_roles["app/services/auth_service.py"] == ROLE_SERVICE_LAYER
    assert result.file_roles["app/routes/auth.py"] == ROLE_ROUTE_HANDLER
    assert result.file_roles["tests/test_auth.py"] == ROLE_TEST_FILE
    assert result.implementation_order == [
        "app/core/settings.py",
        "app/services/auth_service.py",
        "app/routes/auth.py",
        "tests/test_auth.py",
    ]


def test_rate_limiting_records_missing_route_and_service_when_absent() -> None:
    context = {
        "matched_files": ["app/core/settings.py", "tests/test_auth.py"],
        "matched_tests": ["tests/test_auth.py"],
    }

    result = plan_multifile_implementation(
        task="Add rate limits to password reset requests",
        repository_context=context,
        artifact_context="",
        experience_context="",
    )

    assert result.plan_type == PLAN_RATE_LIMITING
    assert result.selected_files == ["app/core/settings.py", "tests/test_auth.py"]
    assert result.missing_layers == [ROLE_SERVICE_LAYER, ROLE_ROUTE_HANDLER]


def test_pagination_plan_selects_route_service_and_tests_without_ui() -> None:
    result = plan_multifile_implementation(
        task="Support pagination for product search",
        repository_context=_context(),
        artifact_context="Product search should paginate backend results.",
        experience_context="",
    )

    assert result.plan_type == PLAN_PAGINATION
    assert "app/routes/products.py" in result.selected_files
    assert "app/services/product_search.py" in result.selected_files
    assert "tests/test_products.py" in result.selected_files
    assert "app/ui/password_reset_form.tsx" not in result.selected_files
    assert ROLE_UI_COMPONENT not in result.file_roles.values()


def test_auth_guard_plan_selects_middleware_service_route_and_tests() -> None:
    result = plan_multifile_implementation(
        task="Add auth guard enforcement for password reset",
        repository_context=_context(),
        artifact_context="Auth guard should use middleware when available.",
        experience_context="",
    )

    assert result.plan_type == PLAN_AUTH_GUARD
    assert result.file_roles["app/middleware/auth_guard.py"] == ROLE_MIDDLEWARE
    assert result.file_roles["app/services/auth_service.py"] == ROLE_SERVICE_LAYER
    assert result.file_roles["app/routes/auth.py"] == ROLE_ROUTE_HANDLER
    assert result.file_roles["tests/test_auth.py"] == ROLE_TEST_FILE


def test_ui_component_allowed_when_frontend_is_explicit() -> None:
    result = plan_multifile_implementation(
        task="Support pagination for product search in the frontend UI",
        repository_context={
            **_context(),
            "matched_files": [*_context()["matched_files"], "app/ui/product_search.tsx"],
            "recommended_patch_targets": [*_context()["recommended_patch_targets"], "app/ui/product_search.tsx"],
        },
        artifact_context="",
        experience_context="",
    )

    assert "app/ui/product_search.tsx" in result.selected_files
    assert result.file_roles["app/ui/product_search.tsx"] == ROLE_UI_COMPONENT
