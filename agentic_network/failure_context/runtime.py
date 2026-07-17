"""Compile compact failure payloads for repair agents.

The compiler is deterministic and read-only. It converts review findings,
test output, command metadata, patches, and affected files into a bounded
payload for Fixer/Self-Healing agents. Python files get AST-localized source
snippets; whole files are not included by default.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.test_validity_gate.runtime import evaluate_test_validity_gate

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
MAX_TEXT_CHARS = 6000
MAX_SOURCE_CHARS = 8000
TRACE_FILE_LINE = re.compile(r'File "([^"]+)", line (\d+)')
PYTEST_FILE_LINE = re.compile(r"(?m)^([A-Za-z]:[^:\n]+|/[^:\n]+|[\w./\\-]+\.py):(\d+):?")
DIFF_FILE_LINE = re.compile(r"(?m)^diff --git a/(.*?) b/(.*?)$")
INTEGRATION_KEYWORDS = {
    "webhook",
    "stripe",
    "redis",
    "postgres",
    "postgresql",
    "database",
    "migration",
    "alembic",
    "docker",
    "compose",
    "container",
    "service",
    "port",
    "connection refused",
    "timeout",
    "e2e",
    "integration",
    "webpack",
    "vite",
    "next",
    "react",
    "typescript",
    "node",
    "env",
}
SYSTEM_KEYWORDS = {
    "Stripe": {"stripe", "webhook", "signature", "customer", "subscription", "checkout"},
    "PostgreSQL": {"postgres", "postgresql", "database", "sqlalchemy", "alembic", "migration", "relation", "table", "column"},
    "Redis": {"redis", "cache", "queue", "celery", "broker"},
    "Docker Compose": {"docker", "compose", "container", "service", "port", "connection refused"},
    "Frontend": {"react", "next", "vite", "webpack", "typescript", "node", "npm", "jsdom"},
    "Auth": {"auth", "jwt", "token", "session", "oauth", "permission", "rbac"},
}
CROSS_DOMAIN_CANDIDATE_PATTERNS = (
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "compose*.yml",
    "compose*.yaml",
    "Dockerfile",
    ".env",
    ".env.*",
    "*.env",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "next.config.*",
    "vite.config.*",
    "alembic.ini",
    "*.sql",
    "*.yaml",
    "*.yml",
)
CROSS_DOMAIN_PATH_PARTS = {
    "alembic",
    "migrations",
    "migration",
    "docker",
    "config",
    "configs",
    "settings",
    "tests",
    "integration",
    "e2e",
}
MAX_SUSPECTS = 8
MAX_SUSPECT_EXCERPT_CHARS = 1600


@dataclass(frozen=True)
class _Reference:
    path: str
    line: int | None = None


def compile_pipeline_failure_context(
    *,
    project_root: str | Path,
    outputs: dict[str, str],
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compile a targeted payload from pipeline stage outputs."""

    review_text = "\n\n".join(
        value
        for value in (
            outputs.get("reviewer", ""),
            outputs.get("static_sanity", ""),
            outputs.get("post_fix_static_sanity", ""),
        )
        if value
    )
    test_text = outputs.get("test_runner", "")
    patch_text = "\n\n".join(
        value for value in (outputs.get("execution", ""), outputs.get("patch_apply", "")) if value
    )
    return compile_failure_context(
        project_root=project_root,
        reviewer_report=review_text,
        test_report=test_text,
        stdout=test_text,
        stderr="",
        commands=[],
        affected_files=[],
        patch_text=patch_text,
        user_request=outputs.get("user", ""),
        product_requirements=outputs.get("product", ""),
        architecture_plan=outputs.get("architect", ""),
        test_plan=outputs.get("test_revised") or outputs.get("test", ""),
        code_plan=outputs.get("code", ""),
        artifact_paths=artifact_paths or {},
        source="pipeline",
    )


