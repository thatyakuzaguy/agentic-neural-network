"""Read-only Skill Evidence Bundle runtime for ANN agents."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_ROOTS = [REPO_ROOT / "outputs" / "skills" / "documentation", REPO_ROOT / "outputs" / "skills" / "github"]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "outputs" / "skill_evidence"
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}
EVIDENCE_TYPES = {"documentation", "github_metadata", "github_file", "github_pattern", "package_info", "unknown"}


@dataclass(frozen=True)
class SkillEvidenceItem:
    """One compact read-only skill evidence item."""

    source_skill: str
    source_action: str
    title: str
    summary: str
    evidence_type: str
    source_path: str
    citations: list[str]
    relevance_score: float
    safe_to_use: bool
    risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillEvidenceResult:
    """Skill Evidence Bundle result."""

    status: str
    evidence_items: list[dict[str, Any]]
    sources_used: list[str]
    summary: str
    recommendations: list[str]
    risks: list[str]
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_skill_evidence_bundle(
    skill_output_roots: list[str | Path] | None = None,
    run_dir: str | Path | None = None,
    max_items: int = 20,
) -> SkillEvidenceResult:
    """Build a compact, advisory evidence bundle from existing skill artifacts."""

    errors: list[str] = []
    warnings: list[str] = []
    roots = _resolve_skill_roots(skill_output_roots, errors)
    output_dir = _resolve_output_dir(run_dir, errors)
    if errors:
        return SkillEvidenceResult(
            status="BLOCKED",
            evidence_items=[],
            sources_used=[],
            summary="Skill evidence bundle blocked by validation errors.",
            recommendations=[],
            risks=["Evidence was not read because one or more paths failed validation."],
            artifacts=[],
            validation_errors=_dedupe(errors),
            validation_warnings=_dedupe(warnings),
        )
    items: list[SkillEvidenceItem] = []
    sources_used: list[str] = []
    for root in roots:
        if not root.is_dir():
            warnings.append(f"missing_skill_output_root:{root}")
            continue
        collected = _collect_from_root(root)
        items.extend(collected)
        if collected:
            sources_used.append(str(root))
    compact_items = sorted(items, key=lambda item: item.relevance_score, reverse=True)[: max(0, max_items)]
    status = "VALID" if compact_items else "EMPTY"
    recommendations = _recommendations(compact_items)
    risks = _risks(compact_items)
    summary = _summary(compact_items)
    result_without_artifacts = SkillEvidenceResult(
        status=status,
        evidence_items=[item.to_dict() for item in compact_items],
        sources_used=sources_used,
        summary=summary,
        recommendations=recommendations,
        risks=risks,
        artifacts=[],
        validation_errors=[],
        validation_warnings=_dedupe(warnings),
    )
    artifacts = _write_artifacts(output_dir, result_without_artifacts)
    return SkillEvidenceResult(**{**result_without_artifacts.to_dict(), "artifacts": artifacts})


def _resolve_skill_roots(roots: list[str | Path] | None, errors: list[str]) -> list[Path]:
    selected = roots or DEFAULT_SKILL_ROOTS
    resolved: list[Path] = []
    for root in selected:
        raw = str(root)
        if _has_traversal(raw):
            errors.append("skill_output_root_path_traversal_blocked")
            continue
        path = Path(root).resolve()
        if _has_protected_part(path):
            errors.append(f"skill_output_root_protected_path_blocked:{path}")
            continue
        resolved.append(path)
    return resolved


def _resolve_output_dir(run_dir: str | Path | None, errors: list[str]) -> Path:
    if run_dir is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return DEFAULT_EVIDENCE_ROOT / timestamp
    raw = str(run_dir)
    if _has_traversal(raw):
        errors.append("run_dir_path_traversal_blocked")
        return DEFAULT_EVIDENCE_ROOT / "blocked"
    resolved = Path(run_dir).resolve()
    if _has_protected_part(resolved):
        errors.append(f"run_dir_protected_path_blocked:{resolved}")
    return resolved


def _collect_from_root(root: Path) -> list[SkillEvidenceItem]:
    name = root.name.lower()
    if name == "documentation":
        return _collect_documentation(root)
    if name == "github":
        return _collect_github(root)
    return []


def _collect_documentation(root: Path) -> list[SkillEvidenceItem]:
    items: list[SkillEvidenceItem] = []
    lookup = _read_json(root / "lookup_result.json")
    if lookup:
        sources = _read_json_list(root / "sources.json")
        citations = [str(item.get("url")) for item in sources if isinstance(item, dict) and item.get("url")]
        items.append(
            SkillEvidenceItem(
                source_skill="documentation",
                source_action="lookup",
                title=f"Documentation lookup: {lookup.get('query', 'unknown query')}",
                summary=_safe_summary(str(lookup.get("summary") or "")),
                evidence_type="documentation",
                source_path=str(root / "lookup_result.json"),
                citations=citations,
                relevance_score=0.82,
                safe_to_use=True,
                risks=["Documentation can be stale; verify against current project requirements."],
            )
        )
    return items


def _collect_github(root: Path) -> list[SkillEvidenceItem]:
    items: list[SkillEvidenceItem] = []
    repo_lookup = _read_json(root / "github_lookup_result.json")
    if repo_lookup:
        items.append(
            SkillEvidenceItem(
                source_skill="github",
                source_action="lookup_repo",
                title=f"GitHub repository metadata: {repo_lookup.get('repo', 'unknown repo')}",
                summary=_safe_summary(str(repo_lookup.get("summary") or repo_lookup.get("description") or "")),
                evidence_type="github_metadata",
                source_path=str(root / "github_lookup_result.json"),
                citations=[str(repo_lookup.get("repo", ""))],
                relevance_score=0.74,
                safe_to_use=True,
                risks=["Repository metadata is advisory and must not be copied as implementation."],
            )
        )
    file_lookup = _read_json(root / "github_file_lookup_result.json")
    if file_lookup:
        redacted = bool(file_lookup.get("redacted"))
        items.append(
            SkillEvidenceItem(
                source_skill="github",
                source_action="lookup_file",
                title=f"GitHub file evidence: {file_lookup.get('path', 'unknown path')}",
                summary=_safe_summary(str(file_lookup.get("content_preview") or "")),
                evidence_type="github_file",
                source_path=str(root / "github_file_lookup_result.json"),
                citations=[str(file_lookup.get("path", ""))],
                relevance_score=0.69 if not redacted else 0.48,
                safe_to_use=not redacted,
                risks=_dedupe(
                    [
                        "Do not copy external source text directly into generated projects.",
                        "Secret-like content was redacted." if redacted else "",
                    ]
                ),
            )
        )
    patterns = _read_json(root / "github_patterns.json")
    if patterns:
        pattern_count = len(patterns.get("patterns", [])) if isinstance(patterns.get("patterns"), list) else 0
        items.append(
            SkillEvidenceItem(
                source_skill="github",
                source_action="extract_patterns",
                title=f"GitHub pattern extraction: {patterns.get('repo', 'unknown repo')}",
                summary=_safe_summary(str(patterns.get("summary") or f"{pattern_count} patterns detected.")),
                evidence_type="github_pattern",
                source_path=str(root / "github_patterns.json"),
                citations=[str(path) for path in patterns.get("evidence_files", [])] if isinstance(patterns.get("evidence_files"), list) else [],
                relevance_score=0.88,
                safe_to_use=True,
                risks=["Patterns are advisory only; do not copy external code directly."],
            )
        )
    return items


def _write_artifacts(output_dir: Path, result: SkillEvidenceResult) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_md = output_dir / "70_skill_evidence_bundle.md"
    bundle_json = output_dir / "70_skill_evidence_bundle.json"
    summary_md = output_dir / "71_skill_evidence_summary.md"
    bundle_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    bundle_md.write_text(_bundle_markdown(result), encoding="utf-8")
    summary_md.write_text(_summary_markdown(result), encoding="utf-8")
    return [str(bundle_md), str(bundle_json), str(summary_md)]


def _bundle_markdown(result: SkillEvidenceResult) -> str:
    lines = [
        "# Skill Evidence Bundle",
        "",
        f"Status: {result.status}",
        f"Items: {len(result.evidence_items)}",
        "",
        "## Summary",
        result.summary,
        "",
        "## Evidence Items",
    ]
    for item in result.evidence_items:
        lines.extend(
            [
                f"### {item['title']}",
                f"- Skill: {item['source_skill']}",
                f"- Action: {item['source_action']}",
                f"- Type: {item['evidence_type']}",
                f"- Safe to use: {item['safe_to_use']}",
                f"- Source path: {item['source_path']}",
                f"- Summary: {item['summary']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _summary_markdown(result: SkillEvidenceResult) -> str:
    return "\n".join(
        [
            "# Skill Evidence Summary",
            "",
            f"Status: {result.status}",
            result.summary,
            "",
            "## Recommendations",
            *[f"- {item}" for item in result.recommendations],
            "",
            "## Risks",
            *[f"- {item}" for item in result.risks],
            "",
            "Evidence is advisory only. It must not be used to copy external code directly into projects.",
            "",
        ]
    )


def _recommendations(items: list[SkillEvidenceItem]) -> list[str]:
    types = {item.evidence_type for item in items}
    recommendations: list[str] = []
    if "documentation" in types:
        recommendations.append("Consult documentation evidence when refining architecture and API usage.")
    if "github_pattern" in types:
        recommendations.append("Use extracted patterns as planning guidance, not as code to copy.")
    if "github_metadata" in types:
        recommendations.append("Use repository metadata to calibrate stack assumptions and project conventions.")
    if "github_file" in types:
        recommendations.append("Summarize referenced files into requirements or test ideas without injecting source code.")
    return recommendations or ["No skill evidence recommendations are available."]


def _risks(items: list[SkillEvidenceItem]) -> list[str]:
    risks = ["Skill evidence is advisory only and must not automatically modify projects."]
    for item in items:
        risks.extend(item.risks)
    return _dedupe(risks)


def _summary(items: list[SkillEvidenceItem]) -> str:
    if not items:
        return "No reusable skill evidence artifacts were found."
    counts: dict[str, int] = {}
    for item in items:
        counts[item.evidence_type] = counts.get(item.evidence_type, 0) + 1
    count_text = ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
    return f"Collected {len(items)} read-only skill evidence item(s): {count_text}."


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or _has_protected_part(path):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or _has_protected_part(path):
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _safe_summary(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:1000]


def _has_traversal(raw: str) -> bool:
    return any(part == ".." for part in raw.replace("\\", "/").split("/"))


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
