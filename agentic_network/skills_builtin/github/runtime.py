"""GitHub read-only skill runtime.

This MVP reads public repository metadata through the GitHub HTTPS API after
the sandbox grants both `network` and `git_read`. It never invokes git,
spawns shells, downloads repositories, executes repository code, or installs
dependencies.
"""

from __future__ import annotations

import json
import re
import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agentic_network.skills.sandbox import validate_workspace_path
from agentic_network.skills_builtin.github.patterns import extract_patterns_from_files


DEFAULT_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 750_000
USER_AGENT = "ANN-GitHubSkill/10.4 local-first"
DEFAULT_FILE_MAX_BYTES = 120_000
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


@dataclass(frozen=True)
class GitHubLookupResult:
    """Read-only GitHub repository lookup result."""

    status: str
    repo: str
    description: str
    default_branch: str
    stars: int | None
    forks: int | None
    language: str
    license: str
    topics: list[str]
    files_sample: list[dict[str, object]]
    summary: str
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repo": self.repo,
            "description": self.description,
            "default_branch": self.default_branch,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "license": self.license,
            "topics": self.topics,
            "files_sample": self.files_sample,
            "summary": self.summary,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class GitHubFileLookupResult:
    """Read-only GitHub file lookup result."""

    status: str
    repo: str
    path: str
    ref: str
    size_bytes: int
    content_preview: str
    content_sha: str
    redacted: bool
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repo": self.repo,
            "path": self.path,
            "ref": self.ref,
            "size_bytes": self.size_bytes,
            "content_preview": self.content_preview,
            "content_sha": self.content_sha,
            "redacted": self.redacted,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class GitHubPatternExtractionResult:
    """Deterministic GitHub pattern extraction result."""

    status: str
    repo: str
    files_analyzed: list[str]
    patterns: list[dict[str, str]]
    summary: str
    recommendations: list[str]
    evidence_files: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repo": self.repo,
            "files_analyzed": self.files_analyzed,
            "patterns": self.patterns,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "evidence_files": self.evidence_files,
            "errors": self.errors,
        }


def github_lookup_repo(payload: dict[str, Any], workspace: str | Path, audit_path: str | Path) -> GitHubLookupResult:
    """Lookup public GitHub repository metadata and persist read-only artifacts."""

    repo = _clean_repo(payload.get("repo"))
    max_files = _max_files(payload.get("max_files"))
    allowed_domains = _clean_domains(payload.get("allowed_domains"))
    metadata_url = f"https://api.github.com/repos/{repo}"
    errors: list[str] = []
    if _blocked_domain(metadata_url, allowed_domains):
        errors.append(f"blocked_domain:{urlparse(metadata_url).hostname or ''}")
        result = _empty_result(repo, errors)
        write_github_artifacts(result, payload, {}, [], workspace, audit_path)
        return result
    metadata: dict[str, Any] = {}
    tree_entries: list[dict[str, object]] = []
    try:
        metadata_payload = fetch_json(metadata_url)
        if not isinstance(metadata_payload, dict):
            raise ValueError("GitHub repository metadata response must be an object.")
        metadata = metadata_payload
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"fetch_failed:{metadata_url}:{exc}")
    default_branch = str(metadata.get("default_branch") or payload.get("ref") or "main")
    tree_url = f"https://api.github.com/repos/{repo}/git/trees/{default_branch}?recursive=1"
    if metadata and _blocked_domain(tree_url, allowed_domains):
        errors.append(f"blocked_domain:{urlparse(tree_url).hostname or ''}")
    elif metadata:
        try:
            tree_payload = fetch_json(tree_url)
            if isinstance(tree_payload, dict):
                tree_entries = _file_sample(tree_payload.get("tree"), max_files)
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            contents_url = f"https://api.github.com/repos/{repo}/contents?ref={default_branch}"
            if _blocked_domain(contents_url, allowed_domains):
                errors.append(f"blocked_domain:{urlparse(contents_url).hostname or ''}")
                errors.append(f"fetch_failed:{tree_url}:{exc}")
            else:
                try:
                    contents_payload = fetch_json(contents_url)
                    tree_entries = _contents_sample(contents_payload, max_files)
                except (OSError, URLError, ValueError, json.JSONDecodeError) as contents_exc:
                    errors.append(f"fetch_failed:{tree_url}:{exc}")
                    errors.append(f"fetch_failed:{contents_url}:{contents_exc}")
    result = GitHubLookupResult(
        status="SUCCESS" if metadata else "FAILED",
        repo=repo,
        description=str(metadata.get("description") or ""),
        default_branch=default_branch,
        stars=_int_or_none(metadata.get("stargazers_count")),
        forks=_int_or_none(metadata.get("forks_count")),
        language=str(metadata.get("language") or ""),
        license=_license_name(metadata.get("license")),
        topics=[str(topic) for topic in metadata.get("topics", []) if isinstance(topic, str)],
        files_sample=tree_entries,
        summary=_summary(repo, metadata, tree_entries, errors),
        errors=errors,
    )
    write_github_artifacts(result, payload, metadata, tree_entries, workspace, audit_path)
    return result


