import json
from pathlib import Path

from agentic_network.knowledge_agent.runtime import (
    KNOWLEDGE_OUTPUT_FILE,
    capture_knowledge,
    parse_knowledge_capture_sections,
    validate_knowledge_capture,
)


ARTIFACT_CONTENT = {
    "01_product_requirements.md": "REQUIREMENTS\n- Add rate limits to password reset requests.\n\nACCEPTANCE CRITERIA\n- Legitimate reset attempts still work.",
    "02_architecture_plan.md": "TECHNICAL SUMMARY\n- Use a centralized rate-limit policy for account recovery.",
    "03_code.md": "CODE CHANGES\n- Apply configurable rate-limit policy before reset instructions are sent.",
    "04_tests.md": "TEST SCENARIOS\n- Verify excessive requests are blocked.\n- Verify limits reset after the configured time window.",
    "05_security.md": "SECURITY FINDINGS\n- Preserve generic feedback to reduce user enumeration.\n\nTHREATS\n- Automated abuse can trigger repeated reset messages.",
    "06_review.md": "APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh",
    "07_fix_plan.md": "READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh",
    "08_final_review.md": "FINAL DECISION\nApproved\n\nCONFIDENCE\nHigh",
    "09_handoff_bundle.md": "# ANN Handoff Bundle\n\n## Run Summary\n- Final decision: Approved",
}


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "00_user_request.md").write_text(
        "Add rate limits to password reset requests.\n",
        encoding="utf-8",
    )
    for filename, content in ARTIFACT_CONTENT.items():
        (run_dir / filename).write_text(content + "\n", encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "Add rate limits to password reset requests.",
                "stages_run": [
                    "product",
                    "architect",
                    "code",
                    "test",
                    "security",
                    "reviewer",
                    "fixer",
                    "final",
                    "handoff",
                ],
                "final_decision": "Approved",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_knowledge_capture_from_mock_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)

    result = capture_knowledge(run_dir)

    artifact = (run_dir / KNOWLEDGE_OUTPUT_FILE).read_text(encoding="utf-8")
    assert result.validation_errors == []
    assert result.future_reuse_score == "High"
    assert result.confidence == "High"
    assert "Rate limiting requires balancing usability and abuse prevention." in artifact
    assert "Rate-limited user actions." in artifact
    assert "User enumeration risks should be minimized with generic feedback." in artifact


def test_knowledge_index_update_and_persistent_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)

    result = capture_knowledge(run_dir)

    knowledge_dir = tmp_path / "knowledge"
    index = json.loads((knowledge_dir / "index.json").read_text(encoding="utf-8"))
    run_payload = json.loads((knowledge_dir / "runs" / "run.json").read_text(encoding="utf-8"))
    assert index["total_runs"] == 1
    assert "rate_limiting" in index["known_patterns"]
    assert index["known_lesson_count"] >= 1
    assert run_payload["future_reuse_score"] == result.future_reuse_score
    assert run_payload["final_decision"] == "Approved"


def test_pattern_and_lesson_extraction(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)

    capture_knowledge(run_dir)

    knowledge_dir = tmp_path / "knowledge"
    pattern = json.loads((knowledge_dir / "patterns" / "rate_limiting.json").read_text(encoding="utf-8"))
    lesson_files = list((knowledge_dir / "lessons").glob("*.json"))
    assert pattern["pattern"] == "Rate-limited user actions."
    assert pattern["runs"] == ["run"]
    assert lesson_files


def test_missing_artifact_handling(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    (run_dir / "05_security.md").unlink()

    result = capture_knowledge(run_dir)

    assert result.validation_errors == []
    assert "missing_artifact:05_security.md" in result.warnings
    assert (run_dir / KNOWLEDGE_OUTPUT_FILE).exists()


def test_validator_rejects_code_and_invalid_score() -> None:
    content = """LESSONS LEARNED
- Keep it reusable.

REUSABLE PATTERNS
- Pattern.

PRODUCT INSIGHTS
- Product.

ARCHITECTURE INSIGHTS
- Architecture.

TESTING INSIGHTS
- Testing.

SECURITY INSIGHTS
- Security.

FUTURE REUSE SCORE
Very High

CONFIDENCE
High

```python
def example():
    return None
```
"""
    parsed = parse_knowledge_capture_sections(content)
    errors = validate_knowledge_capture(content, parsed)

    assert "invalid_future_reuse_score" in errors
    assert any(error.startswith("forbidden_code_marker") for error in errors)
