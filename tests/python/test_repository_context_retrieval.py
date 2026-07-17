from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.execution_agent.runtime import (
    generate_execution_plan,
    select_patch_targets_from_repository_context,
)
from agentic_network.pipeline.runner import PipelineRunner
from agentic_network.repository_intelligence_agent.retrieval import build_repository_context


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _write_indexes(run_dir: Path) -> Path:
    index_dir = run_dir / "repository_intelligence"
    functions = [
        {"name": "password_reset", "file": "app/routes/auth.py", "line": 10, "args": ["email"]},
        {"name": "check_password_reset_rate_limit", "file": "app/services/reset_service.py", "line": 4, "args": ["email"]},
        {"name": "search_products", "file": "app/routes/products.py", "line": 20, "args": ["page", "page_size"]},
        {"name": "paginate_items", "file": "app/services/pagination.py", "line": 5, "args": ["items"]},
    ]
    classes = [
        {"name": "PasswordResetLimiter", "file": "app/services/reset_service.py", "line": 1, "methods": ["allow"]},
        {"name": "ProductSearchService", "file": "app/services/product_search.py", "line": 1, "methods": ["search"]},
    ]
    routes = [
        {"path": "/password/reset", "method": "POST", "handler": "password_reset", "file": "app/routes/auth.py"},
        {"path": "/products/search", "method": "GET", "handler": "search_products", "file": "app/routes/products.py"},
    ]
    dependency_graph = {
        "file_dependencies": [
            {
                "file": "app/routes/auth.py",
                "depends_on": ["app/services/reset_service.py"],
                "depended_by": [],
            },
            {
                "file": "app/services/reset_service.py",
                "depends_on": ["app/core/config.py"],
                "depended_by": ["app/routes/auth.py"],
            },
            {
                "file": "app/routes/products.py",
                "depends_on": ["app/services/product_search.py"],
                "depended_by": [],
            },
            {
                "file": "app/services/product_search.py",
                "depends_on": ["app/services/pagination.py"],
                "depended_by": ["app/routes/products.py"],
            },
        ],
        "service_dependencies": [],
        "route_dependencies": [],
    }
    tests_map = {
        "app/routes/auth.py": ["tests/test_auth.py"],
        "app/services/reset_service.py": ["tests/test_auth.py"],
        "app/routes/products.py": ["tests/test_products.py"],
        "app/services/pagination.py": ["tests/test_pagination.py"],
    }
    _write_json(index_dir / "functions.json", functions)
    _write_json(index_dir / "classes.json", classes)
    _write_json(index_dir / "imports.json", [])
    _write_json(
        index_dir / "call_graph.json",
        [
            {
                "caller": f"unrelated_{index}",
                "callee": "very_large_unrelated_call_graph_entry",
                "file": f"app/unrelated/module_{index}.py",
                "line": index,
            }
            for index in range(100)
        ],
    )
    _write_json(index_dir / "routes.json", routes)
    _write_json(index_dir / "tests_map.json", tests_map)
    _write_json(index_dir / "dependency_graph.json", dependency_graph)
    _write_json(index_dir / "project_summary.json", {"number_of_files": 8})
    return index_dir


def _full_index_chars(index_dir: Path) -> int:
    return sum(len(path.read_text(encoding="utf-8")) for path in index_dir.glob("*.json"))


