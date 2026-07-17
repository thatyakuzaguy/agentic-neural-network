"""Capture reusable, non-LLM knowledge from ANN run artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KNOWLEDGE_OUTPUT_FILE = "10_knowledge_capture.md"
SUMMARY_FILE = "summary.json"
SECTIONS = (
    "LESSONS LEARNED",
    "REUSABLE PATTERNS",
    "PRODUCT INSIGHTS",
    "ARCHITECTURE INSIGHTS",
    "TESTING INSIGHTS",
    "SECURITY INSIGHTS",
    "FUTURE REUSE SCORE",
    "CONFIDENCE",
)
OPTIONAL_ARTIFACTS = {
    "09_handoff_bundle.md",
    "repository_intelligence/project_summary.json",
    "26_repository_context.md",
    "26_repository_context.json",
    "13_patch_apply.md",
    "14_test_run.md",
    "15_merge_readiness.md",
    "16_human_approval.md",
    "17_failure_analysis.md",
    "18_root_cause.md",
    "21_self_healing.md",
    "25_patch_quality.md",
}
ARTIFACTS = (
    "repository_intelligence/project_summary.json",
    "26_repository_context.md",
    "26_repository_context.json",
    "01_product_requirements.md",
    "02_architecture_plan.md",
    "03_code.md",
    "04_tests.md",
    "05_security.md",
    "06_review.md",
    "07_fix_plan.md",
    "08_final_review.md",
    "11_execution_plan.md",
    "25_patch_quality.md",
    "12_patch_approval.md",
    "13_patch_apply.md",
    "14_test_run.md",
    "17_failure_analysis.md",
    "18_root_cause.md",
    "15_merge_readiness.md",
    "16_human_approval.md",
    "21_self_healing.md",
    "09_handoff_bundle.md",
)
CONCEPT_PATTERNS = {
    "rate_limiting": {
        "label": "Rate-limited user actions.",
        "keywords": ("rate limit", "rate-limit", "rate limiting", "limits are enforced"),
    },
    "pagination": {
        "label": "Paginated collection access.",
        "keywords": ("pagination", "paginated", "page size"),
    },
    "authentication": {
        "label": "Authentication-sensitive workflow controls.",
        "keywords": ("authentication", "auth", "login", "password"),
    },
    "account_recovery": {
        "label": "Account recovery flow safeguards.",
        "keywords": ("password reset", "account recovery", "reset instructions", "recovery flow"),
    },
    "notifications": {
        "label": "User notification controls.",
        "keywords": ("notification", "email", "message"),
    },
    "search": {
        "label": "Search behavior constraints.",
        "keywords": ("search", "query", "filter"),
    },
    "retry_policies": {
        "label": "Retry and backoff policies.",
        "keywords": ("retry", "backoff", "retries"),
    },
    "abuse_prevention": {
        "label": "Abuse prevention controls.",
        "keywords": ("abuse", "attacker", "excessive", "automated"),
    },
}
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


@dataclass(frozen=True)
class KnowledgeCaptureResult:
    """Result metadata for a knowledge capture run."""

    run_dir: str
    artifact_path: str
    reusable_patterns: list[str]
    lessons: list[str]
    warnings: list[str]
    validation_errors: list[str]
    future_reuse_score: str
    confidence: str


def capture_knowledge(run_dir: Path) -> KnowledgeCaptureResult:
    """Create knowledge artifacts for a completed or partial ANN run."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    artifacts = _load_artifacts(resolved_run_dir, warnings)
    all_text = "\n\n".join([json.dumps(summary), *artifacts.values()])
    lower_text = all_text.lower()

    concepts = _detect_concepts(lower_text)
    lessons = _extract_lessons(lower_text, concepts)
    reusable_patterns = [CONCEPT_PATTERNS[key]["label"] for key in concepts]
    product_insights = _product_insights(lower_text, concepts)
    architecture_insights = _architecture_insights(lower_text, concepts)
    testing_insights = _testing_insights(lower_text, concepts)
    security_insights = _security_insights(lower_text, concepts)
    score = _future_reuse_score(concepts, lessons, security_insights)
    confidence = "High"

    content = _render_capture(
        lessons=lessons,
        reusable_patterns=reusable_patterns or [
            "No reusable patterns identified in available artifacts."
        ],
        product_insights=product_insights,
        architecture_insights=architecture_insights,
        testing_insights=testing_insights,
        security_insights=security_insights,
        future_reuse_score=score,
        confidence=confidence,
    )
    artifact_path = resolved_run_dir / KNOWLEDGE_OUTPUT_FILE
    artifact_path.write_text(content, encoding="utf-8")

    parsed = parse_knowledge_capture_sections(content)
    validation_errors = validate_knowledge_capture(content, parsed)
    _persist_knowledge(
        run_dir=resolved_run_dir,
        summary=summary,
        concepts=concepts,
        reusable_patterns=reusable_patterns,
        lessons=lessons,
        security_insights=security_insights,
        future_reuse_score=score,
    )
    return KnowledgeCaptureResult(
        run_dir=str(resolved_run_dir),
        artifact_path=str(artifact_path),
        reusable_patterns=reusable_patterns,
        lessons=lessons,
        warnings=warnings,
        validation_errors=validation_errors,
        future_reuse_score=score,
        confidence=confidence,
    )


