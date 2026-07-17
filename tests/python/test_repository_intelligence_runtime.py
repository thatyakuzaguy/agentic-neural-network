from __future__ import annotations

import json
import textwrap
from pathlib import Path

from agentic_network.repository_intelligence_agent.runtime import (
    build_repository_intelligence,
    validate_repository_intelligence,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _sample_project(root: Path) -> None:
    _write(
        root / "app" / "routes" / "auth.py",
        """
        from fastapi import APIRouter
        from app.services.reset_service import send_reset_email, check_password_reset_rate_limit

        router = APIRouter()

        @router.post("/password/reset")
        def password_reset(email: str) -> dict:
            result = check_password_reset_rate_limit(email)
            if result["allowed"]:
                send_reset_email(email)
            return result
        """,
    )
    _write(
        root / "app" / "services" / "reset_service.py",
        """
        class ResetLimiter:
            def allow(self, identifier: str) -> bool:
                return True

        def check_password_reset_rate_limit(identifier: str) -> dict:
            limiter = ResetLimiter()
            return {"allowed": limiter.allow(identifier)}

        def send_reset_email(email: str) -> None:
            return None
        """,
    )
    _write(
        root / "app" / "main.py",
        """
        from fastapi import FastAPI
        from app.routes.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        """,
    )
    _write(
        root / "tests" / "test_auth.py",
        """
        from app.routes.auth import password_reset

        def test_password_reset_allowed():
            assert password_reset("user@example.com")["allowed"] is True
        """,
    )
    _write(root / "package.json", '{"name": "sample"}')
    _write(root / "docs" / "notes.md", "# Notes")


def _load(output_dir: Path, name: str):
    return json.loads((output_dir / name).read_text(encoding="utf-8"))


def test_python_function_and_class_extraction(tmp_path: Path) -> None:
    _sample_project(tmp_path)

    result = build_repository_intelligence(tmp_path, tmp_path / "ri")

    functions = _load(Path(result.output_dir), "functions.json")
    classes = _load(Path(result.output_dir), "classes.json")
    names = {item["name"] for item in functions}
    assert "password_reset" in names
    assert "check_password_reset_rate_limit" in names
    assert any(item["name"] == "ResetLimiter" and "allow" in item["methods"] for item in classes)
    assert result.functions >= 4
    assert result.classes == 1
    assert result.validation_passed is True


def test_route_extraction_and_include_router(tmp_path: Path) -> None:
    _sample_project(tmp_path)

    result = build_repository_intelligence(tmp_path, tmp_path / "ri")

    routes = _load(Path(result.output_dir), "routes.json")
    assert any(
        route["path"] == "/password/reset"
        and route["method"] == "POST"
        and route["handler"] == "password_reset"
        and route["file"] == "app/routes/auth.py"
        and route["router"] == "router"
        for route in routes
    )
    assert any(route["method"] == "INCLUDE_ROUTER" and route["path"] == "/api" for route in routes)
    assert result.routes == 2


def test_call_graph_and_import_graph(tmp_path: Path) -> None:
    _sample_project(tmp_path)

    result = build_repository_intelligence(tmp_path, tmp_path / "ri")

    calls = _load(Path(result.output_dir), "call_graph.json")
    imports = _load(Path(result.output_dir), "imports.json")
    assert any(call["caller"] == "password_reset" and call["callee"] == "check_password_reset_rate_limit" for call in calls)
    assert any(call["callee"] == "send_reset_email" for call in calls)
    assert any(
        item["file"] == "app/routes/auth.py"
        and item["module"] == "app.services.reset_service"
        and item["resolved_file"] == "app/services/reset_service.py"
        for item in imports
    )


def test_dependency_graph_and_test_mapping(tmp_path: Path) -> None:
    _sample_project(tmp_path)

    result = build_repository_intelligence(tmp_path, tmp_path / "ri")

    graph = _load(Path(result.output_dir), "dependency_graph.json")
    tests_map = _load(Path(result.output_dir), "tests_map.json")
    auth_entry = next(item for item in graph["file_dependencies"] if item["file"] == "app/routes/auth.py")
    assert "app/services/reset_service.py" in auth_entry["depends_on"]
    assert "tests/test_auth.py" in tests_map["app/routes/auth.py"]
    assert result.tests == 1


def test_project_summary_counts_languages(tmp_path: Path) -> None:
    _sample_project(tmp_path)

    result = build_repository_intelligence(tmp_path, tmp_path / "ri")

    summary = _load(Path(result.output_dir), "project_summary.json")
    assert summary["number_of_files"] >= 6
    assert summary["number_of_routes"] == 2
    assert "Python" in summary["languages_detected"]
    assert "JSON" in summary["languages_detected"]
    assert "Markdown" in summary["languages_detected"]
    assert validate_repository_intelligence(Path(result.output_dir)) == []


def test_protected_path_rejection(tmp_path: Path) -> None:
    protected = tmp_path / "training" / "datasets"
    _write(protected / "sample.py", "def bad():\n    return True")

    result = build_repository_intelligence(
        tmp_path,
        tmp_path / "ri",
        allowed_roots=[protected],
    )

    assert result.files_scanned == 0
    assert "protected_scan_root:training/datasets" in result.validation_errors


def test_large_repository_scan_is_bounded(tmp_path: Path) -> None:
    for index in range(30):
        _write(tmp_path / "pkg" / f"module_{index}.py", f"def function_{index}():\n    return {index}")

    result = build_repository_intelligence(
        tmp_path,
        tmp_path / "ri",
        allowed_roots=[tmp_path / "pkg"],
        max_files=10,
    )

    assert result.files_scanned == 10
    assert result.functions == 10
    assert "max_files_reached" in result.warnings
