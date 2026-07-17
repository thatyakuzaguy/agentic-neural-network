import json
from pathlib import Path

from agentic_network.context_agent.runtime import (
    CONTEXT_OUTPUT_FILE,
    build_context,
    parse_context_sections,
    validate_context_briefing,
)
from agentic_network.memory_agent.runtime import (
    ENGINEERING_KNOWLEDGE_FILE,
    PATTERNS_FILE,
    STATS_FILE,
    SUCCESSFUL_REPAIRS_FILE,
)


def _write_knowledge(root: Path) -> None:
    (root / "patterns").mkdir(parents=True)
    (root / "lessons").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "index.json").write_text(
        json.dumps(
            {
                "total_runs": 1,
                "known_patterns": [
                    "rate_limiting",
                    "authentication",
                    "account_recovery",
                    "abuse_prevention",
                ],
                "known_lesson_count": 2,
                "known_security_insights": 1,
                "last_updated": "2026-06-15T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    patterns = {
        "rate_limiting": "Rate-limited user actions.",
        "authentication": "Authentication-sensitive workflow controls.",
        "account_recovery": "Account recovery flow safeguards.",
        "abuse_prevention": "Abuse prevention controls.",
    }
    for pattern_id, pattern in patterns.items():
        (root / "patterns" / f"{pattern_id}.json").write_text(
            json.dumps(
                {
                    "id": pattern_id,
                    "pattern": pattern,
                    "runs": ["20260615_061422"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    lessons = {
        "rate_limit_balance": "Rate limiting requires balancing usability and abuse prevention.",
        "generic_feedback": "User-facing messaging should avoid account enumeration.",
    }
    for lesson_id, lesson in lessons.items():
        (root / "lessons" / f"{lesson_id}.json").write_text(
            json.dumps({"id": lesson_id, "lesson": lesson, "runs": ["20260615_061422"]}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    (root / "runs" / "20260615_061422.json").write_text(
        json.dumps(
            {
                "run_id": "20260615_061422",
                "task": "Add rate limits to password reset requests.",
                "final_decision": "Approved",
                "reusable_patterns": list(patterns.values()),
                "lessons_learned": list(lessons.values()),
                "future_reuse_score": "High",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _configure_policy(monkeypatch, project_root: Path) -> None:
    monkeypatch.setenv("ANN_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", str(project_root))
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "/mnt/c,C:\\")
    monkeypatch.delenv("ANN_PROTECTED_PATHS", raising=False)


def _write_memory(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / PATTERNS_FILE).write_text(
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
    (root / SUCCESSFUL_REPAIRS_FILE).write_text("[]\n", encoding="utf-8")
    (root / ENGINEERING_KNOWLEDGE_FILE).write_text(
        json.dumps(
            [
                {
                    "domain": "rate_limiting",
                    "constants": {"WINDOW_SECONDS": 7200},
                    "confidence": "High",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / STATS_FILE).write_text("{}\n", encoding="utf-8")


def test_context_generation_matches_reusable_knowledge(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge"
    _write_knowledge(knowledge_root)

    result = build_context("Add rate limits to password reset requests.", knowledge_root)

    parsed = parse_context_sections(result.context_artifact)
    assert result.validation_errors == []
    assert parsed["context_confidence"] == "High"
    assert "Rate-limited user actions." in result.matched_patterns
    assert "Authentication-sensitive workflow controls." in result.matched_patterns
    assert "Account recovery flow safeguards." in result.matched_patterns
    assert "Abuse prevention controls." in result.matched_patterns
    assert any("Rate limiting requires balancing" in item for item in result.matched_lessons)
    assert result.matched_runs


def test_context_generation_injects_experience_memory(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    knowledge_root = project_root / "knowledge"
    memory_root = project_root / "memory"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    _configure_policy(monkeypatch, project_root)
    _write_knowledge(knowledge_root)
    _write_memory(memory_root)
    run_dir.mkdir(parents=True)

    result = build_context(
        "Add rate limits to password reset requests.",
        knowledge_root,
        memory_root=memory_root,
        run_dir=run_dir,
    )

    parsed = parse_context_sections(result.context_artifact)
    assert result.validation_errors == []
    assert parsed["experience_memory"]
    assert "Reusable constants: WINDOW_SECONDS=7200." in result.context_artifact
    assert (run_dir / "22_memory_query.md").exists()
    assert (run_dir / "23_memory_matches.md").exists()
    assert (run_dir / "24_experience_context.md").exists()


def test_context_missing_knowledge_is_graceful(tmp_path: Path) -> None:
    result = build_context("Create a small feature.", tmp_path / "missing-knowledge")

    assert result.validation_errors == []
    assert "missing_knowledge_root" in result.warnings
    assert "No prior reusable project context matched" in result.context_artifact
    assert "CONTEXT CONFIDENCE\nHigh" in result.context_artifact


def test_context_validator_rejects_code_like_output() -> None:
    content = """PROJECT CONTEXT
- Context.

RELATED PATTERNS
- Pattern.

RELEVANT LESSONS
- Lesson.

SIMILAR RUNS
- Run.

KNOWN RISKS
- Risk.

RECOMMENDED FOCUS
- Focus.

CONTEXT CONFIDENCE
High

```python
def example():
    return None
```
"""
    parsed = parse_context_sections(content)
    errors = validate_context_briefing(content, parsed)

    assert any(error.startswith("forbidden_code_marker") for error in errors)


def test_cli_output_filename_constant() -> None:
    assert CONTEXT_OUTPUT_FILE == "00_context.md"
