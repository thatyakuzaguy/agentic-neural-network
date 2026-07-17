from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    NORMALIZED_CANDIDATES,
    RAW_SOURCES_DIR,
    CandidateRow,
    add_common_args,
    clean_text,
    is_license_clear,
    read_json,
    resolve_public_path,
    response_from_parts,
    truncate_text,
    write_jsonl,
)

SPAM_TERMS = (
    "payment link",
    "wallet address",
    "crypto wallet",
    "bitcoin",
    "ethereum",
    "pricing",
    "discount",
    "advertising",
    "advertisement",
    "sponsored",
    "buy now",
    "limited offer",
    "telegram",
    "whatsapp",
    "casino",
    "loan",
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "allow",
    "also",
    "been",
    "being",
    "cannot",
    "could",
    "does",
    "from",
    "have",
    "into",
    "issue",
    "make",
    "need",
    "only",
    "problem",
    "should",
    "that",
    "their",
    "there",
    "this",
    "through",
    "using",
    "when",
    "where",
    "with",
    "would",
}

SECTION_ALIASES = {
    "problem": "problem",
    "problem statement": "problem",
    "description": "problem",
    "current behavior": "problem",
    "bug": "problem",
    "what happened": "problem",
    "expected behavior": "solution",
    "proposed solution": "solution",
    "solution": "solution",
    "proposal": "solution",
    "implementation": "implementation",
    "implementation steps": "implementation",
    "steps": "implementation",
    "tasks": "implementation",
    "testing": "testing",
    "testing done": "testing",
    "tests": "testing",
    "test plan": "testing",
    "type of change": "type_of_change",
    "labels": "type_of_change",
}


def _is_promotional_or_spam(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in SPAM_TERMS):
        return True
    return bool(re.search(r"\b(0x[a-f0-9]{20,}|bc1[a-z0-9]{20,})\b", lowered))


def _heading_key(line: str) -> str | None:
    stripped = line.strip()
    heading = re.match(r"^#{1,6}\s+(.+?)\s*$", stripped)
    if heading:
        value = heading.group(1)
    else:
        bold = re.match(r"^\*\*(.+?)\*\*:?\s*$", stripped)
        value = bold.group(1) if bold else stripped.rstrip(":")
    normalized = re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()
    return SECTION_ALIASES.get(normalized)


def _parse_issue_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {
        "problem": [],
        "solution": [],
        "implementation": [],
        "testing": [],
        "type_of_change": [],
    }
    current = "problem"
    for line in body.splitlines():
        key = _heading_key(line)
        if key:
            current = key
            continue
        if line.strip():
            sections[current].append(line.strip())
    return {key: clean_text("\n".join(value)) for key, value in sections.items()}


def _sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+-\s+|\n+\*\s+|\n+\d+[.)]\s+", clean_text(text))
    return [chunk.strip(" -\t") for chunk in chunks if len(chunk.strip(" -\t")) >= 12]


def _bullet_items(text: str) -> list[str]:
    items = []
    for line in clean_text(text).splitlines():
        item = re.sub(r"^\s*(?:[-*]|\d+[.)]|\[[ xX]\])\s*", "", line).strip()
        if item and len(item) >= 8:
            items.append(item)
    return items or _sentences(text)


def _feature_terms(title: str, body: str, labels: list[str]) -> list[str]:
    domain_terms = [
        "cache",
        "caching",
        "cached",
        "ttl",
        "invalidation",
        "cache key",
        "fastapi",
        "api",
        "endpoint",
        "auth",
        "rbac",
        "audit",
        "security",
        "pipeline",
        "cli",
        "database",
        "migration",
        "tenant",
        "webhook",
        "pagination",
        "validation",
    ]
    combined = f"{title}\n{body}\n{' '.join(labels)}".lower()
    found = [term for term in domain_terms if term in combined]
    words = [
        word
        for word in re.findall(r"[a-z][a-z0-9_-]{3,}", combined)
        if word not in STOPWORDS and not word.startswith("http")
    ]
    for word in words:
        if word not in found:
            found.append(word)
        if len(found) >= 8:
            break
    return found[:8] or ["requested behavior"]


def _first_relevant(items: list[str], terms: list[str], fallback: str) -> str:
    lowered_terms = [term.lower() for term in terms]
    for item in items:
        if any(term in item.lower() for term in lowered_terms):
            return item
    return items[0] if items else fallback


