"""Documentation lookup skill runtime.

This MVP performs constrained HTTP lookups for documentation pages only after
the skill sandbox grants the `network` permission. It never executes code,
spawns shells, installs dependencies, or writes outside its skill workspace.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from agentic_network.skills.sandbox import validate_workspace_path


DEFAULT_TIMEOUT_SECONDS = 8
USER_AGENT = "ANN-DocumentationSkill/10.3 local-first"


@dataclass(frozen=True)
class DocumentationLookupResult:
    """Documentation lookup payload returned by the builtin skill."""

    status: str
    query: str
    sources: list[dict[str, str]]
    summary: str
    citations: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "sources": self.sources,
            "summary": self.summary,
            "citations": self.citations,
            "errors": self.errors,
        }


def documentation_lookup(payload: dict[str, Any], workspace: str | Path, audit_path: str | Path) -> DocumentationLookupResult:
    """Run a constrained online documentation lookup and persist artifacts."""

    query = _clean_query(payload.get("query"))
    allowed_domains = _clean_domains(payload.get("allowed_domains"))
    max_results = _max_results(payload.get("max_results"))
    candidate_urls = _candidate_urls(query, allowed_domains, payload.get("urls"), max_results)
    sources: list[dict[str, str]] = []
    errors: list[str] = []
    for url in candidate_urls:
        domain = urlparse(url).hostname or ""
        if allowed_domains and not _domain_allowed(domain, allowed_domains):
            errors.append(f"blocked_domain:{domain}")
            continue
        try:
            fetched = fetch_url(url)
        except (OSError, URLError, ValueError) as exc:
            errors.append(f"fetch_failed:{url}:{exc}")
            continue
        sources.append(
            {
                "url": url,
                "domain": domain,
                "title": _extract_title(fetched) or domain,
                "excerpt": _excerpt(_text_from_html(fetched), query),
                "consulted_at": _now(),
            }
        )
        if len(sources) >= max_results:
            break
    summary = _summarize(query, sources, errors)
    result = DocumentationLookupResult(
        status="SUCCESS" if sources else "FAILED",
        query=query,
        sources=sources,
        summary=summary,
        citations=[item["url"] for item in sources],
        errors=errors,
    )
    write_lookup_artifacts(result, payload, workspace, audit_path)
    return result


def fetch_url(url: str) -> str:
    """Fetch one URL using stdlib HTTP only."""

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only https documentation URLs are allowed.")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:  # noqa: S310 - URL allowlist is checked by caller.
        content_type = response.headers.get("content-type", "")
        if "text" not in content_type and "html" not in content_type and "json" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")
        raw = response.read(250_000)
    return raw.decode("utf-8", errors="replace")


def write_lookup_artifacts(
    result: DocumentationLookupResult,
    request_payload: dict[str, Any],
    workspace: str | Path,
    audit_path: str | Path,
) -> None:
    """Persist documentation lookup artifacts inside the skill audit path."""

    workspace_path = Path(workspace).resolve()
    audit_dir = Path(audit_path).resolve()
    validate_workspace_path(workspace_path / "lookup_cache.json", workspace_path)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "lookup_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    (audit_dir / "lookup_result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    (audit_dir / "sources.json").write_text(json.dumps(result.sources, indent=2), encoding="utf-8")
    (audit_dir / "result_summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    with (audit_dir / "audit.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": _now(), "documentation_lookup": result.to_dict()}, sort_keys=True) + "\n")


def _candidate_urls(query: str, allowed_domains: list[str], urls: object, max_results: int) -> list[str]:
    if isinstance(urls, list):
        return [str(url).strip() for url in urls if str(url).strip()][:max_results]
    domains = allowed_domains or ["docs.python.org"]
    encoded = quote_plus(query)
    candidates: list[str] = []
    for domain in domains:
        candidates.extend(
            [
                f"https://{domain}/search.html?q={encoded}",
                f"https://{domain}/search/?q={encoded}",
                f"https://{domain}/?q={encoded}",
            ]
        )
    return candidates[: max(max_results * 3, max_results)]


def _clean_query(value: object) -> str:
    query = str(value or "").strip()
    if not query:
        raise ValueError("Documentation lookup requires a non-empty query.")
    return query[:300]


def _clean_domains(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("allowed_domains must be a list.")
    domains: list[str] = []
    for item in value:
        domain = str(item).strip().lower()
        if not domain or "/" in domain or "\\" in domain or ":" in domain:
            raise ValueError(f"Invalid allowed domain: {item}")
        domains.append(domain)
    return domains


def _max_results(value: object) -> int:
    try:
        parsed = int(value or 5)
    except (TypeError, ValueError):
        parsed = 5
    return min(max(parsed, 1), 10)


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    normalized = domain.lower()
    return any(normalized == allowed or normalized.endswith(f".{allowed}") for allowed in allowed_domains)


def _extract_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    return _squash(_text_from_html(match.group(1))) if match else ""


def _text_from_html(text: str) -> str:
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return html.unescape(_squash(stripped))


def _excerpt(text: str, query: str) -> str:
    clean = _squash(text)
    lowered = clean.lower()
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_+-]{4,}", query)]
    index = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(index - 160, 0)
    return clean[start : start + 600]


def _summarize(query: str, sources: list[dict[str, str]], errors: list[str]) -> str:
    if not sources:
        return f"No documentation sources were retrieved for '{query}'. Errors: {len(errors)}."
    source_lines = [f"{item['title']} ({item['domain']}): {item['excerpt']}" for item in sources]
    return _squash(f"Documentation lookup for '{query}' consulted {len(sources)} source(s). " + " ".join(source_lines))[:2000]


def _summary_markdown(result: DocumentationLookupResult) -> str:
    return "\n".join(
        [
            "# Documentation Lookup Result",
            "",
            f"Status: {result.status}",
            f"Query: {result.query}",
            "",
            "## Summary",
            result.summary,
            "",
            "## Sources",
            *[f"- [{item['title']}]({item['url']})" for item in result.sources],
            "",
            "## Errors",
            *[f"- {error}" for error in result.errors],
            "",
        ]
    )


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