def test_password_reset_task_selects_auth_reset_rate_limit_context(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    index_dir = _write_indexes(run_dir)

    result = build_repository_context("Add rate limits to password reset requests", run_dir)

    assert result.validation_passed is True
    assert "app/routes/auth.py" in result.matched_files
    assert "app/services/reset_service.py" in result.matched_files
    assert any(route["path"] == "/password/reset" for route in result.matched_routes)
    assert any(function["name"] == "check_password_reset_rate_limit" for function in result.matched_functions)
    assert "tests/test_auth.py" in result.matched_tests
    assert "app/services/reset_service.py" in result.dependency_paths
    assert "app/routes/auth.py" in result.recommended_patch_targets
    markdown = Path(result.context_artifact).read_text(encoding="utf-8")
    compact_json = Path(result.compact_json_artifact).read_text(encoding="utf-8")
    assert "file_dependencies" not in markdown
    assert len(markdown) + len(compact_json) < _full_index_chars(index_dir)


def test_pagination_task_selects_search_product_pagination_context(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_indexes(run_dir)

    result = build_repository_context("Add pagination to product search results", run_dir)

    assert "app/routes/products.py" in result.matched_files
    assert "app/services/product_search.py" in result.dependency_paths
    assert any(route["path"] == "/products/search" for route in result.matched_routes)
    assert any(function["name"] == "paginate_items" for function in result.matched_functions)
    assert "tests/test_products.py" in result.matched_tests


def test_retrieval_limits_are_respected(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_indexes(run_dir)

    result = build_repository_context(
        "Add pagination to product search results",
        run_dir,
        max_functions=1,
        max_classes=1,
        max_routes=1,
        max_tests=1,
        max_files=2,
    )

    assert len(result.matched_functions) <= 1
    assert len(result.matched_classes) <= 1
    assert len(result.matched_routes) <= 1
    assert len(result.matched_tests) <= 1
    assert len(result.matched_files) <= 2


def test_missing_indexes_are_handled_gracefully(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = build_repository_context("Add rate limits", run_dir)

    assert result.validation_passed is False
    assert "repository_intelligence_indexes_missing" in result.validation_errors
    assert "missing_repository_intelligence_dir" in result.warnings
    assert Path(result.context_artifact).exists()
    assert Path(result.compact_json_artifact).exists()


def test_execution_uses_repository_context_instead_of_full_indexes(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    route = repo / "app" / "routes" / "auth.py"
    _write(route, "def password_reset(email):\n    return {'accepted': True}")
    service = repo / "app" / "services" / "reset_service.py"
    _write(service, "def check_password_reset_rate_limit(email):\n    return {'allowed': True}")
    run_dir = tmp_path / "run"
    _write_indexes(run_dir)
    build_repository_context("Add rate limits to password reset requests", run_dir)
    _write(
        run_dir / "03_code_revised.md",
        """
        FILES TO MODIFY
        - Candidate: password reset request handling module.

        NEW FILES
        - Candidate: tests for password reset rate-limit behavior.

        CODE CHANGES
        - Add configurable rate limit policy.

        TESTS TO ADD
        - Verify excessive reset attempts are blocked.

        CONFIDENCE
        High
        """,
    )
    _write(run_dir / "04_tests_revised.md", "TEST SCENARIOS\n- Verify reset limits.")
    _write(run_dir / "05_security_revised.md", "SECURITY FINDINGS\n- Preserve generic reset feedback.")
    _write(run_dir / "08_final_review.md", "FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh")
    monkeypatch.setattr("agentic_network.execution_agent.runtime._project_root", lambda: repo)

    result = generate_execution_plan(run_dir)

    assert result.repository_context_used is True
    assert result.repository_context_chars < _full_index_chars(run_dir / "repository_intelligence")
    assert result.repository_context_files > 0
    assert result.repository_context_functions > 0
    assert "app/routes/auth.py" in (result.candidate_files or [])


def test_repository_context_selector_scores_route_service_above_unrelated_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_indexes(run_dir)
    result = build_repository_context("Add rate limits to password reset requests", run_dir)
    payload = json.loads(Path(result.compact_json_artifact).read_text(encoding="utf-8"))
    payload["recommended_patch_targets"] = [
        "app/unrelated.py",
        *payload.get("recommended_patch_targets", []),
    ]
    payload["matched_files"] = [
        "app/unrelated.py",
        *payload.get("matched_files", []),
    ]

    selection = select_patch_targets_from_repository_context(
        "Add rate limits to password reset requests",
        payload,
        "Backend password reset abuse prevention.",
    )

    assert selection.selected_targets
    assert selection.selected_targets[0] in {
        "app/services/reset_service.py",
        "app/routes/auth.py",
    }
    assert "app/unrelated.py" not in selection.selected_targets[:2]


def test_pipeline_integration_writes_repository_context_summary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "app" / "routes" / "auth.py", "def password_reset(email):\n    return True")
    config = replace(_config(tmp_path), project_root=repo)
    runner = PipelineRunner(config, mock=True, mock_changes_required=False)

    result = runner.run(
        "Add rate limits to password reset requests.",
        stages=["context", "repository_intelligence", "repository_context"],
    )

    output_dir = Path(result.output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert result.stages_run == ["context", "repository_intelligence", "repository_context"]
    assert (output_dir / "26_repository_context.md").exists()
    assert (output_dir / "26_repository_context.json").exists()
    assert summary["repository_context_enabled"] is True
    assert summary["repository_context_validation_passed"] is True
    assert summary["repository_context_chars"] > 0


def _config(tmp_path: Path) -> PipelineConfig:
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
        stage_isolation="inprocess",
    )
