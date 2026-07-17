"""Build a non-LLM reusable context briefing from the local knowledge base."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.memory_agent.retrieval import (
    ExperienceContextResult,
    build_experience_context,
)

CONTEXT_OUTPUT_FILE = "00_context.md"
SECTIONS = (
    "PROJECT CONTEXT",
    "RELATED PATTERNS",
    "RELEVANT LESSONS",
    "SIMILAR RUNS",
    "KNOWN RISKS",
    "RECOMMENDED FOCUS",
    "Experience Memory",
    "CONTEXT CONFIDENCE",
)
CODE_MARKERS = (
    "```",
    "```python",
    "def ",
    "class ",
    "import ",
    "from ",
    "return ",
    "raise ",
    "except ",
    "try:",
    "+++",
    "---",
    "@@",
)
CONCEPT_KEYWORDS = {
    "rate_limiting": ("rate", "limit", "limits", "limiting", "throttle", "excessive"),
    "authentication": ("auth", "authentication", "login", "password", "credential"),
    "account_recovery": ("password", "reset", "recovery", "recover", "account"),
    "abuse_prevention": ("abuse", "attacker", "excessive", "spam", "automated"),
    "pagination": ("pagination", "paginated", "page"),
    "notifications": ("notification", "email", "message"),
    "search": ("search", "query", "filter"),
    "retry_policies": ("retry", "retries", "backoff"),
}


@dataclass(frozen=True)
class ContextResult:
    """Result metadata for a context briefing build."""

    task: str
    matched_patterns: list[str]
    matched_lessons: list[str]
    matched_runs: list[str]
    context_artifact: str
    warnings: list[str]
    validation_errors: list[str]
    experience_context_result: ExperienceContextResult | None = None


def build_context(
    task: str,
    knowledge_root: Path,
    *,
    run_dir: Path | None = None,
    memory_root: Path | None = None,
) -> ContextResult:
    """Build a context briefing using only the local knowledge base."""

    root = knowledge_root.resolve()
    warnings: list[str] = []
    knowledge = _load_knowledge(root, warnings)
    experience_result: ExperienceContextResult | None = None
    if run_dir is not None:
        experience_result = build_experience_context(
            task,
            memory_root or root.parent / "memory",
            run_dir,
        )
        warnings.extend(experience_result.warnings)
    task_tokens = _tokens(task)
    task_lower = task.lower()

    matched_patterns = _match_patterns(task_tokens, task_lower, knowledge["patterns"])
    matched_lessons = _match_lessons(task_tokens, task_lower, knowledge["lessons"], matched_patterns)
    matched_runs = _match_runs(task_tokens, task_lower, knowledge["runs"], matched_patterns)
    known_risks = _known_risks(task_lower, matched_patterns, matched_lessons)
    focus = _recommended_focus(task_lower, matched_patterns, matched_lessons)
    project_context = _project_context(matched_patterns, matched_runs)

    content = _render_context(
        project_context=project_context,
        related_patterns=matched_patterns or ["No related reusable patterns found in local knowledge."],
        relevant_lessons=matched_lessons or ["No relevant reusable lessons found in local knowledge."],
        similar_runs=matched_runs or ["No similar prior runs found in local knowledge."],
        known_risks=known_risks,
        recommended_focus=focus,
        experience_memory=_experience_memory_bullets(experience_result),
    )
    parsed = parse_context_sections(content)
    validation_errors = validate_context_briefing(content, parsed)
    return ContextResult(
        task=task,
        matched_patterns=matched_patterns,
        matched_lessons=matched_lessons,
        matched_runs=matched_runs,
        context_artifact=content,
        warnings=warnings,
        validation_errors=validation_errors,
        experience_context_result=experience_result,
    )


def parse_context_sections(content: str) -> dict[str, str]:
    """Parse fixed Context Agent sections."""

    parsed: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    headings = set(SECTIONS)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in headings:
            if current is not None:
                parsed[_section_key(current)] = "\n".join(buffer).strip()
            current = stripped
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        parsed[_section_key(current)] = "\n".join(buffer).strip()
    return parsed


def validate_context_briefing(content: str, parsed: dict[str, str]) -> list[str]:
    """Validate the context briefing contract."""

    errors: list[str] = []
    for section in SECTIONS:
        key = _section_key(section)
        value = parsed.get(key, "").strip()
        if not value:
            errors.append(f"missing_section:{section}")
            continue
        if section != "CONTEXT CONFIDENCE":
            bullets = [line for line in value.splitlines() if line.strip().startswith("- ")]
            if not bullets:
                errors.append(f"section_missing_bullet:{section}")
    if parsed.get("context_confidence", "").strip() != "High":
        errors.append("invalid_context_confidence")
    lowered = content.lower()
    for marker in CODE_MARKERS:
        if marker.lower() in lowered:
            errors.append(f"forbidden_code_marker:{marker.strip()}")
    return errors


def _load_knowledge(root: Path, warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not root.exists():
        warnings.append("missing_knowledge_root")
        return {"patterns": [], "lessons": [], "runs": []}
    data = {
        "patterns": _load_json_dir(root / "patterns", warnings, "patterns"),
        "lessons": _load_json_dir(root / "lessons", warnings, "lessons"),
        "runs": _load_json_dir(root / "runs", warnings, "runs"),
    }
    index_path = root / "index.json"
    if not index_path.exists():
        warnings.append("missing_knowledge_index")
    return data


def _load_json_dir(path: Path, warnings: list[str], label: str) -> list[dict[str, Any]]:
    if not path.exists():
        warnings.append(f"missing_knowledge_{label}_dir")
        return []
    records: list[dict[str, Any]] = []
    for file_path in sorted(path.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append(f"invalid_knowledge_json:{file_path.name}")
            continue
        if isinstance(payload, dict):
            payload.setdefault("_source", file_path.stem)
            records.append(payload)
    return records


def _match_patterns(
    task_tokens: set[str], task_lower: str, patterns: list[dict[str, Any]]
) -> list[str]:
    matches: list[str] = []
    for record in patterns:
        pattern_id = str(record.get("id") or record.get("_source") or "")
        text = " ".join(str(record.get(key, "")) for key in ("id", "pattern"))
        if _record_matches(pattern_id, text, task_tokens, task_lower):
            pattern = str(record.get("pattern") or pattern_id.replace("_", " ")).strip()
            if pattern:
                matches.append(pattern)
    return _dedupe(matches)


def _match_lessons(
    task_tokens: set[str],
    task_lower: str,
    lessons: list[dict[str, Any]],
    matched_patterns: list[str],
) -> list[str]:
    pattern_text = " ".join(matched_patterns).lower()
    matches: list[str] = []
    for record in lessons:
        lesson = str(record.get("lesson") or "").strip()
        if not lesson:
            continue
        lesson_lower = lesson.lower()
        if _overlap(task_tokens, _tokens(lesson_lower)) or any(
            token in lesson_lower for token in _tokens(pattern_text)
        ):
            matches.append(lesson)
    return _dedupe(matches)


def _match_runs(
    task_tokens: set[str],
    task_lower: str,
    runs: list[dict[str, Any]],
    matched_patterns: list[str],
) -> list[str]:
    matches: list[str] = []
    pattern_text = " ".join(matched_patterns).lower()
    for record in runs:
        task = str(record.get("task") or "")
        patterns = " ".join(str(item) for item in record.get("reusable_patterns", []))
        haystack = f"{task} {patterns}".lower()
        if _overlap(task_tokens, _tokens(haystack)) or any(
            token in haystack for token in _tokens(pattern_text)
        ):
            run_id = str(record.get("run_id") or record.get("_source") or "previous_run")
            if "rate" in haystack and "limit" in haystack:
                matches.append(f"{run_id}: previous rate-limiting workflow.")
            elif "auth" in haystack or "password" in haystack or "recovery" in haystack:
                matches.append(f"{run_id}: previous authentication-related workflow.")
            else:
                matches.append(f"{run_id}: previous related workflow.")
    return _dedupe(matches)[:5]


def _known_risks(task_lower: str, patterns: list[str], lessons: list[str]) -> list[str]:
    text = " ".join([task_lower, *patterns, *lessons]).lower()
    risks: list[str] = []
    if "rate" in text and "limit" in text:
        risks.append("Excessively strict limits may impact legitimate users.")
        risks.append("Weak controls may allow repeated abuse.")
    if "account" in text or "password" in text or "recovery" in text:
        risks.append("User-facing messaging can accidentally reveal account state.")
    return risks or ["No known reusable risks matched the current task."]


def _recommended_focus(task_lower: str, patterns: list[str], lessons: list[str]) -> list[str]:
    text = " ".join([task_lower, *patterns, *lessons]).lower()
    focus: list[str] = []
    if "rate" in text and "limit" in text:
        focus.append("Maintain balance between security and usability.")
        focus.append("Verify limited workflows remain functional for legitimate users.")
    if "account" in text or "password" in text or "recovery" in text:
        focus.append("Keep account recovery messaging clear and non-revealing.")
    return focus or ["Proceed with the standard artifact-only planning flow."]


def _project_context(patterns: list[str], runs: list[str]) -> list[str]:
    context: list[str] = []
    joined = " ".join(patterns + runs).lower()
    if "authentication" in joined or "account" in joined or "password" in joined:
        context.append("Similar authentication-related workflows have been processed previously.")
    if patterns:
        context.append("Reusable knowledge is available for the current task domain.")
    if runs:
        context.append("Previous ANN runs provide related context for this request.")
    return context or ["No prior reusable project context matched the current task."]


def _render_context(
    *,
    project_context: list[str],
    related_patterns: list[str],
    relevant_lessons: list[str],
    similar_runs: list[str],
    known_risks: list[str],
    recommended_focus: list[str],
    experience_memory: list[str],
) -> str:
    parts: list[str] = []
    for heading, bullets in (
        ("PROJECT CONTEXT", project_context),
        ("RELATED PATTERNS", related_patterns),
        ("RELEVANT LESSONS", relevant_lessons),
        ("SIMILAR RUNS", similar_runs),
        ("KNOWN RISKS", known_risks),
        ("RECOMMENDED FOCUS", recommended_focus),
        ("Experience Memory", experience_memory),
    ):
        parts.append(heading)
        parts.extend(f"- {item}" for item in _dedupe(bullets))
        parts.append("")
    parts.extend(["CONTEXT CONFIDENCE", "High", ""])
    return "\n".join(parts)


def _experience_memory_bullets(result: ExperienceContextResult | None) -> list[str]:
    if result is None:
        return ["Experience memory retrieval was not requested for this context build."]
    bullets: list[str] = []
    if result.patterns_used:
        bullets.append("Reusable patterns: " + ", ".join(result.patterns_used[:5]) + ".")
    if result.constants_used:
        values = ", ".join(f"{key}={value}" for key, value in result.constants_used.items())
        bullets.append("Reusable constants: " + values + ".")
    if result.previous_fixes:
        bullets.append(f"Previous fixes available: {len(result.previous_fixes)}.")
    if result.validation_errors:
        bullets.append("Experience memory retrieval completed with validation warnings for review.")
    return bullets or ["No matching engineering experience memory found."]


def _record_matches(
    record_id: str, text: str, task_tokens: set[str], task_lower: str
) -> bool:
    record_tokens = _tokens(f"{record_id} {text}")
    if _overlap(task_tokens, record_tokens):
        return True
    if record_id == "abuse_prevention" and "rate" in task_lower and "limit" in task_lower:
        return True
    keywords = CONCEPT_KEYWORDS.get(record_id, ())
    return any(keyword in task_lower for keyword in keywords)


def _tokens(value: str) -> set[str]:
    raw = set(re.findall(r"[a-z0-9]+", value.lower()))
    expanded = set(raw)
    if "limits" in raw or "limited" in raw or "limiting" in raw:
        expanded.add("limit")
    if "reset" in raw or "recovery" in raw:
        expanded.add("account")
    return {token for token in expanded if len(token) > 2}


def _overlap(left: set[str], right: set[str]) -> bool:
    return bool(left & right)


def _section_key(section: str) -> str:
    return section.lower().replace(" ", "_")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item.strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output