def github_lookup_file(payload: dict[str, Any], workspace: str | Path, audit_path: str | Path) -> GitHubFileLookupResult:
    """Lookup one public GitHub text file without cloning or executing code."""

    repo = _clean_repo(payload.get("repo"))
    path = _clean_repo_path(payload.get("path"))
    ref = _clean_ref(payload.get("ref"))
    allowed_domains = _clean_domains(payload.get("allowed_domains"))
    max_bytes = _max_bytes(payload.get("max_bytes"))
    errors: list[str] = []
    if _looks_binary(path):
        result = _file_result("BLOCKED", repo, path, ref, 0, "", "", False, ["binary_file_blocked"])
        write_file_artifacts(result, payload, workspace, audit_path, "")
        return result
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    if _blocked_domain(url, allowed_domains):
        result = _file_result("BLOCKED", repo, path, ref, 0, "", "", False, [f"blocked_domain:{urlparse(url).hostname or ''}"])
        write_file_artifacts(result, payload, workspace, audit_path, "")
        return result
    content = ""
    size = 0
    try:
        payload_json = fetch_json(url)
        if not isinstance(payload_json, dict):
            raise ValueError("GitHub file response must be an object.")
        if str(payload_json.get("type") or "") != "file":
            raise ValueError("GitHub path is not a file.")
        size = _int_or_none(payload_json.get("size")) or 0
        if size > max_bytes:
            raise ValueError(f"file_too_large:{size}>{max_bytes}")
        content = _decode_github_content(payload_json)
        encoded_size = len(content.encode("utf-8"))
        if encoded_size > max_bytes:
            raise ValueError(f"file_too_large:{encoded_size}>{max_bytes}")
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    redacted_content, redacted = redact_secret_like_content(content)
    result = _file_result(
        "SUCCESS" if content and not errors else "FAILED",
        repo,
        path,
        ref,
        len(content.encode("utf-8")) if content else size,
        redacted_content[:2000],
        hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
        redacted,
        errors,
    )
    write_file_artifacts(result, payload, workspace, audit_path, redacted_content)
    return result


