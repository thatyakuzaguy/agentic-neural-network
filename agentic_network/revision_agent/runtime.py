"""Artifact-only Revision Agent runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CODE_REVISED_OUTPUT_FILE = "03_code_revised.md"
TEST_REVISED_OUTPUT_FILE = "04_tests_revised.md"
SECURITY_REVISED_OUTPUT_FILE = "05_security_revised.md"
REVISION_SUMMARY_OUTPUT_FILE = "10_revision_summary.md"

SOURCE_ARTIFACTS = {
    "code": "03_code.md",
    "test": "04_tests.md",
    "security": "05_security.md",
    "reviewer": "06_review.md",
    "fixer": "07_fix_plan.md",
}

SECTION_KEYS = {
    "CODE CHANGES": "code_changes",
    "TEST CHANGES": "test_changes",
    "SECURITY CHANGES": "security_changes",
    "REVISION SUMMARY": "revision_summary",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTIONS = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in REQUIRED_SECTIONS) + r")\s*$",
    re.IGNORECASE,
)
GENERIC_SECTION_LINE = re.compile(r"^\s*([A-Z][A-Z0-9 /_-]{2,})\s*$")
BULLET_LINE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
NUMBERED_LIST_LINE = re.compile(r"^\s*\d+[\.)]\s+(.+?)\s*$")
PATCH_MARKER_LINE = re.compile(
    r"(?im)^\s*(?:[-*]\s+)?(?:\+\+\+|---|@@|diff --git|Index:|patch\b)(?:\s|$)"
)
CODE_FENCE = "```"
FORBIDDEN_CODE_PATTERNS = {
    "code_fence_present": re.compile(re.escape(CODE_FENCE)),
    "patch_markers_present": PATCH_MARKER_LINE,
    "import_present": re.compile(r"\b(?:import|from)\s+"),
    "definition_present": re.compile(r"\b(?:def|class)\s+"),
    "decorator_present": re.compile(r"(?m)^\s*@"),
    "control_flow_present": re.compile(r"\b(?:return|raise|except)\s+|\btry\s*:"),
}

SKIP_PHRASES = (
    "none",
    "no ",
    "not applicable",
    "n/a",
    "no significant",
    "no requirement",
    "no architecture",
    "no implementation",
    "no test",
    "no security",
)

CODE_SECTION_HINTS = {
    "REQUIREMENT GAPS",
    "ARCHITECTURE GAPS",
    "IMPLEMENTATION RISKS",
    "RECOMMENDATIONS",
    "FIX SUMMARY",
    "REQUIREMENT FIXES",
    "ARCHITECTURE FIXES",
    "IMPLEMENTATION FIXES",
    "PRIORITY ORDER",
}
TEST_SECTION_HINTS = {"TEST COVERAGE GAPS", "TEST FIXES"}
SECURITY_SECTION_HINTS = {"SECURITY GAPS", "SECURITY FIXES"}

TEST_KEYWORDS = ("test", "coverage", "scenario", "case", "regression", "automation")
SECURITY_KEYWORDS = (
    "security",
    "abuse",
    "threat",
    "attack",
    "attacker",
    "authorization",
    "authentication",
    "generic feedback",
    "enumeration",
)


@dataclass(frozen=True)
class RevisionResult:
    """Metadata and generated content for an artifact-only revision pass."""

    run_dir: str
    revised_code: str
    revised_tests: str
    revised_security: str
    revision_summary: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    artifact_path: str
    code_artifact_path: str
    test_artifact_path: str
    security_artifact_path: str
    artifacts_generated: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def apply_revisions(run_dir: Path) -> RevisionResult:
    """Revise planning artifacts using reviewer findings and fixer recommendations."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    sources = _load_sources(resolved_run_dir, warnings)
    review_items = _extract_items_by_section(sources.get("reviewer", ""))
    fixer_items = _extract_items_by_section(sources.get("fixer", ""))
    derived = _derive_revision_items(review_items, fixer_items)

    revised_code = _append_revision_additions(
        sources.get("code", ""),
        "REVISION ADDITIONS",
        derived["code"],
        fallback="No code revisions were identified from reviewer findings or fixer recommendations.",
    )
    revised_tests = _append_revision_additions(
        sources.get("test", ""),
        "REVISION ADDITIONS",
        derived["test"],
        fallback="No test revisions were identified from reviewer findings or fixer recommendations.",
    )
    revised_security = _append_revision_additions(
        sources.get("security", ""),
        "REVISION ADDITIONS",
        derived["security"],
        fallback="No security revisions were identified from reviewer findings or fixer recommendations.",
    )
    if not any(derived.values()):
        warnings.append("no_actionable_review_or_fixer_items")

    revision_summary = _render_revision_summary(
        code_changes=derived["code"],
        test_changes=derived["test"],
        security_changes=derived["security"],
    )
    parsed_sections = parse_revision_sections(revision_summary)
    validation_errors = validate_revision_summary(revision_summary, parsed_sections)

    code_path = resolved_run_dir / CODE_REVISED_OUTPUT_FILE
    test_path = resolved_run_dir / TEST_REVISED_OUTPUT_FILE
    security_path = resolved_run_dir / SECURITY_REVISED_OUTPUT_FILE
    summary_path = resolved_run_dir / REVISION_SUMMARY_OUTPUT_FILE
    code_path.write_text(revised_code.rstrip() + "\n", encoding="utf-8")
    test_path.write_text(revised_tests.rstrip() + "\n", encoding="utf-8")
    security_path.write_text(revised_security.rstrip() + "\n", encoding="utf-8")
    summary_path.write_text(revision_summary.rstrip() + "\n", encoding="utf-8")

    return RevisionResult(
        run_dir=str(resolved_run_dir),
        revised_code=revised_code,
        revised_tests=revised_tests,
        revised_security=revised_security,
        revision_summary=revision_summary,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        artifact_path=str(summary_path),
        code_artifact_path=str(code_path),
        test_artifact_path=str(test_path),
        security_artifact_path=str(security_path),
        artifacts_generated=[
            CODE_REVISED_OUTPUT_FILE,
            TEST_REVISED_OUTPUT_FILE,
            SECURITY_REVISED_OUTPUT_FILE,
            REVISION_SUMMARY_OUTPUT_FILE,
        ],
    )


