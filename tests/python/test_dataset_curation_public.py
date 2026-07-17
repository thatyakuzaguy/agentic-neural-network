from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dataset_curation.common import DEFAULT_DATA_ROOT, TARGET_SECTIONS, candidate_from_dict
from dataset_curation.export_candidates import export_approved_gold
from dataset_curation.generate_ears_synthetic import (
    BANNED_QUALITY_PHRASES,
    CONFIDENCE_VALUES,
    SCENARIO_BANK,
    content_fingerprint,
    generate_synthetic_candidates,
    quality_gate_rejections,
    quality_summary,
    section_pair_fingerprint,
    write_pending_review,
)
from dataset_curation.normalize_sources import _github_issue_candidate
from dataset_curation.score_candidates import score_candidate


GENERIC_PHRASES = (
    "clarify and implement the software behavior requested",
    "preserve existing public api behavior",
    "the issue text may omit exact acceptance criteria",
    "behavior described by the issue is reproducible or verifiable",
)

PROMOTIONAL_TERMS = (
    "payment link",
    "wallet address",
    "buy now",
    "discount",
    "advertising",
    "sponsored",
)


def _export_test_root(name: str) -> Path:
    root = DEFAULT_DATA_ROOT / f".test_public_gold_export_{name}"
    if root.exists():
        shutil.rmtree(root)
    return root