def github_extract_patterns(payload: dict[str, Any], workspace: str | Path, audit_path: str | Path) -> GitHubPatternExtractionResult:
    """Fetch selected text files and extract deterministic technical patterns."""

    repo = _clean_repo(payload.get("repo"))
    ref = _clean_ref(payload.get("ref"))
    allowed_domains = _clean_domains(payload.get("allowed_domains"))
    max_files = min(_max_files(payload.get("max_files")), 20)
    max_bytes = _max_bytes(payload.get("max_bytes_per_file"))
    paths = _clean_paths(payload.get("paths"))[:max_files]
    errors: list[str] = []
    fetched_files: list[dict[str, object]] = []
    evidence_files: list[str] = []
    for path in paths:
        file_payload = {
            "repo": repo,
            "path": path,
            "ref": ref,
            "allowed_domains": allowed_domains,
            "max_bytes": max_bytes,
        }
        result = github_lookup_file(file_payload, workspace, audit_path)
        if result.status == "SUCCESS":
            fetched_files.append(
                {
                    "path": path,
                    "content": result.content_preview,
                    "redacted": result.redacted,
                    "content_sha": result.content_sha,
                }
            )
            evidence_files.append(path)
        else:
            errors.extend([f"{path}:{error}" for error in result.errors])
    extracted = extract_patterns_from_files(
        fetched_files,
        pattern_types=[str(item) for item in payload.get("pattern_types", [])] if isinstance(payload.get("pattern_types"), list) else None,
    )
    result = GitHubPatternExtractionResult(
        status="SUCCESS" if fetched_files else "FAILED",
        repo=repo,
        files_analyzed=[str(item["path"]) for item in fetched_files],
        patterns=extracted["patterns"],
        summary=str(extracted["summary"]),
        recommendations=list(extracted["recommendations"]),
        evidence_files=evidence_files,
        errors=errors,
    )
    write_pattern_artifacts(result, payload, workspace, audit_path)
    return result


def fetch_json(url: str) -> object:
    """Fetch one JSON resource using stdlib HTTPS only."""

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only https GitHub URLs are allowed.")
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:  # noqa: S310 - caller checks domains.
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("GitHub response exceeded size limit.")
    return json.loads(raw.decode("utf-8", errors="replace"))


def redact_secret_like_content(content: str) -> tuple[str, bool]:
    """Redact secret-like lines before persisting previews or evidence."""

    redacted = False
    safe_lines: list[str] = []
    for line in content.splitlines():
        safe_line = line
        for pattern in SECRET_PATTERNS:
            if pattern.search(safe_line):
                safe_line = pattern.sub("[REDACTED_SECRET]", safe_line)
                redacted = True
        safe_lines.append(safe_line)
    return "\n".join(safe_lines), redacted


def write_github_artifacts(
    result: GitHubLookupResult,
    request_payload: dict[str, Any],
    metadata: dict[str, Any],
    file_tree: list[dict[str, object]],
    workspace: str | Path,
    audit_path: str | Path,
) -> None:
    """Persist GitHub lookup artifacts inside outputs/skills/github."""

    workspace_path = Path(workspace).resolve()
    audit_dir = Path(audit_path).resolve()
    validate_workspace_path(workspace_path / "github_cache.json", workspace_path)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "github_lookup_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    (audit_dir / "github_lookup_result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    (audit_dir / "github_repo_metadata.json").write_text(json.dumps(_metadata_summary(metadata), indent=2), encoding="utf-8")
    (audit_dir / "github_file_tree.json").write_text(json.dumps(file_tree, indent=2), encoding="utf-8")
    (audit_dir / "result_summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    with (audit_dir / "audit.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": _now(), "github_lookup_repo": result.to_dict()}, sort_keys=True) + "\n")


def write_file_artifacts(
    result: GitHubFileLookupResult,
    request_payload: dict[str, Any],
    workspace: str | Path,
    audit_path: str | Path,
    content: str,
) -> None:
    """Persist safe file lookup artifacts."""

    workspace_path = Path(workspace).resolve()
    audit_dir = Path(audit_path).resolve()
    validate_workspace_path(workspace_path / "github_file_cache.txt", workspace_path)
    audit_dir.mkdir(parents=True, exist_ok=True)
    safe_content = content if not result.redacted else result.content_preview
    (audit_dir / "github_file_lookup_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    (audit_dir / "github_file_lookup_result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    (audit_dir / "github_file_content_redacted.txt").write_text(safe_content, encoding="utf-8")
    (audit_dir / "result_summary.md").write_text(_file_summary_markdown(result), encoding="utf-8")
    with (audit_dir / "audit.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": _now(), "github_lookup_file": result.to_dict()}, sort_keys=True) + "\n")


