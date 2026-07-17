import json
from pathlib import Path

from agentic_network.memory_agent.runtime import (
    ENGINEERING_KNOWLEDGE_FILE,
    PATTERNS_FILE,
    STATS_FILE,
    SUCCESSFUL_REPAIRS_FILE,
    record_engineering_experience,
    search_experience,
)


def _configure_policy(monkeypatch, project_root: Path) -> None:
    monkeypatch.setenv("ANN_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", str(project_root))
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "/mnt/c,C:\\")
    monkeypatch.delenv("ANN_PROTECTED_PATHS", raising=False)


def _run_dir(project_root: Path) -> Path:
    run_dir = project_root / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_run(
    run_dir: Path,
    *,
    task: str = "Add rate limits to password reset requests.",
    self_healing_status: str = "RETRY_PATCH_GENERATED",
    merge_decision: str = "READY TO APPLY",
) -> None:
    summary = {
        "task": task,
        "self_healing_status": self_healing_status,
        "self_healing_last_patch": str(run_dir / "19_retry_patch_001.diff"),
        "self_healing_last_error": "name 'PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS' is not defined",
        "merge_readiness_decision": merge_decision,
        "patch_approval_decision": "Approved",
        "patch_apply_status": "DRY_RUN_PASSED",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "17_failure_analysis.md").write_text(
        "FAILURE SUMMARY\n- Missing constant.\n\n"
        "ERROR TYPE\n- NameError\n\n"
        "ERROR LOCATION\n- agentic_network/config.py\n\n"
        "EXTRACTED SIGNALS\n"
        "- missing_symbol = PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS\n"
        "- message = name is not defined\n\n"
        "CONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "18_root_cause.md").write_text(
        "ROOT CAUSE SUMMARY\n"
        "- Referenced symbol PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS is missing from code or configuration.\n\n"
        "LIKELY CAUSE\n- Missing uppercase constant.\n\n"
        "SAFE FIX STRATEGY\n- Add conservative constant.\n\n"
        "UNSAFE ACTIONS AVOIDED\n- Did not apply patches.\n\n"
        "CONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "21_self_healing.md").write_text(
        "SELF HEALING SUMMARY\n- Retry patch generated.\n\n"
        "ATTEMPT STATUS\n- RETRY_PATCH_GENERATED\n\n"
        f"RETRY PATCH\n- {run_dir / '19_retry_patch_001.diff'}\n\n"
        "VALIDATION\n- Passed\n\n"
        "NEXT ACTION\n- Route through approval.\n\n"
        "CONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "15_merge_readiness.md").write_text(
        f"MERGE DECISION\n{merge_decision}\n\nCONFIDENCE\nHigh\n",
        encoding="utf-8",
    )
    (run_dir / "12_patch_approval.md").write_text("APPROVAL DECISION\nApproved\n", encoding="utf-8")
    (run_dir / "13_patch_apply.md").write_text("PATCH APPLY STATUS\nDry Run Passed\n", encoding="utf-8")
    (run_dir / "14_test_run.md").write_text("TEST STATUS\nSkipped\n", encoding="utf-8")


def _memory_json(project_root: Path, filename: str):
    return json.loads((project_root / "memory" / filename).read_text(encoding="utf-8"))


def test_store_successful_repair(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    result = record_engineering_experience(run_dir)

    repairs = _memory_json(project_root, SUCCESSFUL_REPAIRS_FILE)
    assert result.validation_passed is True
    assert result.successful_repairs == 1
    assert repairs[0]["task"] == "Add rate limits to password reset requests."
    assert repairs[0]["success"] is True
    assert repairs[0]["fix"]["strategy"] == "add_constant"
    assert repairs[0]["fix"]["value"] == 3600


def test_store_failed_repair(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir, self_healing_status="FAILED_PERMANENTLY", merge_decision="BLOCKED")

    result = record_engineering_experience(run_dir)

    repairs = _memory_json(project_root, SUCCESSFUL_REPAIRS_FILE)
    assert result.failed_repairs == 1
    assert repairs[0]["success"] is False


def test_store_nameerror_pattern(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    result = record_engineering_experience(run_dir)

    patterns = _memory_json(project_root, PATTERNS_FILE)
    assert result.patterns_recorded == 1
    assert patterns == [
        {
            "confidence": "High",
            "description": "Missing uppercase constant",
            "error_type": "NameError",
            "pattern_id": "nameerror_missing_constant",
            "recommended_fix": "add_constant",
        }
    ]


def test_store_rate_limit_domain_knowledge(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    result = record_engineering_experience(run_dir)

    knowledge = _memory_json(project_root, ENGINEERING_KNOWLEDGE_FILE)
    assert result.last_domain == "rate_limiting"
    assert knowledge[0]["domain"] == "rate_limiting"
    assert knowledge[0]["constants"]["WINDOW_SECONDS"] == 3600
    assert knowledge[0]["constants"]["MAX_ATTEMPTS"] == 5
    assert knowledge[0]["constants"]["THRESHOLD"] == 10


def test_search_experiences(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)
    record_engineering_experience(run_dir)

    results = search_experience("password reset rate limit missing constant", max_results=5)

    assert results["relevant_repairs"]
    assert results["known_patterns"][0]["pattern_id"] == "nameerror_missing_constant"
    assert results["known_constants"][0]["domain"] == "rate_limiting"
    assert results["previous_fixes"][0]["strategy"] == "add_constant"


def test_reject_duplicates(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    first = record_engineering_experience(run_dir)
    second = record_engineering_experience(run_dir)

    patterns = _memory_json(project_root, PATTERNS_FILE)
    repairs = _memory_json(project_root, SUCCESSFUL_REPAIRS_FILE)
    assert first.patterns_recorded == 1
    assert second.patterns_recorded == 0
    assert len(patterns) == 1
    assert len(repairs) == 1


def test_reject_invalid_json(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    memory_dir = project_root / "memory"
    memory_dir.mkdir(parents=True)
    _configure_policy(monkeypatch, project_root)
    (memory_dir / PATTERNS_FILE).write_text("{not json", encoding="utf-8")
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    result = record_engineering_experience(run_dir)

    assert "invalid_json:patterns.json" in result.validation_errors


def test_update_stats(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    record_engineering_experience(run_dir)

    stats = _memory_json(project_root, STATS_FILE)
    assert stats["repairs_recorded"] == 1
    assert stats["patterns_recorded"] == 1
    assert stats["successful_retries"] == 1
    assert stats["failed_retries"] == 0


def test_filesystem_policy_respected(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _configure_policy(monkeypatch, project_root)
    monkeypatch.setenv("ANN_PROTECTED_PATHS", "memory")
    run_dir = _run_dir(project_root)
    _write_run(run_dir)

    result = record_engineering_experience(run_dir)

    assert any(error.startswith("protected_path_modified:") for error in result.validation_errors)
    assert not (project_root / "memory" / PATTERNS_FILE).exists()