def compile_failure_context(
    *,
    project_root: str | Path | None = None,
    reviewer_report: str = "",
    test_report: str = "",
    stdout: str = "",
    stderr: str = "",
    commands: list[Any] | None = None,
    affected_files: list[Any] | None = None,
    patch_text: str = "",
    user_request: str = "",
    product_requirements: str = "",
    architecture_plan: str = "",
    test_plan: str = "",
    code_plan: str = "",
    artifact_paths: dict[str, str] | None = None,
    source: str = "runtime",
) -> dict[str, Any]:
    """Return a compact repair payload with optional AST-localized snippets."""

    root = Path(project_root).resolve() if project_root else None
    combined_trace = "\n".join(_clip(text) for text in (test_report, stdout, stderr, reviewer_report))
    refs = _dedupe_refs(
        [
            *_references_from_trace(combined_trace),
            *_references_from_patch(patch_text),
            *[_Reference(str(item)) for item in (affected_files or []) if str(item).strip()],
        ]
    )
    targets = [_target_payload(root, ref) for ref in refs]
    findings = _finding_lines(reviewer_report, test_report, stdout, stderr)
    command_payload = [_stringify_command(command) for command in (commands or [])]
    isolation = isolate_cross_domain_root_cause(
        project_root=root,
        trace_text=combined_trace,
        targets=targets,
        commands=command_payload,
        patch_text=patch_text,
        affected_files=[str(item) for item in (affected_files or [])],
    )
    test_validity = evaluate_test_validity_gate(
        test_report=test_report,
        stdout=stdout,
        stderr=stderr,
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
        test_plan=test_plan,
        code_plan=code_plan,
        targets=targets,
        affected_files=[str(item) for item in (affected_files or [])],
        artifact_paths=artifact_paths or {},
    )
    status = "TARGETED" if targets else ("TRACE_ONLY" if findings or combined_trace.strip() else "EMPTY")
    return {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "status": status,
        "payload_strategy": "ast_node_or_trace_slice",
        "project_root": str(root) if root else "",
        "commands": command_payload,
        "findings": findings[:30],
        "targets": targets,
        "root_cause_isolation": isolation,
        "test_validity": test_validity,
        "trace_excerpt": _clip(combined_trace),
        "patch_files": [ref.path for ref in _references_from_patch(patch_text)],
        "artifact_paths": artifact_paths or {},
        "code_plan_excerpt": _clip(code_plan, 3000),
        "limits": {
            "max_text_chars": MAX_TEXT_CHARS,
            "max_source_chars": MAX_SOURCE_CHARS,
            "whole_file_sent": False,
            "ast_node_preferred": True,
        },
        "safety": {
            "read_only": True,
            "no_shell": True,
            "no_install": True,
            "no_network": True,
            "protected_paths_excluded": True,
            "cross_domain_scan_read_only": True,
        },
    }