def parse_revision_sections(content: str) -> dict[str, list[str] | str]:
    """Parse the fixed Revision Agent summary format."""

    parsed: dict[str, list[str] | str] = {}
    current_heading: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = SECTION_LINE.match(line)
        if match:
            current_heading = match.group(1).upper()
            key = SECTION_KEYS[current_heading]
            parsed[key] = "" if current_heading == "CONFIDENCE" else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading == "CONFIDENCE":
            parsed[key] = line.lstrip("- ").strip()
        elif line.startswith(("- ", "* ")):
            value = parsed.setdefault(key, [])
            if isinstance(value, list):
                value.append(line[2:].strip())
    return parsed


def validate_revision_summary(
    content: str,
    parsed_sections: dict[str, list[str] | str],
) -> list[str]:
    """Validate the Revision Agent summary contract."""

    errors: list[str] = []
    counts = _section_counts(content)
    for title, key in SECTION_KEYS.items():
        count = counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section:{title}")
        elif count > 1:
            errors.append(f"duplicate_section:{title}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section:{title}")
    for title, key in SECTION_KEYS.items():
        value = parsed_sections.get(key, "")
        if title == "CONFIDENCE":
            if str(value).strip() != "High":
                errors.append("confidence_not_high")
        elif not isinstance(value, list) or not value:
            errors.append(f"empty_section:{title}")
    if re.search(r"(?m)^\s*#{1,6}\s+", content):
        errors.append("markdown_headings_present")
    for name, pattern in FORBIDDEN_CODE_PATTERNS.items():
        if pattern.search(content):
            errors.append(name)
    return errors


