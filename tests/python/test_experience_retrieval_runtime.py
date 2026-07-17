import json
from pathlib import Path

from agentic_network.memory_agent.retrieval import (
    EXPERIENCE_CONTEXT_FILE,
    MEMORY_MATCHES_FILE,
    MEMORY_QUERY_FILE,
    build_experience_context,
    memory_retrieval_summary_fields,
    validate_memory_artifact,
)
from agentic_network.memory_agent.runtime import (
    ENGINEERING_KNOWLEDGE_FILE,
    PATTERNS_FILE,
    STATS_FILE,
    SUCCESSFUL_REPAIRS_FILE,
)


def _configure_policy(monkeypatch, project_root: Path) -> None:
    monkeypatch.setenv("ANN_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", str(project_root))
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "/mnt/c,C:\\")
    monkeypatch.delenv("ANN_PROTECTED_PATHS", raising=False)


def _write_memory(memory_root: Path, *, dangerous: bool = False) -> None:
    memory_root.mkdir(parents=True, exist_ok=True)
    (memory_root / PATTERNS_FILE).write_text(
        json.dumps(
            [
                {
                    "pattern_id": "nameerror_missing_constant",
                    "description": "Missing uppercase constant",
                    "recommended_fix": "add_constant",
                    "error_type": "NameError",
                    "confidence": "High",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    repair_strategy = "add_constant"
    if dangerous:
        repair_strategy = "add_constant; sudo rm /mnt/c/tmp/file"
    (memory_root / SUCCESSFUL_REPAIRS_FILE).write_text(
        json.dumps(
            [
                {
                    "repair_id": "repair_rate_limit_constant",
                    "task": "Add rate limits to password reset requests.",
                    "fix": {"strategy": repair_strategy, "value": 7200},
                    "patch": {"target": "agentic_network/config.py", "retry_patch": "--- unsafe"},
                    "success": True,
                    "confidence": "High",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (memory_root / ENGINEERING_KNOWLEDGE_FILE).write_text(
        json.dumps(
            [
                {
                    "domain": "rate_limiting",
                    "constants": {
                        "WINDOW_SECONDS": 7200,
                        "MAX_ATTEMPTS": 7,
                        "THRESHOLD": 11,
                    },
                    "confidence": "High",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (memory_root / STATS_FILE).write_text("{}\n", encoding="utf-8")


def test_build_experience_context_writes_no_match_artifacts(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    memory_root = project_root / "memory"
    run_dir.mkdir(parents=True)
    memory_root.mkdir()
    _configure_policy(monkeypatch, project_root)

    result = build_experience_context("Create a small feature.", memory_root, run_dir)

    assert result.validation_errors == []
    assert result.matches_found == 0
    for filename in (MEMORY_QUERY_FILE, MEMORY_MATCHES_FILE, EXPERIENCE_CONTEXT_FILE):
        content = (run_dir / filename).read_text(encoding="utf-8")
        assert validate_memory_artifact(filename, content) == []
        assert "CONFIDENCE\nHigh" in content
    assert "No reusable constants matched." in (run_dir / EXPERIENCE_CONTEXT_FILE).read_text(encoding="utf-8")


def test_build_experience_context_retrieves_constants_and_patterns(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    memory_root = project_root / "memory"
    run_dir.mkdir(parents=True)
    _configure_policy(monkeypatch, project_root)
    _write_memory(memory_root)

    result = build_experience_context(
        "Add rate limits to password reset requests.",
        memory_root,
        run_dir,
    )

    assert result.validation_errors == []
    assert result.constants_used == {"WINDOW_SECONDS": 7200, "MAX_ATTEMPTS": 7, "THRESHOLD": 11}
    assert "nameerror_missing_constant" in result.patterns_used
    context = (run_dir / EXPERIENCE_CONTEXT_FILE).read_text(encoding="utf-8")
    assert "- WINDOW_SECONDS=7200" in context
    assert "- MAX_ATTEMPTS=7" in context
    summary = memory_retrieval_summary_fields(result)
    assert summary["memory_retrieval_enabled"] is True
    assert summary["memory_matches_found"] > 0
    assert summary["memory_context_injected"] is True


def test_invalid_memory_json_is_reported_without_unsafe_failure(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    memory_root = project_root / "memory"
    run_dir.mkdir(parents=True)
    memory_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    (memory_root / PATTERNS_FILE).write_text("{invalid", encoding="utf-8")
    (memory_root / SUCCESSFUL_REPAIRS_FILE).write_text("[]\n", encoding="utf-8")
    (memory_root / ENGINEERING_KNOWLEDGE_FILE).write_text("[]\n", encoding="utf-8")
    (memory_root / STATS_FILE).write_text("{}\n", encoding="utf-8")

    result = build_experience_context("Add rate limits.", memory_root, run_dir)

    assert "invalid_memory_json:patterns.json" in result.validation_errors
    assert (run_dir / EXPERIENCE_CONTEXT_FILE).exists()
    assert "No reusable constants matched." in (run_dir / EXPERIENCE_CONTEXT_FILE).read_text(encoding="utf-8")


def test_dangerous_memory_content_is_not_injected(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    memory_root = project_root / "memory"
    run_dir.mkdir(parents=True)
    _configure_policy(monkeypatch, project_root)
    _write_memory(memory_root, dangerous=True)

    result = build_experience_context("Add rate limits to password reset requests.", memory_root, run_dir)
    context = (run_dir / EXPERIENCE_CONTEXT_FILE).read_text(encoding="utf-8")

    assert result.validation_errors == []
    assert "sudo" not in context
    assert "/mnt/c" not in context
    assert "--- unsafe" not in context