def isolate_cross_domain_root_cause(
    *,
    project_root: str | Path | None,
    trace_text: str,
    targets: list[dict[str, Any]],
    commands: list[str] | None = None,
    patch_text: str = "",
    affected_files: list[str] | None = None,
) -> dict[str, Any]:
    """Rank cross-domain suspects for integration-boundary failures.

    The isolation pass is deterministic and read-only. It does not replace the
    AST-localized symptom; it adds a ranked suspect set so the Fixer can inspect
    config, migrations, fixtures, and service wiring before rewriting a healthy
    Python function that merely surfaced the exception.
    """

    root = Path(project_root).resolve() if project_root else None
    command_text = "\n".join(commands or [])
    combined = "\n".join(value for value in (trace_text, command_text, patch_text) if value)
    systems = _detect_systems(combined)
    symptom_confidence = _symptom_confidence(targets, combined)
    integration_failure = _looks_like_integration_failure(combined, targets, systems)
    suspects = _rank_cross_domain_suspects(
        root=root,
        trace_text=combined,
        targets=targets,
        systems=systems,
        affected_files=affected_files or [],
    )
    if integration_failure:
        failure_type = "integration_boundary_failure"
    elif suspects:
        failure_type = "possible_cross_domain_failure"
    else:
        failure_type = "unit_or_localized_failure"
    return {
        "version": "1.0",
        "failure_type": failure_type,
        "systems": systems,
        "symptom": _symptom_payload(targets, symptom_confidence),
        "ranked_suspects": suspects,
        "fix_policy": {
            "do_not_rewrite_symptom_node_until_cross_domain_suspects_checked": bool(
                integration_failure and suspects and symptom_confidence < 0.7
            ),
            "prefer_config_fixture_or_migration_fix_when_ranked_higher": True,
            "request_diagnostic_followup_when_confidence_is_ambiguous": bool(
                integration_failure and suspects and suspects[0]["confidence"] < 0.72
            ),
            "escalate_after_max_attempts": True,
        },
        "confidence_notes": _confidence_notes(integration_failure, systems, suspects, symptom_confidence),
        "safety": {
            "read_only": True,
            "whole_files_sent": False,
            "protected_paths_excluded": True,
        },
    }


