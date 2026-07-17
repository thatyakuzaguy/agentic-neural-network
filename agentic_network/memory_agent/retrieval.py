"""Experience retrieval for ANN engineering memory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.memory_agent.runtime import (
    ENGINEERING_KNOWLEDGE_FILE,
    PATTERNS_FILE,
    STATS_FILE,
    SUCCESSFUL_REPAIRS_FILE,
    search_experience,
)
from agentic_network.safety.filesystem_policy import load_filesystem_policy

MEMORY_QUERY_FILE = "22_memory_query.md"
MEMORY_MATCHES_FILE = "23_memory_matches.md"
EXPERIENCE_CONTEXT_FILE = "24_experience_context.md"

SECTIONS_BY_FILE = {
    MEMORY_QUERY_FILE: ("MEMORY QUERY", "QUERY TERMS", "CONFIDENCE"),
    MEMORY_MATCHES_FILE: (
        "MEMORY MATCHES",
        "KNOWN PATTERNS",
        "KNOWN CONSTANTS",
        "PREVIOUS FIXES",
        "CONFIDENCE",
    ),
    EXPERIENCE_CONTEXT_FILE: (
        "EXPERIENCE CONTEXT",
        "REUSABLE PATTERNS",
        "REUSABLE CONSTANTS",
        "RELEVANT REPAIRS",
        "RECOMMENDED REUSE",
        "CONFIDENCE",
    ),
}
FORBIDDEN_TEXT_PATTERN = re.compile(
    r"(?im)(```|@@|^\+\+\+|^---|(?:^|\s)(?:rm\s+|del\s+|sudo\b|chmod\b|"
    r"powershell\b|pwsh\b|bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|"
    r"os\.system\b|eval\s*\(|exec\s*\())"
)
MOUNT_PATH_PATTERN = re.compile(r"(?<!\w)(/mnt/[a-zA-Z]/[^\s)\]]+)")


@dataclass(frozen=True)
class ExperienceContextResult:
    """Result metadata for experience context retrieval."""

    query: str
    matches: dict[str, list[dict[str, Any]]]
    patterns_used: list[str]
    constants_used: dict[str, int]
    previous_fixes: list[dict[str, Any]]
    artifacts_written: list[str]
    validation_errors: list[str]
    warnings: list[str]
    experience_context: str

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors

    @property
    def matches_found(self) -> int:
        return sum(len(values) for values in self.matches.values())


def build_experience_context(
    task: str,
    memory_root: Path,
    run_dir: Path,
    max_results: int = 5,
) -> ExperienceContextResult:
    """Retrieve engineering experience and write run-scoped memory artifacts."""

    resolved_memory_root = memory_root.resolve()
    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    path_errors = _validate_paths(resolved_memory_root, resolved_run_dir)
    errors.extend(path_errors)
    memory_errors = _validate_memory_json(resolved_memory_root, warnings)
    errors.extend(memory_errors)

    query = task.strip()
    terms = _query_terms(query)
    matches = _empty_matches()
    if not errors:
        matches = search_experience(query, max_results=max_results)

    safe_matches = _sanitize_matches(matches, warnings)
    patterns_used = _patterns_used(safe_matches)
    constants_used = _constants_used(safe_matches)
    previous_fixes = safe_matches.get("previous_fixes", [])

    query_content = _render_query(query, terms)
    matches_content = _render_matches(safe_matches)
    experience_context = _render_experience_context(
        query=query,
        patterns_used=patterns_used,
        constants_used=constants_used,
        repairs=safe_matches.get("relevant_repairs", []),
        previous_fixes=previous_fixes,
    )
    artifacts = {
        MEMORY_QUERY_FILE: query_content,
        MEMORY_MATCHES_FILE: matches_content,
        EXPERIENCE_CONTEXT_FILE: experience_context,
    }
    for filename, content in artifacts.items():
        errors.extend(validate_memory_artifact(filename, content))
    if not _path_is_safe_for_run(resolved_run_dir):
        errors.append("run_dir_not_safe_for_memory_artifacts")
    if not path_errors and not any(error.startswith("forbidden_content:") for error in errors):
        resolved_run_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in artifacts.items():
            (resolved_run_dir / filename).write_text(content.rstrip() + "\n", encoding="utf-8")

    return ExperienceContextResult(
        query=query,
        matches=safe_matches,
        patterns_used=patterns_used,
        constants_used=constants_used,
        previous_fixes=previous_fixes,
        artifacts_written=[str(resolved_run_dir / filename) for filename in artifacts],
        validation_errors=_dedupe(errors),
        warnings=_dedupe(warnings),
        experience_context=experience_context,
    )


def memory_retrieval_summary_fields(result: ExperienceContextResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "memory_retrieval_enabled": True,
        "memory_query": result.query,
        "memory_matches_found": result.matches_found,
        "memory_context_injected": bool(result.experience_context.strip()),
        "memory_patterns_used": result.patterns_used,
        "memory_constants_used": result.constants_used,
        "memory_previous_fixes_used": result.previous_fixes,
        "memory_retrieval_validation_passed": result.validation_passed,
        "memory_retrieval_validation_errors": result.validation_errors,
        "memory_retrieval_validation_warnings": result.warnings,
    }


def validate_memory_artifact(filename: str, content: str) -> list[str]:
    """Validate fixed retrieval artifact shape and safety."""

    errors: list[str] = []
    required = SECTIONS_BY_FILE.get(filename, ())
    for section in required:
        if not re.search(rf"(?m)^\s*{re.escape(section)}\s*$", content):
            errors.append(f"missing_section:{filename}:{section}")
    if not re.search(r"(?m)^CONFIDENCE\s*\nHigh\s*$", content):
        errors.append(f"confidence_not_high:{filename}")
    if FORBIDDEN_TEXT_PATTERN.search(content):
        errors.append(f"forbidden_content:{filename}")
    policy = load_filesystem_policy()
    for path_text in MOUNT_PATH_PATTERN.findall(content):
        if policy.is_path_blocked(path_text):
            errors.append(f"blocked_path_present:{filename}")
    return _dedupe(errors)


def _render_query(query: str, terms: list[str]) -> str:
    return "\n".join(
        [
            "MEMORY QUERY",
            f"- {_safe_text(query) or 'No query supplied.'}",
            "",
            "QUERY TERMS",
            *_bullets(terms or ["None"]),
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _render_matches(matches: dict[str, list[dict[str, Any]]]) -> str:
    repairs = [_repair_summary(item) for item in matches.get("relevant_repairs", [])]
    patterns = [_pattern_summary(item) for item in matches.get("known_patterns", [])]
    constants = [_constants_summary(item) for item in matches.get("known_constants", [])]
    fixes = [_fix_summary(item) for item in matches.get("previous_fixes", [])]
    return "\n".join(
        [
            "MEMORY MATCHES",
            *_bullets(repairs or ["No relevant repairs found."]),
            "",
            "KNOWN PATTERNS",
            *_bullets(patterns or ["No known patterns found."]),
            "",
            "KNOWN CONSTANTS",
            *_bullets(constants or ["No known constants found."]),
            "",
            "PREVIOUS FIXES",
            *_bullets(fixes or ["No previous fixes found."]),
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _render_experience_context(
    *,
    query: str,
    patterns_used: list[str],
    constants_used: dict[str, int],
    repairs: list[dict[str, Any]],
    previous_fixes: list[dict[str, Any]],
) -> str:
    constants = [f"{key}={value}" for key, value in constants_used.items()]
    repair_summaries = [_repair_summary(item) for item in repairs]
    recommendations = _recommendations(query, patterns_used, constants_used, previous_fixes)
    return "\n".join(
        [
            "EXPERIENCE CONTEXT",
            *_bullets([f"Retrieved engineering experience for: {_safe_text(query)}."] if query else ["No query supplied."]),
            "",
            "REUSABLE PATTERNS",
            *_bullets(patterns_used or ["No reusable patterns matched."]),
            "",
            "REUSABLE CONSTANTS",
            *_bullets(constants or ["No reusable constants matched."]),
            "",
            "RELEVANT REPAIRS",
            *_bullets(repair_summaries or ["No relevant repairs matched."]),
            "",
            "RECOMMENDED REUSE",
            *_bullets(recommendations),
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _recommendations(
    query: str,
    patterns: list[str],
    constants: dict[str, int],
    fixes: list[dict[str, Any]],
) -> list[str]:
    items: list[str] = []
    lowered = query.lower()
    if constants:
        items.append("Prefer retrieved constants for matching domains before deterministic defaults.")
    if patterns:
        items.append("Check generated changes against retrieved repair patterns.")
    if fixes:
        items.append("Review previous fixes for safe implementation strategy.")
    if "rate" in lowered and "limit" in lowered:
        items.append("Reuse rate limiting experience while preserving legitimate user paths.")
    return items or ["Proceed without memory-specific reuse recommendations."]


def _sanitize_matches(matches: dict[str, Any], warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    safe = _empty_matches()
    for key in safe:
        values = matches.get(key, []) if isinstance(matches, dict) else []
        if not isinstance(values, list):
            warnings.append(f"invalid_match_bucket:{key}")
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            cleaned = _sanitize_value(value)
            if cleaned:
                safe[key].append(cleaned)
    return safe


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _safe_text(str(key), max_chars=80)
            if safe_key in {"retry_patch", "patch"} and isinstance(item, str):
                continue
            safe_item = _sanitize_value(item)
            if not _is_empty(safe_item):
                cleaned[safe_key] = safe_item
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            safe_item = _sanitize_value(item)
            if not _is_empty(safe_item):
                cleaned_items.append(safe_item)
        return cleaned_items
    if isinstance(value, (int, float, bool)):
        return value
    text = _safe_text(str(value))
    return "" if FORBIDDEN_TEXT_PATTERN.search(text) else text


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _validate_memory_json(memory_root: Path, warnings: list[str]) -> list[str]:
    errors: list[str] = []
    if not memory_root.exists():
        warnings.append("memory_root_missing")
        return errors
    for filename in (
        PATTERNS_FILE,
        SUCCESSFUL_REPAIRS_FILE,
        ENGINEERING_KNOWLEDGE_FILE,
        STATS_FILE,
    ):
        path = memory_root / filename
        if not path.exists():
            warnings.append(f"memory_file_missing:{filename}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"invalid_memory_json:{filename}")
        except OSError:
            errors.append(f"memory_file_unreadable:{filename}")
    return errors


def _validate_paths(memory_root: Path, run_dir: Path) -> list[str]:
    errors: list[str] = []
    policy = load_filesystem_policy()
    project_root = policy.project_root.resolve()
    for label, path in (("memory_root", memory_root),):
        if ".." in str(path).replace("\\", "/").split("/"):
            errors.append(f"{label}_path_traversal")
        if policy.is_path_blocked(path):
            errors.append(f"{label}_blocked")
        if not policy.is_path_allowed(path):
            errors.append(f"{label}_outside_allowed_roots")
        try:
            path.resolve().relative_to(project_root)
        except ValueError:
            errors.append(f"{label}_outside_project_root")
    if ".." in str(run_dir).replace("\\", "/").split("/"):
        errors.append("run_dir_path_traversal")
    if policy.is_path_blocked(run_dir):
        errors.append("run_dir_blocked")
    return _dedupe(errors)


def _path_is_safe_for_run(run_dir: Path) -> bool:
    policy = load_filesystem_policy()
    return ".." not in str(run_dir).replace("\\", "/").split("/") and not policy.is_path_blocked(run_dir)


def _query_terms(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9_]{3,}", query.lower())
    return _dedupe(tokens)[:12]


def _patterns_used(matches: dict[str, list[dict[str, Any]]]) -> list[str]:
    patterns: list[str] = []
    for item in matches.get("known_patterns", []):
        value = str(item.get("pattern_id") or item.get("description") or item.get("recommended_fix") or "").strip()
        if value:
            patterns.append(value)
    return _dedupe(patterns)


def _constants_used(matches: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    constants: dict[str, int] = {}
    for item in matches.get("known_constants", []):
        payload = item.get("constants", {})
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if isinstance(value, int):
                constants[str(key)] = value
    return constants


def _repair_summary(item: dict[str, Any]) -> str:
    task = _safe_text(str(item.get("task", "Previous repair")))
    strategy = ""
    fix = item.get("fix", {})
    if isinstance(fix, dict):
        strategy = _safe_text(str(fix.get("strategy", "")))
    return f"{task} using {strategy or 'recorded strategy'}"


def _pattern_summary(item: dict[str, Any]) -> str:
    return _safe_text(
        str(item.get("pattern_id") or item.get("description") or item.get("recommended_fix") or "Recorded pattern")
    )


def _constants_summary(item: dict[str, Any]) -> str:
    domain = _safe_text(str(item.get("domain", "known_domain")))
    constants = item.get("constants", {})
    if isinstance(constants, dict):
        values = ", ".join(f"{_safe_text(str(key))}={value}" for key, value in constants.items() if isinstance(value, int))
        return f"{domain}: {values or 'no numeric constants'}"
    return domain


def _fix_summary(item: dict[str, Any]) -> str:
    return _safe_text(str(item.get("strategy") or item.get("repair_id") or "Previous fix"))


def _safe_text(value: str, *, max_chars: int = 180) -> str:
    text = re.sub(r"[\r\n\t]+", " ", value)
    text = re.sub(r"[^A-Za-z0-9 .,;:_=/()'\"-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def _empty_matches() -> dict[str, list[dict[str, Any]]]:
    return {
        "relevant_repairs": [],
        "known_patterns": [],
        "known_constants": [],
        "previous_fixes": [],
    }


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items or ["None"]]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output