def write_pattern_artifacts(
    result: GitHubPatternExtractionResult,
    request_payload: dict[str, Any],
    workspace: str | Path,
    audit_path: str | Path,
) -> None:
    """Persist deterministic pattern extraction artifacts."""

    workspace_path = Path(workspace).resolve()
    audit_dir = Path(audit_path).resolve()
    validate_workspace_path(workspace_path / "github_patterns_cache.json", workspace_path)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "github_pattern_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    (audit_dir / "github_patterns.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    (audit_dir / "github_pattern_summary.md").write_text(_pattern_summary_markdown(result), encoding="utf-8")
    (audit_dir / "result_summary.md").write_text(_pattern_summary_markdown(result), encoding="utf-8")
    with (audit_dir / "audit.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": _now(), "github_extract_patterns": result.to_dict()}, sort_keys=True) + "\n")


def _empty_result(repo: str, errors: list[str]) -> GitHubLookupResult:
    return GitHubLookupResult(
        status="FAILED",
        repo=repo,
        description="",
        default_branch="",
        stars=None,
        forks=None,
        language="",
        license="",
        topics=[],
        files_sample=[],
        summary=f"GitHub lookup for {repo} did not run because the request was blocked.",
        errors=errors,
    )


def _file_result(
    status: str,
    repo: str,
    path: str,
    ref: str,
    size_bytes: int,
    content_preview: str,
    content_sha: str,
    redacted: bool,
    errors: list[str],
) -> GitHubFileLookupResult:
    return GitHubFileLookupResult(
        status=status,
        repo=repo,
        path=path,
        ref=ref,
        size_bytes=size_bytes,
        content_preview=content_preview,
        content_sha=content_sha,
        redacted=redacted,
        errors=errors,
    )


def _clean_repo(value: object) -> str:
    repo = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GitHub lookup requires repo in owner/name format.")
    return repo


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


def _clean_repo_path(value: object) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if not path or path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("GitHub file path traversal is not allowed.")
    if _looks_binary(path):
        return path
    if len(path) > 500:
        raise ValueError("GitHub file path is too long.")
    return path