def _load_sources(run_dir: Path, warnings: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key, filename in SOURCE_ARTIFACTS.items():
        path = run_dir / filename
        if path.exists():
            sources[key] = path.read_text(encoding="utf-8").strip()
        else:
            warnings.append(f"missing_artifact:{filename}")
            sources[key] = ""
    return sources


def _extract_items_by_section(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading_match = GENERIC_SECTION_LINE.match(stripped)
        if heading_match and not stripped.startswith(("-", "*")):
            current_heading = heading_match.group(1).upper()
            sections.setdefault(current_heading, [])
            continue
        bullet_match = BULLET_LINE.match(stripped) or NUMBERED_LIST_LINE.match(stripped)
        if current_heading and bullet_match:
            item = _sanitize_item(bullet_match.group(1))
            if item and not _should_skip_item(item):
                sections.setdefault(current_heading, []).append(item)
    return sections


def _derive_revision_items(
    review_items: dict[str, list[str]],
    fixer_items: dict[str, list[str]],
) -> dict[str, list[str]]:
    buckets = {"code": [], "test": [], "security": []}
    for source in (review_items, fixer_items):
        for heading, items in source.items():
            for item in items:
                normalized_items = _normalize_revision_item(item)
                for normalized in normalized_items:
                    bucket_names = _buckets_for_item(heading, normalized)
                    for bucket_name in bucket_names:
                        buckets[bucket_name].append(normalized)
    return {key: _dedupe(values) for key, values in buckets.items()}


def _normalize_revision_item(item: str) -> list[str]:
    lowered = item.lower()
    normalized: list[str] = []
    if "retry window" in lowered or "retry windows" in lowered:
        normalized.append("Add configurable retry windows.")
    if "escalation threshold" in lowered or "escalation thresholds" in lowered:
        normalized.append("Add escalation thresholds for repeated or severe cases.")
    if "identifier rotation" in lowered:
        normalized.append("Account for identifier rotation handling.")
    if "identifier tracking" in lowered or "identifier track" in lowered:
        normalized.append("Track relevant request identifiers consistently across the planned flow.")
    if normalized:
        return normalized

    text = item.strip().rstrip(".")
    text = re.sub(r"^(?:missing|add|include|ensure|address|cover)\s+", "", text, flags=re.I).strip()
    if not text:
        return []
    first = text[0].upper() + text[1:]
    if re.search(r"\b(?:window|threshold|policy|tracking|handling|feedback|limit|coverage|test|security|mitigation)s?\b", first, re.I):
        return [f"Add {first}."]
    return [f"Incorporate {first}."]


def _buckets_for_item(heading: str, item: str) -> list[str]:
    heading = heading.upper()
    if heading in TEST_SECTION_HINTS:
        return ["test"]
    if heading in SECURITY_SECTION_HINTS:
        return ["security"]
    if heading in CODE_SECTION_HINTS:
        buckets = ["code"]
    else:
        buckets = ["code"]
    lowered = item.lower()
    if any(keyword in lowered for keyword in TEST_KEYWORDS):
        buckets.append("test")
    if any(keyword in lowered for keyword in SECURITY_KEYWORDS):
        buckets.append("security")
    return _dedupe(buckets)


def _append_revision_additions(
    original: str,
    heading: str,
    additions: list[str],
    *,
    fallback: str,
) -> str:
    base = original.strip() or "Original artifact was not available."
    cleaned_additions = [_sanitize_item(item) for item in additions if _sanitize_item(item)]
    if not cleaned_additions:
        cleaned_additions = [fallback]
    lines = [base, "", heading]
    lines.extend(f"- {item}" for item in _dedupe(cleaned_additions))
    return "\n".join(lines).strip()


def _render_revision_summary(
    *,
    code_changes: list[str],
    test_changes: list[str],
    security_changes: list[str],
) -> str:
    safe_code = code_changes or ["No code artifact changes were required by reviewer or fixer inputs."]
    safe_tests = test_changes or ["No test artifact changes were required by reviewer or fixer inputs."]
    safe_security = security_changes or ["No security artifact changes were required by reviewer or fixer inputs."]
    summary_items = [
        "Created revised code, test, and security planning artifacts.",
        "Incorporated reviewer findings and fixer recommendations without applying repository changes.",
        "Kept revisions at artifact-planning level only.",
    ]
    lines: list[str] = []
    for heading, items in (
        ("CODE CHANGES", safe_code),
        ("TEST CHANGES", safe_tests),
        ("SECURITY CHANGES", safe_security),
        ("REVISION SUMMARY", summary_items),
    ):
        lines.append(heading)
        lines.extend(f"- {_sanitize_item(item)}" for item in _dedupe(items))
        lines.append("")
    lines.extend(["CONFIDENCE", "High"])
    return "\n".join(lines).strip()


def _sanitize_item(item: str) -> str:
    text = item.replace("`", "").strip()
    text = text.replace("```", "")
    text = re.sub(r"\s+", " ", text)
    if PATCH_MARKER_LINE.search(text):
        return ""
    if any(pattern.search(text) for pattern in FORBIDDEN_CODE_PATTERNS.values()):
        return ""
    return text.strip()


def _should_skip_item(item: str) -> bool:
    lowered = item.lower().strip()
    return any(lowered.startswith(phrase) for phrase in SKIP_PHRASES)


def _section_counts(content: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTIONS}
    for line in content.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