def _concrete_requirements(title: str, sections: dict[str, str], terms: list[str]) -> list[str]:
    requirements: list[str] = []
    problem = _first_relevant(_sentences(sections["problem"]), terms, title)
    if problem:
        requirements.append(f"Fix or support the reported {terms[0]} behavior: {problem}")
    for item in _bullet_items(sections["solution"])[:2]:
        requirements.append(f"Implement the proposed {terms[0]} behavior: {item}")
    for item in _bullet_items(sections["implementation"])[:3]:
        requirements.append(f"Complete the requested implementation step for {terms[0]}: {item}")
    if len(requirements) == 1:
        requirements.append(f"Use the issue title as the task boundary: {title}")
    return list(dict.fromkeys(requirements))[:5]


def _concrete_ambiguities(
    sections: dict[str, str], terms: list[str], labels: list[str]
) -> list[str]:
    ambiguities: list[str] = []
    if "cache" in " ".join(terms):
        ambiguities.append("What cache invalidation trigger, TTL, or cache-key dimensions apply?")
    if "api" in terms or "endpoint" in terms:
        ambiguities.append("Which API status codes and response schema changes are expected?")
    if "security" in terms or "auth" in terms or "rbac" in terms:
        ambiguities.append("Which actors, roles, or permissions may exercise this behavior?")
    if not sections["testing"]:
        ambiguities.append(f"What regression test must prove the {terms[0]} behavior?")
    if not labels:
        ambiguities.append("What type-of-change label should reviewers apply to this issue?")
    return ambiguities[:4] or [f"What exact edge cases should be covered for {terms[0]}?"]


def _concrete_acceptance(sections: dict[str, str], terms: list[str]) -> list[str]:
    feature = terms[0]
    context = _first_relevant(_sentences(f"{sections['solution']}\n{sections['problem']}"), terms, feature)
    criteria = [
        f"Given the reported {feature} scenario for {context}, "
        "when the described action runs, then the issue no longer reproduces.",
    ]
    if "cache" in " ".join(terms):
        criteria.append(
            "Repeated requests use the intended cache entry, and changed inputs "
            "or invalidation events produce fresh results."
        )
    if "api" in terms or "endpoint" in terms:
        criteria.append(f"API responses for the {feature} path return the expected status and payload.")
    for item in _bullet_items(sections["testing"])[:3]:
        criteria.append(f"The documented {feature} test evidence passes: {item}")
    for item in _bullet_items(sections["implementation"])[:2]:
        criteria.append(f"The {feature} implementation includes: {item}")
    return list(dict.fromkeys(criteria))[:5]


def _concrete_risks(terms: list[str], labels: list[str]) -> list[str]:
    joined = " ".join(terms + labels).lower()
    risks = []
    if "cache" in joined:
        risks.append("Incorrect cache keys or invalidation can serve stale or cross-tenant data.")
    if any(term in joined for term in ("security", "auth", "rbac", "permission")):
        risks.append("Authorization changes can expose data or block legitimate users.")
    if any(term in joined for term in ("api", "endpoint")):
        risks.append("API behavior changes can break clients if responses change unexpectedly.")
    if any(term in joined for term in ("database", "migration")):
        risks.append("Schema or data migration changes can be hard to roll back.")
    risks.append("The issue is public user-generated content and requires manual review.")
    return list(dict.fromkeys(risks))[:5]


def _source_payloads(raw_dir: Path) -> list[dict[str, Any]]:
    payloads = []
    for path in sorted(raw_dir.glob("*.json")):
        if path.name == "download_report.json":
            continue
        payload = read_json(path)
        if "source" in payload and "items" in payload:
            payloads.append(payload)
    return payloads


