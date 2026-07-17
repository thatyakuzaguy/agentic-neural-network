import ast
import json
from pathlib import Path

from agentic_network.self_healing_agent.runtime import (
    STATUS_FAILED_ANALYSIS,
    STATUS_FAILED_PERMANENTLY,
    STATUS_NO_FAILURE_DETECTED,
    STATUS_RETRY_PATCH_GENERATED,
    STATUS_SKIPPED,
    analyze_failure,
    run_self_healing,
    validate_retry_patch,
)


def _write_summary(run_dir: Path, **fields) -> None:
    payload = {"output_files": {}, **fields}
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_test_run(run_dir: Path, body: str) -> None:
    (run_dir / "14_test_run.md").write_text(body, encoding="utf-8")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_skipped_when_tests_passed(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="PASSED")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_NO_FAILURE_DETECTED
    assert result.retry_patch_path == ""
    assert not (tmp_path / "19_retry_patch_001.diff").exists()


def test_skipped_when_tests_skipped(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="SKIPPED")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_SKIPPED
    assert result.retry_patch_path == ""
    assert not (tmp_path / "19_retry_patch_001.diff").exists()


def test_failed_permanently_when_attempts_reach_max(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="FAILED", self_healing_attempts=5)
    _write_test_run(tmp_path, "NameError: name 'PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS' is not defined")

    result = run_self_healing(tmp_path, max_attempts=5)

    assert result.status == STATUS_FAILED_PERMANENTLY
    assert "self_healing_max_attempts_reached" in result.validation_errors
    assert result.retry_patch_path == ""


def test_parses_name_error_missing_constant() -> None:
    signal = analyze_failure(
        """Traceback (most recent call last):
  File "agentic_network/auth.py", line 10, in reset
NameError: name 'PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS' is not defined
"""
    )

    assert signal is not None
    assert signal.error_type == "NameError"
    assert signal.missing_symbol == "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS"
    assert signal.location == "agentic_network/auth.py"


def test_generates_retry_patch_for_missing_uppercase_constant(tmp_path: Path) -> None:
    config_path = _project_root() / "agentic_network" / "config.py"
    before = config_path.read_text(encoding="utf-8")
    _write_summary(tmp_path, test_runner_status="FAILED")
    _write_test_run(
        tmp_path,
        "NameError: name 'PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS' is not defined",
    )

    result = run_self_healing(tmp_path)

    after = config_path.read_text(encoding="utf-8")
    assert before == after
    assert result.status == STATUS_RETRY_PATCH_GENERATED
    assert result.retry_patch_path.endswith("19_retry_patch_001.diff")
    patch_text = Path(result.retry_patch_path).read_text(encoding="utf-8")
    assert "--- a/agentic_network/config.py" in patch_text
    assert "+++ b/agentic_network/config.py" in patch_text
    assert "+PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600" in patch_text
    assert result.validation_errors == []
    assert (tmp_path / "17_failure_analysis.md").exists()
    assert (tmp_path / "18_root_cause.md").exists()
    assert (tmp_path / "21_self_healing.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["self_healing_status"] == STATUS_RETRY_PATCH_GENERATED
    assert summary["self_healing_attempts"] == 1
    assert summary["self_healing_validation_passed"] is True
    assert summary["self_healing_last_patch"] == result.retry_patch_path


def test_self_healing_uses_experience_context_constant(tmp_path: Path) -> None:
    config_path = _project_root() / "agentic_network" / "config.py"
    before = config_path.read_text(encoding="utf-8")
    _write_summary(tmp_path, test_runner_status="FAILED")
    _write_test_run(
        tmp_path,
        "NameError: name 'PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS' is not defined",
    )
    (tmp_path / "24_experience_context.md").write_text(
        "EXPERIENCE CONTEXT\n"
        "- Retrieved engineering experience for: Add rate limits.\n\n"
        "REUSABLE PATTERNS\n"
        "- nameerror_missing_constant\n\n"
        "REUSABLE CONSTANTS\n"
        "- WINDOW_SECONDS=7200\n\n"
        "RELEVANT REPAIRS\n"
        "- Add rate limits using add_constant\n\n"
        "RECOMMENDED REUSE\n"
        "- Prefer retrieved constants.\n\n"
        "CONFIDENCE\n"
        "High\n",
        encoding="utf-8",
    )

    result = run_self_healing(tmp_path)

    after = config_path.read_text(encoding="utf-8")
    assert before == after
    assert result.status == STATUS_RETRY_PATCH_GENERATED
    assert result.memory_used is True
    assert result.memory_pattern_used == "nameerror_missing_constant"
    patch_text = Path(result.retry_patch_path).read_text(encoding="utf-8")
    assert "+PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 7200" in patch_text
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["self_healing_memory_used"] is True
    assert summary["self_healing_memory_pattern_used"] == "nameerror_missing_constant"


def test_generated_python_remains_ast_valid(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="FAILED")
    _write_test_run(tmp_path, "NameError: name 'PASSWORD_RESET_MAX_ATTEMPTS' is not defined")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_RETRY_PATCH_GENERATED
    patch_text = Path(result.retry_patch_path).read_text(encoding="utf-8")
    assert validate_retry_patch(patch_text, project_root=_project_root()) == []
    config_source = (_project_root() / "agentic_network" / "config.py").read_text(encoding="utf-8")
    ast.parse(config_source)


def test_missing_module_does_not_generate_install_command(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="FAILED")
    _write_test_run(tmp_path, "ModuleNotFoundError: No module named 'totally_missing_package'")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_FAILED_ANALYSIS
    assert result.retry_patch_path == ""
    assert "unsupported_retry_synthesis:ImportError" in result.validation_warnings
    report = (tmp_path / "21_self_healing.md").read_text(encoding="utf-8")
    assert "pip install" not in report


def test_assertion_error_does_not_generate_unsafe_patch(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="FAILED")
    _write_test_run(tmp_path, "AssertionError: expected 2 got 1")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_FAILED_ANALYSIS
    assert result.retry_patch_path == ""
    assert "unsupported_retry_synthesis:AssertionError" in result.validation_warnings


def test_protected_path_rejected() -> None:
    patch_text = "\n".join(
        [
            "--- a/knowledge/index.json",
            "+++ b/knowledge/index.json",
            "@@ -1,1 +1,2 @@",
            " {",
            '+  "unsafe": true,',
        ]
    )

    errors = validate_retry_patch(patch_text, project_root=_project_root())

    assert any(error.startswith("protected_path_modified:") for error in errors)


def test_artifacts_written_and_summary_updated_for_failed_analysis(tmp_path: Path) -> None:
    _write_summary(tmp_path, test_runner_status="TIMEOUT")
    _write_test_run(tmp_path, "Test execution timed out after 300 seconds.")

    result = run_self_healing(tmp_path)

    assert result.status == STATUS_FAILED_ANALYSIS
    assert (tmp_path / "17_failure_analysis.md").exists()
    assert (tmp_path / "18_root_cause.md").exists()
    assert (tmp_path / "21_self_healing.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["self_healing_enabled"] is True
    assert summary["self_healing_attempts"] == 1
    assert summary["self_healing_artifacts"]
