from pathlib import Path

from agentic_network.execution_agent.synthesizer import (
    STRATEGY_FALLBACK_SOURCE_AWARE,
    STRATEGY_JSON_SAFE_KEY,
    STRATEGY_MARKDOWN_APPEND,
    STRATEGY_PYTHON_CONFIG_CONSTANTS,
    STRATEGY_PYTHON_TODO_IMPLEMENTATION,
    STRATEGY_REJECTED,
    synthesize_patch,
)


ARTIFACT_CONTEXT = """
CODE CHANGES
- Add password reset rate limits.
- Add configurable max attempts and retry window.
- Block excessive password reset attempts.
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _context(repo: Path) -> dict[str, str]:
    return {"project_root": str(repo)}


def test_python_config_constants(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "config.py"
    target.write_text("DEBUG = False\n", encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is True
    assert result.strategy == STRATEGY_PYTHON_CONFIG_CONSTANTS
    assert "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 5" in result.unified_diff
    assert "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600" in result.unified_diff
    assert "ANN patch proposal" not in result.unified_diff
    assert target.read_text(encoding="utf-8") == "DEBUG = False\n"


def test_duplicate_constants_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "config.py"
    target.write_text(
        "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 5\n",
        encoding="utf-8",
    )

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is False
    assert result.strategy == STRATEGY_PYTHON_CONFIG_CONSTANTS
    assert result.fallback_reason == "duplicate_constants_present"
    assert result.unified_diff == ""


def test_python_todo_implementation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "limits.py"
    target.write_text(
        "def max_attempts():\n"
        "    pass # TODO\n",
        encoding="utf-8",
    )

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is True
    assert result.strategy == STRATEGY_PYTHON_TODO_IMPLEMENTATION
    assert "-    pass # TODO" in result.unified_diff
    assert "+    return 5" in result.unified_diff


def test_markdown_append(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "README.md"
    target.write_text("# Notes\n", encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is True
    assert result.strategy == STRATEGY_MARKDOWN_APPEND
    assert "+Approved Behavior" in result.unified_diff
    assert "+- Add password reset rate limits." in result.unified_diff
    assert "```" not in result.unified_diff


def test_json_key_insertion(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "settings.json"
    target.write_text('{\n  "retry_window": 60\n}\n', encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is True
    assert result.strategy == STRATEGY_JSON_SAFE_KEY
    assert '"password_reset_limit": 5' in result.unified_diff


def test_invalid_python_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "config.py"
    target.write_text("def broken(:\n", encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert result.fallback_reason == "invalid_python_before"


def test_invalid_json_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "settings.json"
    target.write_text('{"retry_window": ', encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert result.fallback_reason == "invalid_json_before"


def test_fallback_mode(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "service.py"
    target.write_text("def existing():\n    return True\n", encoding="utf-8")

    result = synthesize_patch(target, "Review this file for scoped implementation.", _context(repo))

    assert result.success is True
    assert result.strategy == STRATEGY_FALLBACK_SOURCE_AWARE
    assert "ANN patch proposal" in result.unified_diff


def test_protected_path_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "training" / "datasets" / "data.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert "protected_path_modified" in result.fallback_reason


def test_filesystem_policy_enforced(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = Path("/mnt/c/tmp/config.py")

    result = synthesize_patch(target, ARTIFACT_CONTEXT, _context(repo))

    assert result.success is False
    assert result.strategy == STRATEGY_REJECTED
    assert "forbidden_c_path_present" in result.fallback_reason