def write_failure_context_artifacts(
    run_dir: str | Path,
    context: dict[str, Any],
    *,
    json_name: str = "06a_failure_context.json",
    markdown_name: str = "06a_failure_context.md",
) -> list[str]:
    """Write JSON and Markdown failure context artifacts."""

    target = Path(run_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / json_name
    markdown_path = target / markdown_name
    json_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    markdown_path.write_text(render_failure_context_markdown(context), encoding="utf-8")
    return [str(json_path), str(markdown_path)]


def render_failure_context_markdown(context: dict[str, Any]) -> str:
    """Render a compact Markdown form suitable for Fixer prompts."""

    lines = [
        "FAILURE CONTEXT",
        f"- Status: {context.get('status')}",
        f"- Strategy: {context.get('payload_strategy')}",
        f"- Whole file sent: {context.get('limits', {}).get('whole_file_sent')}",
        "",
        "COMMANDS",
        *[f"- {command}" for command in context.get("commands", [])],
        "",
        "FINDINGS",
        *[f"- {finding}" for finding in context.get("findings", [])],
        "",
        "TARGETS",
    ]
    for target in context.get("targets", []):
        lines.extend(
            [
                f"- Path: {target.get('path')}",
                f"  Line: {target.get('line') or 'unknown'}",
                f"  AST: {target.get('ast_node_type') or 'none'} {target.get('symbol') or ''}".rstrip(),
                f"  Lines: {target.get('line_start') or 'unknown'}-{target.get('line_end') or 'unknown'}",
                f"  Reason: {target.get('reason')}",
            ]
        )
        excerpt = str(target.get("source_excerpt") or "").strip()
        if excerpt:
            lines.extend(["  Source excerpt:", _indent_fenced(excerpt)])
    trace = str(context.get("trace_excerpt") or "").strip()
    isolation = context.get("root_cause_isolation") or {}
    test_validity = context.get("test_validity") or {}
    if isolation:
        lines.extend(
            [
                "",
                "CROSS-DOMAIN ROOT CAUSE ISOLATION",
                f"- Failure type: {isolation.get('failure_type')}",
                f"- Systems: {', '.join(isolation.get('systems') or []) or 'none'}",
                "- Fix policy:",
            ]
        )
        policy = isolation.get("fix_policy") or {}
        lines.extend(f"  - {key}: {value}" for key, value in policy.items())
        lines.append("- Ranked suspects:")
        suspects = isolation.get("ranked_suspects") or []
        if not suspects:
            lines.append("  - none")
        for suspect in suspects:
            lines.extend(
                [
                    f"  - Path: {suspect.get('path')}",
                    f"    Domain: {suspect.get('domain')}",
                    f"    Confidence: {suspect.get('confidence')}",
                    f"    Reason: {suspect.get('reason')}",
                ]
            )
            excerpt = str(suspect.get("source_excerpt") or "").strip()
            if excerpt:
                lines.extend(["    Source excerpt:", _indent_fenced(excerpt, spaces=4)])
    if test_validity:
        lines.extend(
            [
                "",
                "TEST VALIDITY GATE",
                f"- Status: {test_validity.get('status')}",
                f"- Classification: {test_validity.get('classification')}",
                f"- Confidence: {test_validity.get('confidence')}",
                f"- Recommended next action: {test_validity.get('recommended_next_action')}",
                "- Fix policy:",
            ]
        )
        policy = test_validity.get("fix_policy") or {}
        lines.extend(f"  - {key}: {value}" for key, value in policy.items())
        lines.append("- Reasons:")
        lines.extend(f"  - {reason}" for reason in test_validity.get("reasons", []) or ["None"])
        assertion_evidence = test_validity.get("assertion_evidence") or []
        if assertion_evidence:
            lines.append("- Assertion evidence:")
            lines.extend(f"  - {item}" for item in assertion_evidence)
        contract_authority = (test_validity.get("contract_evidence") or {}).get("contract_authority") or {}
        if contract_authority:
            lines.extend(
                [
                    "- Contract authority:",
                    f"  - Status: {contract_authority.get('status')}",
                    f"  - Owner: {contract_authority.get('owner')}",
                    f"  - Recommended next action: {contract_authority.get('recommended_next_action')}",
                ]
            )
            lines.extend(f"  - Reason: {reason}" for reason in contract_authority.get("reasons", []) or ["None"])
    if trace:
        lines.extend(["", "TRACE EXCERPT", _fenced(trace)])
    code = str(context.get("code_plan_excerpt") or "").strip()
    if code and context.get("status") == "EMPTY":
        lines.extend(["", "CODE PLAN EXCERPT", _fenced(code)])
    lines.append("")
    return "\n".join(lines)


def _looks_like_integration_failure(
    text: str,
    targets: list[dict[str, Any]],
    systems: list[str],
) -> bool:
    lower = text.lower()
    if systems and any(keyword in lower for keyword in INTEGRATION_KEYWORDS):
        return True
    if any("integration" in str(target.get("path", "")).lower() for target in targets):
        return True
    if any("tests" in str(target.get("path", "")).lower() and systems for target in targets):
        return True
    return False


def _detect_systems(text: str) -> list[str]:
    lower = text.lower()
    systems = [
        system
        for system, keywords in SYSTEM_KEYWORDS.items()
        if any(keyword in lower for keyword in keywords)
    ]
    return systems


def _symptom_confidence(targets: list[dict[str, Any]], text: str) -> float:
    if not targets:
        return 0.0
    first = targets[0]
    confidence = 0.46 if first.get("reason") == "ast_localized" else 0.35
    lower_path = str(first.get("path", "")).lower()
    lower_text = text.lower()
    if "assert" in lower_text or "traceback" in lower_text:
        confidence += 0.08
    if any(part in lower_path for part in ("test_", "/tests/", "\\tests\\")):
        confidence -= 0.12
    if any(keyword in lower_text for keyword in ("connection refused", "missing table", "no such table", "relation", "port")):
        confidence -= 0.14
    return max(0.1, min(confidence, 0.86))


def _symptom_payload(targets: list[dict[str, Any]], confidence: float) -> dict[str, Any]:
    if not targets:
        return {"file": "", "line": None, "symbol": "", "confidence": confidence}
    target = targets[0]
    return {
        "file": target.get("path", ""),
        "line": target.get("line"),
        "symbol": target.get("symbol", ""),
        "ast_node_type": target.get("ast_node_type", ""),
        "confidence": confidence,
        "note": "Traceback location may be symptom, not root cause, for integration failures.",
    }


def _rank_cross_domain_suspects(
    *,
    root: Path | None,
    trace_text: str,
    targets: list[dict[str, Any]],
    systems: list[str],
    affected_files: list[str],
) -> list[dict[str, Any]]:
    if root is None or not root.exists():
        return []
    lower_trace = trace_text.lower()
    target_paths = {str(target.get("path", "")).replace("\\", "/").lower() for target in targets}
    candidates = _cross_domain_candidate_paths(root, affected_files, lower_trace)
    suspects: list[dict[str, Any]] = []
    for path in candidates:
        relative = path.relative_to(root)
        if _has_protected_part(relative) or not path.is_file():
            continue
        content = _safe_read(path)
        domain = _domain_for_path(relative)
        score, reasons = _score_cross_domain_candidate(
            relative=relative,
            content=content,
            trace_text=lower_trace,
            systems=systems,
            target_paths=target_paths,
            domain=domain,
        )
        if score <= 0:
            continue
        excerpt = _matching_excerpt(content.splitlines(), lower_trace)
        suspects.append(
            {
                "path": str(relative).replace("\\", "/"),
                "domain": domain,
                "confidence": round(min(score / 100, 0.95), 2),
                "reason": "; ".join(reasons[:4]),
                "source_excerpt": excerpt,
                "whole_file_sent": False,
            }
        )
    suspects.sort(key=lambda item: (-float(item["confidence"]), str(item["path"])))
    return suspects[:MAX_SUSPECTS]


def _cross_domain_candidate_paths(root: Path, affected_files: list[str], trace_text: str) -> list[Path]:
    candidates: list[Path] = []
    for value in affected_files:
        resolved = _resolve_reference(root, value)
        if resolved is not None:
            candidates.append(resolved)
    for pattern in CROSS_DOMAIN_CANDIDATE_PATTERNS:
        candidates.extend(root.glob(pattern))
        candidates.extend(root.glob(f"**/{pattern}"))
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = {part.lower() for part in relative.parts}
        if parts.intersection(CROSS_DOMAIN_PATH_PARTS):
            candidates.append(path)
        elif _path_mentions_trace_tokens(relative, trace_text):
            candidates.append(path)
    return _dedupe_paths(candidates, root)[:120]


def _score_cross_domain_candidate(
    *,
    relative: Path,
    content: str,
    trace_text: str,
    systems: list[str],
    target_paths: set[str],
    domain: str,
) -> tuple[int, list[str]]:
    path_text = str(relative).replace("\\", "/").lower()
    content_lower = content[:20000].lower()
    score = 0
    reasons: list[str] = []
    if path_text in target_paths:
        score += 18
        reasons.append("directly referenced by failure trace")
    if domain != "application_code":
        score += 18
        reasons.append(f"{domain} can affect integration boundaries")
    if "test" in path_text or "integration" in path_text:
        score += 22
        reasons.append("test or fixture may define the failing integration contract")
    for system in systems:
        keywords = SYSTEM_KEYWORDS.get(system, set())
        matches = [keyword for keyword in keywords if keyword in path_text or keyword in content_lower]
        if matches:
            score += 16 + min(len(matches) * 3, 18)
            reasons.append(f"matches {system} signals: {', '.join(matches[:4])}")
    if any(token in trace_text for token in ("missing table", "no such table", "relation", "column")):
        if domain in {"migration", "database"}:
            score += 34
            reasons.append("database schema error points to migrations or SQL")
    if "connection refused" in trace_text or "port" in trace_text:
        if domain in {"docker_compose", "environment", "config"}:
            score += 32
            reasons.append("connection/port error points to service wiring")
    if "signature" in trace_text or "webhook" in trace_text:
        if domain in {"test_fixture", "environment", "config"}:
            score += 28
            reasons.append("webhook/signature failures often come from fixtures or secrets")
    if any(token in trace_text for token in ("webpack", "vite", "typescript", "ts-jest", "jsdom")):
        if domain in {"frontend_config", "package_manifest", "test_fixture"}:
            score += 30
            reasons.append("frontend tooling failure points to JS/TS config or package metadata")
    if len(content) > MAX_SOURCE_CHARS * 3:
        score -= 8
        reasons.append("large file excerpt capped")
    return score, reasons


def _domain_for_path(path: Path) -> str:
    text = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    if name.startswith("docker-compose") or name.startswith("compose"):
        return "docker_compose"
    if name == "dockerfile":
        return "docker"
    if name.startswith(".env") or name.endswith(".env") or ".env." in name:
        return "environment"
    if "alembic" in text or "migration" in text or path.suffix.lower() == ".sql":
        return "migration" if "alembic" in text or "migration" in text else "database"
    if "test" in text or "fixture" in text:
        return "test_fixture"
    if name in {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        return "package_manifest"
    if name.startswith(("next.config", "vite.config")) or name == "tsconfig.json":
        return "frontend_config"
    if path.suffix.lower() in {".yml", ".yaml", ".toml", ".json"}:
        return "config"
    return "application_code"


def _path_mentions_trace_tokens(path: Path, trace_text: str) -> bool:
    text = str(path).replace("\\", "/").lower()
    tokens = {token for token in re.split(r"[^a-z0-9_]+", trace_text) if len(token) >= 5}
    return any(token in text for token in tokens)


def _matching_excerpt(lines: list[str], trace_text: str) -> str:
    if not lines:
        return ""
    tokens = [
        token
        for token in re.split(r"[^a-z0-9_]+", trace_text.lower())
        if len(token) >= 5
    ][:40]
    match_indexes = [
        index + 1
        for index, line in enumerate(lines)
        if any(token in line.lower() for token in tokens)
    ]
    if match_indexes:
        return _source_excerpt_from_lines(
            lines,
            match_indexes[0],
            context_lines=2,
            max_chars=MAX_SUSPECT_EXCERPT_CHARS,
        )
    return _source_excerpt_from_lines(
        lines,
        1,
        min(len(lines), 12),
        context_lines=0,
        max_chars=MAX_SUSPECT_EXCERPT_CHARS,
    )


def _confidence_notes(
    integration_failure: bool,
    systems: list[str],
    suspects: list[dict[str, Any]],
    symptom_confidence: float,
) -> list[str]:
    notes: list[str] = []
    if integration_failure:
        notes.append("Failure includes integration-boundary signals.")
    if systems:
        notes.append("Detected systems: " + ", ".join(systems))
    if suspects and suspects[0]["confidence"] > symptom_confidence:
        notes.append("Highest-ranked cross-domain suspect outranks traceback symptom.")
    if not suspects:
        notes.append("No cross-domain files were confidently ranked.")
    return notes


def _target_payload(root: Path | None, ref: _Reference) -> dict[str, Any]:
    path = _resolve_reference(root, ref.path)
    base: dict[str, Any] = {
        "path": str(path) if path else ref.path,
        "line": ref.line,
        "exists": bool(path and path.is_file()),
        "reason": "referenced_by_trace_or_patch",
        "ast_node_type": "",
        "symbol": "",
        "line_start": ref.line,
        "line_end": ref.line,
        "source_excerpt": "",
        "excluded": False,
    }
    if path is None:
        base["reason"] = "unresolved_path"
        return base
    if root and not _is_relative_to(path, root):
        base["excluded"] = True
        base["reason"] = "outside_project_root"
        return base
    relative = path.relative_to(root) if root and _is_relative_to(path, root) else path
    if _has_protected_part(relative):
        base["excluded"] = True
        base["reason"] = "protected_path"
        return base
    if not path.is_file():
        base["reason"] = "file_missing"
        return base
    if path.suffix.lower() != ".py":
        base["source_excerpt"] = _source_excerpt(path, ref.line)
        base["reason"] = "non_python_excerpt"
        return base
    ast_info = _python_ast_slice(path, ref.line)
    base.update(ast_info)
    return base


def _python_ast_slice(path: Path, line: int | None) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {
            "reason": "python_parse_failed",
            "source_excerpt": _source_excerpt_from_lines(lines, line),
        }
    node = _smallest_node_for_line(tree, line or 1)
    if node is None:
        return {
            "reason": "no_ast_node_for_line",
            "source_excerpt": _source_excerpt_from_lines(lines, line),
        }
    start = int(getattr(node, "lineno", line or 1))
    end = int(getattr(node, "end_lineno", start))
    symbol = getattr(node, "name", "") or getattr(node, "arg", "") or ""
    return {
        "reason": "ast_localized",
        "ast_node_type": type(node).__name__,
        "symbol": symbol,
        "line_start": start,
        "line_end": end,
        "source_excerpt": _source_excerpt_from_lines(lines, start, end, context_lines=0),
    }


def _smallest_node_for_line(tree: ast.AST, line: int) -> ast.AST | None:
    candidates: list[ast.AST] = []
    for node in ast.walk(tree):
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if isinstance(start, int) and isinstance(end, int) and start <= line <= end:
            candidates.append(node)
    if not candidates:
        return None
    semantic_candidates = [
        node
        for node in candidates
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    target_candidates = semantic_candidates or candidates
    return min(
        target_candidates,
        key=lambda node: (
            getattr(node, "end_lineno", line) - getattr(node, "lineno", line),
            -getattr(node, "lineno", line),
        ),
    )


def _references_from_trace(text: str) -> list[_Reference]:
    refs = [_Reference(path, int(line)) for path, line in TRACE_FILE_LINE.findall(text or "")]
    refs.extend(_Reference(path, int(line)) for path, line in PYTEST_FILE_LINE.findall(text or ""))
    return refs


def _references_from_patch(text: str) -> list[_Reference]:
    return [_Reference(new) for _old, new in DIFF_FILE_LINE.findall(text or "")]


def _resolve_reference(root: Path | None, text: str) -> Path | None:
    raw = text.strip().strip('"').replace("\\", "/")
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    if root is not None:
        return (root / raw).resolve()
    return candidate.resolve()


def _source_excerpt(path: Path, line: int | None) -> str:
    return _source_excerpt_from_lines(path.read_text(encoding="utf-8", errors="replace").splitlines(), line)


def _source_excerpt_from_lines(
    lines: list[str],
    line: int | None,
    end_line: int | None = None,
    *,
    context_lines: int = 3,
    max_chars: int = MAX_SOURCE_CHARS,
) -> str:
    if not lines:
        return ""
    start = max(1, (line or 1) - context_lines)
    end = min(len(lines), (end_line or line or 1) + context_lines)
    excerpt = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    return _clip(excerpt, max_chars)


def _finding_lines(*texts: str) -> list[str]:
    findings: list[str] = []
    for text in texts:
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if any(token in lower for token in ("error", "failed", "failure", "bug", "risk", "blocking", "needs fix")):
                findings.append(stripped[:500])
    return _dedupe(findings)


def _stringify_command(command: Any) -> str:
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command)
    return str(command)


def _dedupe_refs(refs: list[_Reference]) -> list[_Reference]:
    seen: set[tuple[str, int | None]] = set()
    result: list[_Reference] = []
    for ref in refs:
        key = (ref.path.replace("\\", "/").lower(), ref.line)
        if not ref.path.strip() or key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result[:20]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe_paths(paths: list[Path], root: Path) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not _is_relative_to(resolved, root):
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _clip(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n...[truncated]"


def _fenced(text: str) -> str:
    return "```\n" + _clip(text) + "\n```"


def _indent_fenced(text: str, *, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in _fenced(text).splitlines())