def parse_knowledge_capture_sections(content: str) -> dict[str, str]:
    """Parse the fixed knowledge capture section format."""

    parsed: dict[str, str] = {}
    lines = content.splitlines()
    current: str | None = None
    buffer: list[str] = []
    headings = set(SECTIONS)
    for line in lines:
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


def validate_knowledge_capture(content: str, parsed: dict[str, str]) -> list[str]:
    """Validate the knowledge capture artifact contract."""

    errors: list[str] = []
    for section in SECTIONS:
        key = _section_key(section)
        value = parsed.get(key, "").strip()
        if not value:
            errors.append(f"missing_section:{section}")
            continue
        if section not in {"FUTURE REUSE SCORE", "CONFIDENCE"}:
            bullets = [line for line in value.splitlines() if line.strip().startswith("- ")]
            if not bullets:
                errors.append(f"section_missing_bullet:{section}")
    score = parsed.get("future_reuse_score", "").strip()
    if score not in {"Low", "Medium", "High"}:
        errors.append("invalid_future_reuse_score")
    if parsed.get("confidence", "").strip() != "High":
        errors.append("invalid_confidence")
    lowered = content.lower()
    for marker in CODE_MARKERS:
        if marker.lower() in lowered:
            errors.append(f"forbidden_code_marker:{marker.strip()}")
    return errors