def _clean_paths(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("extract_patterns requires a non-empty paths list.")
    return [_clean_repo_path(item) for item in value]


def _clean_ref(value: object) -> str:
    ref = str(value or "main").strip()
    if not ref or ref.startswith("/") or "\\" in ref or ".." in ref:
        raise ValueError("Invalid GitHub ref.")
    return ref[:120]


def _max_files(value: object) -> int:
    try:
        parsed = int(value or 20)
    except (TypeError, ValueError):
        parsed = 20
    return min(max(parsed, 1), 100)


def _max_bytes(value: object) -> int:
    try:
        parsed = int(value or DEFAULT_FILE_MAX_BYTES)
    except (TypeError, ValueError):
        parsed = DEFAULT_FILE_MAX_BYTES
    return min(max(parsed, 1_000), DEFAULT_FILE_MAX_BYTES)


def _blocked_domain(url: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return False
    domain = (urlparse(url).hostname or "").lower()
    return domain not in allowed_domains


def _file_sample(value: object, max_files: int) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    files: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if _looks_binary(path):
            continue
        files.append(
            {
                "path": path,
                "mode": str(item.get("mode") or ""),
                "size": _int_or_none(item.get("size")),
            }
        )
        if len(files) >= max_files:
            break
    return files


def _contents_sample(value: object, max_files: int) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    files: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        path = str(item.get("path") or item.get("name") or "")
        if _looks_binary(path):
            continue
        files.append(
            {
                "path": path,
                "mode": "",
                "size": _int_or_none(item.get("size")),
            }
        )
        if len(files) >= max_files:
            break
    return files


def _looks_binary(path: str) -> bool:
    return Path(path).suffix.lower() in {
        ".7z",
        ".bin",
        ".bmp",
        ".class",
        ".dll",
        ".exe",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".webp",
        ".zip",
    }


def _decode_github_content(payload: dict[str, Any]) -> str:
    encoding = str(payload.get("encoding") or "").lower()
    content = str(payload.get("content") or "")
    if encoding != "base64":
        raise ValueError(f"Unsupported GitHub file encoding: {encoding}")
    compact = re.sub(r"\s+", "", content)
    raw = base64.b64decode(compact, validate=True)
    if b"\x00" in raw[:4096]:
        raise ValueError("binary_file_blocked")
    return raw.decode("utf-8")


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": metadata.get("full_name"),
        "description": metadata.get("description"),
        "default_branch": metadata.get("default_branch"),
        "stargazers_count": metadata.get("stargazers_count"),
        "forks_count": metadata.get("forks_count"),
        "language": metadata.get("language"),
        "license": _license_name(metadata.get("license")),
        "topics": metadata.get("topics", []),
        "html_url": metadata.get("html_url"),
    }


def _summary(repo: str, metadata: dict[str, Any], files: list[dict[str, object]], errors: list[str]) -> str:
    if not metadata:
        return f"No GitHub metadata was retrieved for {repo}. Errors: {len(errors)}."
    return (
        f"{repo} is a public GitHub repository. "
        f"Description: {metadata.get('description') or 'No description'}. "
        f"Default branch: {metadata.get('default_branch') or 'unknown'}. "
        f"Language: {metadata.get('language') or 'unknown'}. "
        f"Files sampled: {len(files)}."
    )


def _summary_markdown(result: GitHubLookupResult) -> str:
    return "\n".join(
        [
            "# GitHub Lookup Result",
            "",
            f"Status: {result.status}",
            f"Repository: {result.repo}",
            f"Default branch: {result.default_branch}",
            f"Stars: {result.stars}",
            f"Forks: {result.forks}",
            f"Language: {result.language}",
            f"License: {result.license}",
            "",
            "## Summary",
            result.summary,
            "",
            "## Files Sample",
            *[f"- {item.get('path', '')}" for item in result.files_sample],
            "",
            "## Errors",
            *[f"- {error}" for error in result.errors],
            "",
        ]
    )


def _file_summary_markdown(result: GitHubFileLookupResult) -> str:
    return "\n".join(
        [
            "# GitHub File Lookup Result",
            "",
            f"Status: {result.status}",
            f"Repository: {result.repo}",
            f"Path: {result.path}",
            f"Ref: {result.ref}",
            f"Size bytes: {result.size_bytes}",
            f"Redacted: {result.redacted}",
            f"SHA256: {result.content_sha}",
            "",
            "## Preview",
            result.content_preview[:2000],
            "",
            "## Errors",
            *[f"- {error}" for error in result.errors],
            "",
        ]
    )


def _pattern_summary_markdown(result: GitHubPatternExtractionResult) -> str:
    return "\n".join(
        [
            "# GitHub Pattern Extraction Result",
            "",
            f"Status: {result.status}",
            f"Repository: {result.repo}",
            f"Files analyzed: {', '.join(result.files_analyzed)}",
            "",
            "## Summary",
            result.summary,
            "",
            "## Patterns",
            *[
                f"- {pattern.get('pattern_type')}: {pattern.get('name')} ({pattern.get('file')})"
                for pattern in result.patterns
            ],
            "",
            "## Recommendations",
            *[f"- {recommendation}" for recommendation in result.recommendations],
            "",
            "## Errors",
            *[f"- {error}" for error in result.errors],
            "",
        ]
    )


def _license_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("spdx_id") or value.get("name") or "")
    return ""


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