def _labels_from_github_issue(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels") or []
    names = []
    for label in labels:
        if isinstance(label, dict) and label.get("name"):
            names.append(str(label["name"]))
        elif isinstance(label, str):
            names.append(label)
    return names


def _github_issue_candidate(source: dict[str, Any], issue: dict[str, Any]) -> CandidateRow | None:
    title = clean_text(issue.get("title"))
    body = truncate_text(issue.get("body", ""), max_chars=5000)
    if not title or not body:
        return None
    labels = _labels_from_github_issue(issue)
    raw_input = f"{title}\n\n{body}"
    risk_flags = list(dict.fromkeys(source.get("risk_flags", []) + ["derived_summary_requires_review"]))
    if _is_promotional_or_spam(raw_input):
        risk_flags.append("promotional_or_spam")
    sections = _parse_issue_sections(body)
    terms = _feature_terms(title, body, labels)
    assumptions = [f"Scope stays limited to the reported {terms[0]} behavior in this issue."]
    if sections["type_of_change"]:
        assumptions.append(f"Reviewer-provided change type is source metadata: {sections['type_of_change']}")
    response = response_from_parts(
        requirements=_concrete_requirements(title, sections, terms),
        ambiguities=_concrete_ambiguities(sections, terms, labels),
        assumptions=assumptions,
        acceptance_criteria=_concrete_acceptance(sections, terms),
        risks=_concrete_risks(terms, labels),
        confidence="Medium; grounded in issue text and pending manual review",
    )
    return CandidateRow(
        source=source["source"],
        license=source["license"],
        url=str(issue.get("html_url") or source["url"]),
        raw_input=raw_input,
        raw_output=json.dumps(
            {
                "labels": labels,
                "state": issue.get("state"),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
            },
            sort_keys=True,
        ),
        candidate_task=f"Analyze this public software issue and produce Product Agent requirements: {title}",
        candidate_response=response,
        quality_score=0,
        risk_flags=list(dict.fromkeys(risk_flags)),
    )


def _swebench_candidate(source: dict[str, Any], row: dict[str, Any]) -> CandidateRow | None:
    statement = truncate_text(row.get("problem_statement") or row.get("text") or "", max_chars=6000)
    if not statement:
        return None
    issue = {"title": row.get("instance_id", "SWE-bench issue"), "body": statement, "labels": []}
    candidate = _github_issue_candidate(source, issue)
    if candidate:
        candidate.url = f"{source['url']}#{clean_text(row.get('instance_id', 'unknown-instance'))}"
    return candidate


def _ears_candidate(source: dict[str, Any], item: dict[str, Any]) -> CandidateRow | None:
    task = clean_text(item.get("task"))
    if not task:
        return None
    requirements = [clean_text(value) for value in item.get("requirements", []) if clean_text(value)]
    acceptance = [clean_text(value) for value in item.get("acceptance", []) if clean_text(value)]
    ambiguities = [clean_text(value) for value in item.get("ambiguities", []) if clean_text(value)]
    response = response_from_parts(
        requirements=requirements,
        ambiguities=ambiguities,
        assumptions=[
            "The example is original synthetic material written for Product Agent curation.",
            "The implementation stack should be confirmed before coding.",
        ],
        acceptance_criteria=acceptance,
        risks=["Synthetic examples can be too tidy compared with real stakeholder input."],
        confidence="High for structure; medium for realism",
    )
    return CandidateRow(
        source=source["source"],
        license=source["license"],
        url=source["url"],
        raw_input=task,
        raw_output=json.dumps(item, sort_keys=True),
        candidate_task=task,
        candidate_response=response,
        quality_score=0,
        risk_flags=list(source.get("risk_flags", [])),
    )


def normalize_sources(data_root: Path) -> list[CandidateRow]:
    raw_dir = resolve_public_path(RAW_SOURCES_DIR, data_root)
    normalized_path = resolve_public_path(NORMALIZED_CANDIDATES, data_root)
    if not raw_dir.exists():
        print(f"No raw source directory found at {raw_dir}; leaving normalized candidates unchanged.")
        return []

    candidates: list[CandidateRow] = []
    for payload in _source_payloads(raw_dir):
        source = payload["source"]
        if not is_license_clear(source.get("license", ""), source.get("license_status", "")):
            continue
        for item in payload.get("items", []):
            candidate = None
            if source.get("download_strategy") == "github_issues":
                candidate = _github_issue_candidate(source, item)
            elif source.get("download_strategy") == "huggingface_sample":
                candidate = _swebench_candidate(source, item)
            elif source.get("download_strategy") == "generated_examples":
                candidate = _ears_candidate(source, item)
            if candidate is not None:
                candidates.append(candidate)

    if candidates:
        write_jsonl(normalized_path, candidates)
    else:
        print("No normalized candidates produced; leaving normalized candidates unchanged.")
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize raw source samples into candidate rows.")
    add_common_args(parser)
    args = parser.parse_args()
    candidates = normalize_sources(args.data_root)
    print(f"Normalized {len(candidates)} candidates.")


if __name__ == "__main__":
    main()