def _render_capture(
    *,
    lessons: list[str],
    reusable_patterns: list[str],
    product_insights: list[str],
    architecture_insights: list[str],
    testing_insights: list[str],
    security_insights: list[str],
    future_reuse_score: str,
    confidence: str,
) -> str:
    parts: list[str] = []
    bullet_sections = (
        ("LESSONS LEARNED", lessons),
        ("REUSABLE PATTERNS", reusable_patterns),
        ("PRODUCT INSIGHTS", product_insights),
        ("ARCHITECTURE INSIGHTS", architecture_insights),
        ("TESTING INSIGHTS", testing_insights),
        ("SECURITY INSIGHTS", security_insights),
    )
    for heading, bullets in bullet_sections:
        parts.append(heading)
        parts.extend(f"- {bullet}" for bullet in _dedupe(bullets))
        parts.append("")
    parts.extend(["FUTURE REUSE SCORE", future_reuse_score, "", "CONFIDENCE", confidence, ""])
    return "\n".join(parts)


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_artifacts(run_dir: Path, warnings: list[str]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for filename in ARTIFACTS:
        path = run_dir / filename
        if path.exists():
            artifacts[filename] = path.read_text(encoding="utf-8")
        elif filename not in OPTIONAL_ARTIFACTS:
            warnings.append(f"missing_artifact:{filename}")
    return artifacts


def _detect_concepts(lower_text: str) -> list[str]:
    found: list[str] = []
    for key, spec in CONCEPT_PATTERNS.items():
        if any(keyword in lower_text for keyword in spec["keywords"]):
            found.append(key)
    return found


def _extract_lessons(lower_text: str, concepts: list[str]) -> list[str]:
    lessons: list[str] = []
    if "rate_limiting" in concepts and (
        "usability" in lower_text or "legitimate" in lower_text or "recovery" in lower_text
    ):
        lessons.append("Rate limiting requires balancing usability and abuse prevention.")
    if "account_recovery" in concepts and ("feedback" in lower_text or "generic" in lower_text):
        lessons.append("Account recovery flows benefit through clear, non-revealing user feedback.")
    if "testing" in lower_text and ("time" in lower_text or "window" in lower_text):
        lessons.append("Time-based behavior should be covered with deterministic tests.")
    if "self_healing_status" in lower_text and "retry_patch_generated" in lower_text:
        lessons.append("Self-healing retry proposals should remain review-only and approval-gated.")
    if "final_decision" in lower_text or "approved" in lower_text:
        lessons.append("Final approval is most reusable when upstream artifacts stay internally consistent.")
    return lessons or ["No reusable lessons identified beyond the available artifact chain."]


def _product_insights(lower_text: str, concepts: list[str]) -> list[str]:
    insights: list[str] = []
    if "account_recovery" in concepts:
        insights.append("Recovery flows require clear user messaging.")
    if "rate_limiting" in concepts:
        insights.append("User-facing limits should preserve legitimate completion paths.")
    return insights or ["No reusable product insights identified in available artifacts."]


def _architecture_insights(lower_text: str, concepts: list[str]) -> list[str]:
    insights: list[str] = []
    if "rate_limiting" in concepts and ("policy" in lower_text or "configuration" in lower_text):
        insights.append("Centralized policy management improves consistency for limits.")
    if "authentication" in concepts:
        insights.append("Authentication-sensitive flows should keep controls scoped and explicit.")
    return insights or ["No reusable architecture insights identified in available artifacts."]


def _testing_insights(lower_text: str, concepts: list[str]) -> list[str]:
    insights: list[str] = []
    if "rate_limiting" in concepts:
        insights.append("Limit behavior needs allowed and blocked path coverage.")
    if "window" in lower_text or "time" in lower_text:
        insights.append("Time-window behavior needs deterministic test setup.")
    return insights or ["No reusable testing insights identified in available artifacts."]


def _security_insights(lower_text: str, concepts: list[str]) -> list[str]:
    insights: list[str] = []
    if "abuse_prevention" in concepts:
        insights.append("Abuse prevention controls should fail safely under excessive use.")
    if "generic" in lower_text and ("feedback" in lower_text or "account" in lower_text):
        insights.append("User enumeration risks should be minimized with generic feedback.")
    return insights or ["No reusable security insights identified in available artifacts."]


def _future_reuse_score(concepts: list[str], lessons: list[str], security_insights: list[str]) -> str:
    meaningful_lessons = [item for item in lessons if not item.startswith("No reusable")]
    meaningful_security = [item for item in security_insights if not item.startswith("No reusable")]
    if len(concepts) >= 3 or ("rate_limiting" in concepts and "abuse_prevention" in concepts):
        return "High"
    if concepts or meaningful_lessons or meaningful_security:
        return "Medium"
    return "Low"


def _persist_knowledge(
    *,
    run_dir: Path,
    summary: dict[str, Any],
    concepts: list[str],
    reusable_patterns: list[str],
    lessons: list[str],
    security_insights: list[str],
    future_reuse_score: str,
) -> None:
    root = _knowledge_root(run_dir)
    runs_dir = root / "runs"
    patterns_dir = root / "patterns"
    lessons_dir = root / "lessons"
    for directory in (root, runs_dir, patterns_dir, lessons_dir):
        directory.mkdir(parents=True, exist_ok=True)

    run_id = run_dir.name
    task = str(summary.get("task") or _read_optional(run_dir / "00_user_request.md") or "Unknown").strip()
    final_decision = str(summary.get("final_decision") or summary.get("final_status") or "Unknown")
    run_payload = {
        "run_id": run_id,
        "task": task,
        "final_decision": final_decision,
        "reusable_patterns": reusable_patterns,
        "lessons_learned": lessons,
        "future_reuse_score": future_reuse_score,
    }
    (runs_dir / f"{run_id}.json").write_text(
        json.dumps(run_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    for concept, pattern in zip(concepts, reusable_patterns, strict=False):
        _upsert_record(
            patterns_dir / f"{concept}.json",
            {
                "id": concept,
                "pattern": pattern,
                "runs": [run_id],
                "last_seen": _now(),
            },
            run_id,
        )
    for lesson in lessons:
        if lesson.startswith("No reusable"):
            continue
        slug = _slug(lesson)
        _upsert_record(
            lessons_dir / f"{slug}.json",
            {
                "id": slug,
                "lesson": lesson,
                "runs": [run_id],
                "last_seen": _now(),
            },
            run_id,
        )

    index = {
        "total_runs": len(list(runs_dir.glob("*.json"))),
        "known_patterns": sorted(path.stem for path in patterns_dir.glob("*.json")),
        "known_lesson_count": len(list(lessons_dir.glob("*.json"))),
        "known_security_insights": _count_security_insights(runs_dir),
        "last_updated": _now(),
    }
    (root / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def _upsert_record(path: Path, default_payload: dict[str, Any], run_id: str) -> None:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = default_payload
    else:
        payload = default_payload
    runs = payload.get("runs")
    if not isinstance(runs, list):
        runs = []
    if run_id not in runs:
        runs.append(run_id)
    payload["runs"] = runs
    payload["last_seen"] = _now()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _knowledge_root(run_dir: Path) -> Path:
    if run_dir.parent.name == "runs" and run_dir.parent.parent.name == "outputs":
        return run_dir.parent.parent.parent / "knowledge"
    return run_dir.parent / "knowledge"


def _count_security_insights(runs_dir: Path) -> int:
    count = 0
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        text = "\n".join(payload.get("reusable_patterns", []) + payload.get("lessons_learned", []))
        if any(word in text.lower() for word in ("abuse", "security", "enumeration", "feedback")):
            count += 1
    return count


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


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


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if len(cleaned) > 64:
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned[:55].rstrip('_')}_{digest}"
    return cleaned or "lesson"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