def _write_approved_markdown(
    data_root: Path,
    filename: str,
    *,
    candidate_id: str,
    task: str = "Add tenant-scoped audit logs to invoice exports.",
    response: str = (
        "REQUIREMENTS\n"
        "- Invoice exports must write an audit log entry for each tenant request.\n"
        "AMBIGUITIES\n"
        "- Which invoice export filters should be included in the audit record?\n"
        "ASSUMPTIONS\n"
        "- Audit logging infrastructure already exists.\n"
        "ACCEPTANCE CRITERIA\n"
        "- An invoice export creates one audit record with tenant id and actor id.\n"
        "RISKS\n"
        "- Missing audit logs can weaken billing investigations.\n"
        "CONFIDENCE\n"
        "- High"
    ),
    frontmatter_extra: str = "",
    include_response: bool = True,
) -> Path:
    approved = data_root / "product_agent" / "public_candidates" / "review" / "approved"
    approved.mkdir(parents=True, exist_ok=True)
    response_block = (
        f"""
## Candidate Response

```text
{response}
```
"""
        if include_response
        else ""
    )
    path = approved / filename
    path.write_text(
        f"""---
candidate_id: {candidate_id}
source: EARS_STYLE_PRODUCT_AGENT_SYNTHETIC
quality_score: 94
decision: pending
{frontmatter_extra}---

# EARS_STYLE_PRODUCT_AGENT_SYNTHETIC / {candidate_id}

License: CC0 original synthetic examples

URL: synthetic://product-agent/ears-style

Quality score: 94

Risk flags: synthetic, fully_authored, audit

## Candidate Task

{task}
{response_block}
""",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _github_source() -> dict:
    return {
        "source": "GitHub_Issues_Test",
        "license": "MIT",
        "url": "https://api.github.com/repos/example/project/issues",
        "risk_flags": ["github_user_generated_content", "manual_content_review"],
        "download_strategy": "github_issues",
    }


def test_default_data_root_is_repo_training_datasets() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    assert (repository_root / "training" / "datasets").resolve() == DEFAULT_DATA_ROOT


def test_approved_markdown_with_pending_decision_is_exported() -> None:
    data_root = _export_test_root("pending_decision")
    try:
        _write_approved_markdown(
            data_root,
            "approved_pending.md",
            candidate_id="approved_pending_1",
        )

        rows = export_approved_gold(data_root)

        assert len(rows) == 1
        assert rows[0]["candidate_id"] == "approved_pending_1"
        assert rows[0]["instruction"] == "Add tenant-scoped audit logs to invoice exports."
        assert rows[0]["response"].startswith("REQUIREMENTS")
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_synthetic_approved_markdown_not_in_scored_candidates_is_exported() -> None:
    data_root = _export_test_root("synthetic_without_scored")
    try:
        _write_approved_markdown(
            data_root,
            "synthetic_only.md",
            candidate_id="synthetic_only_1",
            task="Require HMAC signatures for outbound webhook deliveries.",
        )

        rows = export_approved_gold(data_root)

        assert len(rows) == 1
        assert rows[0]["instruction"] == "Require HMAC signatures for outbound webhook deliveries."
        assert rows[0]["source"] == "EARS_STYLE_PRODUCT_AGENT_SYNTHETIC"
        assert rows[0]["license"] == "CC0 original synthetic examples"
        assert rows[0]["url"] == "synthetic://product-agent/ears-style"
        assert rows[0]["risk_flags"] == ["synthetic", "fully_authored", "audit"]
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_duplicate_approved_markdown_exports_once() -> None:
    data_root = _export_test_root("dedupe")
    try:
        _write_approved_markdown(data_root, "first.md", candidate_id="duplicate_1")
        _write_approved_markdown(data_root, "same_id.md", candidate_id="duplicate_1")
        _write_approved_markdown(data_root, "same_text.md", candidate_id="duplicate_2")

        rows = export_approved_gold(data_root)

        assert len(rows) == 1
        assert rows[0]["candidate_id"] == "duplicate_1"
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_missing_candidate_response_is_skipped_with_warning() -> None:
    data_root = _export_test_root("missing_response")
    try:
        _write_approved_markdown(
            data_root,
            "missing_response.md",
            candidate_id="missing_response_1",
            include_response=False,
        )

        with pytest.warns(UserWarning, match="missing Candidate Response"):
            rows = export_approved_gold(data_root)

        assert rows == []
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_approved_markdown_export_falls_back_to_scored_metadata() -> None:
    data_root = _export_test_root("scored_fallback")
    try:
        public_root = data_root / "product_agent" / "public_candidates"
        public_root.mkdir(parents=True, exist_ok=True)
        (public_root / "scored_candidates.jsonl").write_text(
            json.dumps(
                {
                    "candidate_id": "scored_fallback_1",
                    "source": "GitHub_Issues_Test",
                    "license": "MIT",
                    "url": "https://github.com/example/project/issues/1",
                    "quality_score": 77,
                    "risk_flags": ["github_user_generated_content"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        _write_approved_markdown(
            data_root,
            "fallback.md",
            candidate_id="scored_fallback_1",
            frontmatter_extra="",
        )
        path = public_root / "review" / "approved" / "fallback.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("License: CC0 original synthetic examples\n\n", "")
        text = text.replace("URL: synthetic://product-agent/ears-style\n\n", "")
        text = text.replace("Risk flags: synthetic, fully_authored, audit\n\n", "")
        path.write_text(text, encoding="utf-8", newline="\n")

        rows = export_approved_gold(data_root)

        assert rows[0]["license"] == "MIT"
        assert rows[0]["url"] == "https://github.com/example/project/issues/1"
        assert rows[0]["risk_flags"] == ["github_user_generated_content"]
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_github_caching_issue_produces_concrete_requirements() -> None:
    issue = {
        "title": "Cache API token introspection results by tenant",
        "body": """
### Problem statement
Every request calls the token introspection endpoint even when the same tenant and token were checked seconds ago.
This creates latency spikes and causes rate limits during login bursts.

### Proposed solution
Cache successful token introspection responses by tenant id and token hash for 60 seconds.
Do not cache failed introspection responses.

### Implementation steps
- Add a cache key that includes tenant id and token hash.
- Invalidate cached introspection data when the tenant rotates signing keys.

### Testing done
- Added a regression test proving two identical requests perform one introspection call.
- Added a test proving key rotation bypasses the cache.

### Type of change
Performance improvement
""",
        "html_url": "https://github.com/example/project/issues/123",
        "labels": [{"name": "performance"}, {"name": "api"}],
        "state": "open",
    }

    candidate = _github_issue_candidate(_github_source(), issue)

    assert candidate is not None
    response = candidate.candidate_response.lower()
    assert "cache successful token introspection responses" in response
    assert "tenant id and token hash" in response
    assert "key rotation bypasses the cache" in response
    assert "clarify and implement" not in response
    assert "the issue text may omit exact acceptance criteria" not in response
    acceptance_section = response.split("acceptance criteria", maxsplit=1)[1]
    assert "cache" in acceptance_section
    assert "token introspection" in acceptance_section


def test_promotional_issue_is_flagged_and_scored_very_low() -> None:
    issue = {
        "title": "Great pricing for your API project",
        "body": (
            "Buy now with this payment link and send crypto to wallet address "
            "bc1qexamplewallet000000000000."
        ),
        "html_url": "https://github.com/example/project/issues/999",
        "labels": [{"name": "question"}],
        "state": "open",
    }

    candidate = _github_issue_candidate(_github_source(), issue)

    assert candidate is not None
    assert "promotional_or_spam" in candidate.risk_flags
    score, flags, reasons = score_candidate(candidate)
    assert score <= 10
    assert "promotional_or_spam" in flags
    assert "promotional_or_spam" in reasons


def test_generic_boilerplate_response_is_rejected() -> None:
    candidate = candidate_from_dict(
        {
            "source": "GitHub_Issues_Test",
            "license": "MIT",
            "url": "https://github.com/example/project/issues/1",
            "raw_input": "Cache API responses for repeated backend requests.",
            "raw_output": "",
            "candidate_task": "Analyze cache API issue",
            "candidate_response": (
                "REQUIREMENTS\n"
                "- Clarify and implement the software behavior requested in the issue.\n"
                "- Preserve existing public API behavior unless the issue explicitly requests a change.\n"
                "AMBIGUITIES\n"
                "- The issue text may omit exact acceptance criteria.\n"
                "ASSUMPTIONS\n"
                "- None\n"
                "ACCEPTANCE CRITERIA\n"
                "- Behavior described by the issue is reproducible or verifiable.\n"
                "RISKS\n"
                "- None\n"
                "CONFIDENCE\n"
                "- Low"
            ),
            "quality_score": 0,
            "risk_flags": [],
        }
    )

    score, flags, reasons = score_candidate(candidate)
    assert score < 40
    assert "generic_boilerplate_response" in reasons
    assert "generic_boilerplate_response" in flags


def _section_items(response: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in response.splitlines():
        if line in TARGET_SECTIONS:
            current = line
            sections[current] = []
        elif current and line.startswith("- "):
            sections[current].append(line[2:])
    return sections


def test_generated_ears_examples_have_required_sections_and_bullet_counts() -> None:
    rows = generate_synthetic_candidates(25)

    assert len(rows) == 25
    for row in rows:
        sections = _section_items(row["candidate_response"])
        assert set(TARGET_SECTIONS) == set(sections)
        assert 3 <= len(sections["REQUIREMENTS"]) <= 7
        assert 2 <= len(sections["AMBIGUITIES"]) <= 5
        assert 1 <= len(sections["ASSUMPTIONS"]) <= 4
        assert 3 <= len(sections["ACCEPTANCE CRITERIA"]) <= 7
        assert 1 <= len(sections["RISKS"]) <= 4
        assert sections["CONFIDENCE"] == [sections["CONFIDENCE"][0]]
        assert sections["CONFIDENCE"][0] in CONFIDENCE_VALUES
        assert row["license"] == "CC0 original synthetic examples"


def test_generated_ears_examples_avoid_boilerplate_and_promotional_content() -> None:
    rows = generate_synthetic_candidates(40)
    combined = "\n".join(row["candidate_response"] for row in rows).lower()

    assert not any(phrase in combined for phrase in GENERIC_PHRASES)
    assert not any(term in combined for term in PROMOTIONAL_TERMS)
    assert all("promotional_or_spam" not in row["risk_flags"] for row in rows)
    assert all(not quality_gate_rejections(row) for row in rows)


def test_generated_ears_counts_and_quality_coverage_are_respected() -> None:
    rows = generate_synthetic_candidates(50)
    summary = quality_summary(rows)

    assert len(rows) == 50
    assert summary["security_or_multi_tenant"] >= 15
    assert summary["observability_or_audit"] >= 10
    assert summary["failure_or_edge"] >= 10


def test_generated_ears_candidates_are_written_to_pending_review() -> None:
    rows = _unique_synthetic_rows("write_pending", 3)

    report = write_pending_review(rows, DEFAULT_DATA_ROOT, allow_duplicates=True)
    try:
        assert report.generated == 3
        assert report.written == 3
        assert report.skipped_duplicates == 0
        for path in report.written_paths:
            assert path.exists()
            assert path.parent == (
                DEFAULT_DATA_ROOT / "product_agent" / "public_candidates" / "review" / "pending"
            ).resolve()
            text = path.read_text(encoding="utf-8")
            assert "CC0 original synthetic examples" in text
            assert "Candidate Response" in text
    finally:
        _cleanup_paths(report.written_paths)


def _unique_synthetic_rows(prefix: str, count: int) -> list[dict]:
    rows = generate_synthetic_candidates(count)
    for index, row in enumerate(rows):
        marker = f"{prefix}_{index}"
        row["candidate_id"] = f"test_{marker}_{row['candidate_id']}"
        row["candidate_task"] = f"{row['candidate_task']} Test marker {marker}."
        row["raw_input"] = row["candidate_task"]
        row["candidate_response"] = (
            f"{row['candidate_response']}\n"
            f"ACCEPTANCE CRITERIA\n- Test marker {marker} remains unique for dedupe tests."
        )
        row["content_fingerprint"] = content_fingerprint(
            row["candidate_task"], row["candidate_response"]
        )
        row["section_fingerprint"] = section_pair_fingerprint(row["candidate_response"])
    return rows


def _cleanup_paths(paths) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def test_duplicate_candidate_response_is_skipped() -> None:
    rows = _unique_synthetic_rows("duplicate_skip", 1)
    duplicate = dict(rows[0])
    duplicate["candidate_id"] = f"{duplicate['candidate_id']}_duplicate"

    report = write_pending_review(
        [rows[0], duplicate],
        DEFAULT_DATA_ROOT,
        dedupe_existing=False,
        max_per_scenario=10,
    )
    try:
        assert report.generated == 2
        assert report.written == 1
        assert report.skipped_duplicates == 1
    finally:
        _cleanup_paths(report.written_paths)


def test_variant_only_duplicates_are_considered_duplicates() -> None:
    rows = _unique_synthetic_rows("variant_duplicate", 1)
    variant = dict(rows[0])
    variant["candidate_id"] = f"{variant['candidate_id']}_variant"
    variant["candidate_task"] = f"{rows[0]['candidate_task']} Variant 42."
    variant["content_fingerprint"] = content_fingerprint(
        variant["candidate_task"], variant["candidate_response"]
    )

    assert variant["content_fingerprint"] == rows[0]["content_fingerprint"]
    report = write_pending_review(
        [rows[0], variant],
        DEFAULT_DATA_ROOT,
        dedupe_existing=False,
        max_per_scenario=10,
    )
    try:
        assert report.written == 1
        assert report.skipped_duplicates == 1
    finally:
        _cleanup_paths(report.written_paths)


def test_pending_approved_and_rejected_participate_in_dedupe() -> None:
    review_root = DEFAULT_DATA_ROOT / "product_agent" / "public_candidates" / "review"
    created_paths = []
    for state in ("pending", "approved", "rejected"):
        rows = _unique_synthetic_rows(f"state_{state}", 1)
        first_report = write_pending_review(rows, DEFAULT_DATA_ROOT, allow_duplicates=True)
        created = first_report.written_paths[0]
        target = review_root / state / created.name
        if state != "pending":
            target.parent.mkdir(parents=True, exist_ok=True)
            created.replace(target)
        created_paths.append(target)

        second_report = write_pending_review(rows, DEFAULT_DATA_ROOT, max_per_scenario=10)
        try:
            assert second_report.written == 0
            assert second_report.skipped_duplicates == 1
        finally:
            _cleanup_paths(second_report.written_paths)

    _cleanup_paths(created_paths)


def test_allow_duplicates_bypasses_dedupe() -> None:
    rows = _unique_synthetic_rows("allow_duplicate", 1)
    duplicate = dict(rows[0])
    duplicate["candidate_id"] = f"{duplicate['candidate_id']}_duplicate"

    report = write_pending_review(
        [rows[0], duplicate],
        DEFAULT_DATA_ROOT,
        dedupe_existing=False,
        allow_duplicates=True,
    )
    try:
        assert report.generated == 2
        assert report.written == 2
        assert report.skipped_duplicates == 0
    finally:
        _cleanup_paths(report.written_paths)


def test_generated_batch_has_many_unique_task_fingerprints() -> None:
    rows = generate_synthetic_candidates(60)
    unique_fingerprints = {row["content_fingerprint"] for row in rows}

    assert len(unique_fingerprints) >= 55


def test_same_requirements_and_acceptance_with_different_task_text_is_skipped() -> None:
    rows = _unique_synthetic_rows("section_duplicate", 1)
    different_task = dict(rows[0])
    different_task["candidate_id"] = f"{different_task['candidate_id']}_different_task"
    different_task["candidate_task"] = (
        "A different task title that preserves the same requirements and acceptance criteria."
    )
    different_task["raw_input"] = different_task["candidate_task"]
    different_task["content_fingerprint"] = content_fingerprint(
        different_task["candidate_task"], different_task["candidate_response"]
    )
    different_task["section_fingerprint"] = section_pair_fingerprint(
        different_task["candidate_response"]
    )

    assert different_task["content_fingerprint"] != rows[0]["content_fingerprint"]
    assert different_task["section_fingerprint"] == rows[0]["section_fingerprint"]
    report = write_pending_review(
        [rows[0], different_task],
        DEFAULT_DATA_ROOT,
        dedupe_existing=False,
        max_per_scenario=10,
    )
    try:
        assert report.written == 1
        assert report.skipped_duplicates == 1
    finally:
        _cleanup_paths(report.written_paths)


def test_max_per_scenario_one_prevents_repeats() -> None:
    rows = _unique_synthetic_rows("max_per_scenario", 1)
    repeated = dict(rows[0])
    repeated["candidate_id"] = f"{repeated['candidate_id']}_repeat"
    repeated["candidate_task"] = f"{repeated['candidate_task']} Additional material difference."
    repeated["candidate_response"] = repeated["candidate_response"].replace(
        "No business side effects are written when validation or authorization fails.",
        "The repeated scenario writes no business data when validation fails.",
    )
    repeated["content_fingerprint"] = content_fingerprint(
        repeated["candidate_task"], repeated["candidate_response"]
    )
    repeated["section_fingerprint"] = section_pair_fingerprint(repeated["candidate_response"])

    report = write_pending_review(
        [rows[0], repeated],
        DEFAULT_DATA_ROOT,
        dedupe_existing=False,
        max_per_scenario=1,
    )
    try:
        assert report.written == 1
        assert report.skipped_max_per_scenario == 1
    finally:
        _cleanup_paths(report.written_paths)


def test_generated_50_candidates_have_50_unique_scenario_ids() -> None:
    rows = generate_synthetic_candidates(50)
    scenario_ids = {row["scenario_id"] for row in rows}

    assert len(scenario_ids) == 50


def test_generated_candidate_tasks_do_not_contain_variant() -> None:
    rows = generate_synthetic_candidates(60)

    assert all("variant" not in row["candidate_task"].lower() for row in rows)


def test_curated_scenario_bank_has_at_least_60_scenarios() -> None:
    assert len(SCENARIO_BANK) >= 60
    assert all(scenario.scenario_id for scenario in SCENARIO_BANK)


def test_generated_samples_do_not_contain_banned_quality_phrases() -> None:
    rows = generate_synthetic_candidates(60)

    for row in rows:
        text = f"{row['candidate_task']}\n{row['candidate_response']}".lower()
        assert not any(phrase in text for phrase in BANNED_QUALITY_PHRASES)
        assert not quality_gate_rejections(row)


def test_generated_50_examples_have_50_unique_scenario_ids() -> None:
    rows = generate_synthetic_candidates(50)

    assert len({row["scenario_id"] for row in rows}) == 50


def test_generated_examples_are_concrete_and_grammar_correct() -> None:
    rows = generate_synthetic_candidates(50)

    for row in rows:
        response = row["candidate_response"]
        assert " a operator " not in f" {response.lower()} "
        assert "must" in response
        sections = _section_items(response)
        assert all(len(item.split()) >= 6 for item in sections["REQUIREMENTS"])
        assert all("?" in item for item in sections["AMBIGUITIES"])


def test_generated_50_have_no_duplicate_requirements_and_acceptance() -> None:
    rows = generate_synthetic_candidates(50)
    fingerprints = [row["section_fingerprint"] for row in rows]

    assert len(fingerprints) == len(set(fingerprints))


def test_scenarios_are_fully_authored_not_slot_composed() -> None:
    for scenario in SCENARIO_BANK:
        all_text = "\n".join(
            (
                scenario.task,
                *scenario.requirements,
                *scenario.ambiguities,
                *scenario.assumptions,
                *scenario.acceptance,
                *scenario.risks,
            )
        ).lower()
        assert "{" not in all_text
        assert "}" not in all_text
        assert "expected state transition" not in all_text
        assert "clear domain error" not in all_text
        assert "validate access to" not in all_text


def test_acceptance_criteria_contain_concrete_nouns_from_task() -> None:
    stopwords = {
        "before",
        "after",
        "with",
        "from",
        "into",
        "that",
        "this",
        "when",
        "must",
        "add",
        "require",
        "support",
    }
    rows = generate_synthetic_candidates(50)
    for row in rows:
        task_terms = {
            term.rstrip("s")
            for term in row["candidate_task"].lower().replace(".", "").split()
            if len(term) >= 5 and term not in stopwords
        }
        acceptance_terms = {
            term.rstrip("s")
            for term in row["candidate_response"]
            .split("ACCEPTANCE CRITERIA", maxsplit=1)[1]
            .lower()
            .replace(".", "")
            .split()
        }
        assert task_terms & acceptance_terms
