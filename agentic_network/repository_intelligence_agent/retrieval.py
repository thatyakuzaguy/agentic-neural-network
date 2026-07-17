"""Task-relevant repository intelligence retrieval.

This module keeps the full repository intelligence indexes on disk, then writes
a compact task-specific context for downstream ANN stages. It does not execute
project code, invoke shell commands, apply patches, install packages, load
models, or modify repository source files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import load_filesystem_policy

REPOSITORY_CONTEXT_MD = "26_repository_context.md"
REPOSITORY_CONTEXT_JSON = "26_repository_context.json"
INDEX_DIR = "repository_intelligence"
INDEX_FILES = {
    "functions": "functions.json",
    "classes": "classes.json",
    "imports": "imports.json",
    "call_graph": "call_graph.json",
    "routes": "routes.json",
    "tests_map": "tests_map.json",
    "dependency_graph": "dependency_graph.json",
    "project_summary": "project_summary.json",
}
GENERIC_TOKENS = {
    "add",
    "api",
    "app",
    "class",
    "code",
    "file",
    "files",
    "function",
    "handler",
    "implementation",
    "module",
    "request",
    "requests",
    "route",
    "routes",
    "service",
    "test",
    "tests",
    "the",
}
KEYWORD_GROUPS = {
    "auth": ("auth", "authentication", "login", "password", "reset", "session", "security"),
    "authentication": ("auth", "authentication", "login", "password", "reset", "session", "security"),
    "login": ("auth", "authentication", "login", "password", "session"),
    "password": ("auth", "authentication", "login", "password", "reset", "account", "security"),
    "reset": ("auth", "password", "reset", "recovery", "account"),
    "rate": ("rate", "limit", "limits", "limiting", "throttle", "quota", "abuse", "security"),
    "limit": ("rate", "limit", "limits", "limiting", "throttle", "quota"),
    "limits": ("rate", "limit", "limits", "limiting", "throttle", "quota"),
    "pagination": ("pagination", "page", "page_size", "cursor", "next_cursor", "previous_cursor"),
    "page": ("pagination", "page", "page_size", "cursor"),
    "search": ("search", "query", "filter", "product", "pagination"),
    "product": ("product", "catalog", "search", "pagination"),
    "middleware": ("middleware", "security", "auth", "rate", "limit"),
    "security": ("security", "auth", "abuse", "rate", "limit"),
}


@dataclass(frozen=True)
class RepositoryContextResult:
    """Compact repository context selected for a task."""

    task: str
    matched_files: list[str]
    matched_functions: list[dict[str, Any]]
    matched_classes: list[dict[str, Any]]
    matched_routes: list[dict[str, Any]]
    matched_tests: list[str]
    dependency_paths: list[str]
    recommended_patch_targets: list[str]
    context_artifact: str
    compact_json_artifact: str
    validation_errors: list[str]
    warnings: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def build_repository_context(
    task: str,
    run_dir: Path,
    max_functions: int = 30,
    max_classes: int = 20,
    max_routes: int = 20,
    max_tests: int = 20,
    max_files: int = 40,
) -> RepositoryContextResult:
    """Build 26_repository_context.md/json from run-local repository intelligence indexes."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    validation_errors: list[str] = []
    policy = load_filesystem_policy(
        project_root=resolved_run_dir,
        allowed_roots=(resolved_run_dir,),
    )
    read_errors = policy.validate_read_path(resolved_run_dir)
    if read_errors:
        validation_errors.extend(read_errors)

    indexes = _load_indexes(resolved_run_dir, warnings)
    tokens = _task_tokens(task)
    functions = _records(indexes.get("functions"))
    classes = _records(indexes.get("classes"))
    routes = _records(indexes.get("routes"))
    tests_map = indexes.get("tests_map") if isinstance(indexes.get("tests_map"), dict) else {}
    dependency_graph = indexes.get("dependency_graph") if isinstance(indexes.get("dependency_graph"), dict) else {}

    route_scores = _score_records(routes, tokens, ("path", "handler", "file", "method"))
    function_scores = _score_records(functions, tokens, ("name", "file", "returns"))
    class_scores = _score_records(classes, tokens, ("name", "file", "bases", "methods"))
    file_scores = _score_files(
        tokens=tokens,
        route_scores=route_scores,
        function_scores=function_scores,
        class_scores=class_scores,
        tests_map=tests_map,
        dependency_graph=dependency_graph,
    )

    matched_routes = [record for _score, record in route_scores[:max_routes]]
    matched_functions = [record for _score, record in function_scores[:max_functions]]
    matched_classes = [record for _score, record in class_scores[:max_classes]]
    matched_files = [file for file, _score in sorted(file_scores.items(), key=lambda item: (-item[1], item[0]))[:max_files]]
    dependency_paths = _dependency_paths(matched_files, dependency_graph, max_files=max_files)
    matched_tests = _matched_tests(matched_files, tests_map, tokens, max_tests=max_tests)
    recommended_patch_targets = _recommended_patch_targets(
        matched_files=matched_files,
        dependency_paths=dependency_paths,
        matched_tests=matched_tests,
        tokens=tokens,
        max_files=max_files,
    )

    if not indexes:
        validation_errors.append("repository_intelligence_indexes_missing")
    context = _render_context(
        task=task,
        matched_files=matched_files,
        matched_routes=matched_routes,
        matched_functions=matched_functions,
        matched_classes=matched_classes,
        matched_tests=matched_tests,
        dependency_paths=dependency_paths,
        recommended_patch_targets=recommended_patch_targets,
    )
    compact_payload = {
        "task": task,
        "matched_files": matched_files,
        "matched_functions": matched_functions,
        "matched_classes": matched_classes,
        "matched_routes": matched_routes,
        "matched_tests": matched_tests,
        "dependency_paths": dependency_paths,
        "recommended_patch_targets": recommended_patch_targets,
        "keywords": sorted(tokens),
        "validation_errors": _dedupe(validation_errors),
        "warnings": _dedupe(warnings),
    }
    compact_json = json.dumps(compact_payload, indent=2, sort_keys=True)
    md_path = resolved_run_dir / REPOSITORY_CONTEXT_MD
    json_path = resolved_run_dir / REPOSITORY_CONTEXT_JSON
    md_path.write_text(context.rstrip() + "\n", encoding="utf-8")
    json_path.write_text(compact_json.rstrip() + "\n", encoding="utf-8")

    validation_errors.extend(validate_repository_context(context, compact_payload))
    return RepositoryContextResult(
        task=task,
        matched_files=matched_files,
        matched_functions=matched_functions,
        matched_classes=matched_classes,
        matched_routes=matched_routes,
        matched_tests=matched_tests,
        dependency_paths=dependency_paths,
        recommended_patch_targets=recommended_patch_targets,
        context_artifact=str(md_path),
        compact_json_artifact=str(json_path),
        validation_errors=_dedupe(validation_errors),
        warnings=_dedupe(warnings),
    )


def repository_context_summary_fields(result: RepositoryContextResult | None) -> dict[str, Any]:
    """Return summary.json fields for the compact repository context stage."""

    if result is None:
        return {}
    return {
        "repository_context_enabled": True,
        "repository_context_validation_passed": result.validation_passed,
        "repository_context_files": len(result.matched_files),
        "repository_context_functions": len(result.matched_functions),
        "repository_context_classes": len(result.matched_classes),
        "repository_context_routes": len(result.matched_routes),
        "repository_context_tests": len(result.matched_tests),
        "repository_context_chars": _artifact_chars(result.context_artifact)
        + _artifact_chars(result.compact_json_artifact),
        "repository_context_artifact": result.context_artifact,
        "repository_context_json_artifact": result.compact_json_artifact,
        "repository_context_errors": result.validation_errors,
        "repository_context_warnings": result.warnings,
    }


def validate_repository_context(content: str, payload: dict[str, Any]) -> list[str]:
    """Validate fixed context artifact format and compact JSON shape."""

    errors: list[str] = []
    required_headings = (
        "REPOSITORY CONTEXT",
        "MATCHED FILES",
        "MATCHED ROUTES",
        "MATCHED FUNCTIONS",
        "MATCHED CLASSES",
        "MATCHED TESTS",
        "DEPENDENCY PATHS",
        "RECOMMENDED PATCH TARGETS",
        "CONFIDENCE",
    )
    for heading in required_headings:
        if heading not in content:
            errors.append(f"missing_section:{heading}")
    if "\nCONFIDENCE\nHigh" not in content:
        errors.append("confidence_not_high")
    for key in (
        "task",
        "matched_files",
        "matched_functions",
        "matched_classes",
        "matched_routes",
        "matched_tests",
        "dependency_paths",
        "recommended_patch_targets",
    ):
        if key not in payload:
            errors.append(f"compact_json_missing:{key}")
    forbidden_raw_markers = ("\"file_dependencies\"", "\"service_dependencies\"", "\"route_dependencies\"")
    if any(marker in content for marker in forbidden_raw_markers):
        errors.append("raw_index_content_in_markdown")
    return _dedupe(errors)


def _load_indexes(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    indexes: dict[str, Any] = {}
    index_dir = run_dir / INDEX_DIR
    if not index_dir.exists():
        warnings.append("missing_repository_intelligence_dir")
        return indexes
    for key, filename in INDEX_FILES.items():
        path = index_dir / filename
        if not path.exists():
            warnings.append(f"missing_index:{filename}")
            continue
        try:
            indexes[key] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append(f"invalid_index_json:{filename}")
        except OSError:
            warnings.append(f"unreadable_index:{filename}")
    return indexes


def _task_tokens(task: str) -> set[str]:
    raw = _tokens(task)
    expanded = set(raw)
    for token in raw:
        expanded.update(KEYWORD_GROUPS.get(token, ()))
    return {token for token in expanded if token not in GENERIC_TOKENS}


def _score_records(
    records: list[dict[str, Any]],
    tokens: set[str],
    fields: tuple[str, ...],
) -> list[tuple[int, dict[str, Any]]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for record in records:
        text = " ".join(_field_text(record.get(field)) for field in fields).lower()
        record_tokens = _tokens(text)
        overlap = tokens & record_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        for token in tokens:
            if token in text:
                score += 3
        file_text = str(record.get("file", "")).lower()
        name_text = str(record.get("name") or record.get("handler") or "").lower()
        score += sum(8 for token in tokens if token in file_text)
        score += sum(6 for token in tokens if token in name_text)
        scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("file", "")), str(item[1].get("name", ""))))
    return scored


def _score_files(
    *,
    tokens: set[str],
    route_scores: list[tuple[int, dict[str, Any]]],
    function_scores: list[tuple[int, dict[str, Any]]],
    class_scores: list[tuple[int, dict[str, Any]]],
    tests_map: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> dict[str, int]:
    scores: dict[str, int] = {}
    for score, record in route_scores:
        _add_file_score(scores, str(record.get("file", "")), score + 35)
    for score, record in function_scores:
        _add_file_score(scores, str(record.get("file", "")), score + 20)
    for score, record in class_scores:
        _add_file_score(scores, str(record.get("file", "")), score + 16)
    for source, tests in tests_map.items():
        if source in scores and isinstance(tests, list) and tests:
            scores[source] += 10
            for test_file in tests:
                _add_file_score(scores, str(test_file), max(5, scores[source] // 3))
    for entry in _file_dependencies(dependency_graph):
        file_path = str(entry.get("file", ""))
        if file_path in scores:
            for dependency in entry.get("depends_on", []):
                _add_file_score(scores, str(dependency), max(4, scores[file_path] // 4))
    for file_path in list(scores):
        lower = file_path.lower()
        scores[file_path] += sum(12 for token in tokens if token in lower)
        if _is_test_file(file_path):
            scores[file_path] -= 8
        if ("middleware" in tokens or "rate" in tokens or "limit" in tokens) and "middleware" in lower:
            scores[file_path] += 12
        if ("config" in lower or "settings" in lower) and ({"rate", "limit", "threshold"} & tokens):
            scores[file_path] += 10
    return {path: score for path, score in scores.items() if path}


def _dependency_paths(
    matched_files: list[str],
    dependency_graph: dict[str, Any],
    *,
    max_files: int,
) -> list[str]:
    selected = set(matched_files)
    paths: list[str] = []
    for entry in _file_dependencies(dependency_graph):
        file_path = str(entry.get("file", ""))
        depends_on = [str(path) for path in entry.get("depends_on", [])]
        depended_by = [str(path) for path in entry.get("depended_by", [])]
        if file_path in selected:
            paths.extend(depends_on)
            paths.extend(depended_by[:5])
        elif any(path in selected for path in depends_on + depended_by):
            paths.append(file_path)
    return _dedupe([path for path in paths if path])[:max_files]


def _matched_tests(
    matched_files: list[str],
    tests_map: dict[str, Any],
    tokens: set[str],
    *,
    max_tests: int,
) -> list[str]:
    tests: list[str] = []
    for source in matched_files:
        mapped = tests_map.get(source)
        if isinstance(mapped, list):
            tests.extend(str(item) for item in mapped if item)
    for source, mapped in tests_map.items():
        if not isinstance(mapped, list):
            continue
        if any(token in str(source).lower() for token in tokens):
            tests.extend(str(item) for item in mapped if item)
        for test_file in mapped:
            if any(token in str(test_file).lower() for token in tokens):
                tests.append(str(test_file))
    return _dedupe(tests)[:max_tests]


def _recommended_patch_targets(
    *,
    matched_files: list[str],
    dependency_paths: list[str],
    matched_tests: list[str],
    tokens: set[str],
    max_files: int,
) -> list[str]:
    candidates = list(matched_files)
    candidates.extend(path for path in dependency_paths if not _is_test_file(path))
    candidates.extend(matched_tests)
    if {"rate", "limit"} & tokens:
        constants = [
            path
            for path in matched_files + dependency_paths
            if any(part in path.lower() for part in ("config", "settings"))
        ]
        candidates = constants + candidates
    return _dedupe(candidates)[:max_files]


def _render_context(
    *,
    task: str,
    matched_files: list[str],
    matched_routes: list[dict[str, Any]],
    matched_functions: list[dict[str, Any]],
    matched_classes: list[dict[str, Any]],
    matched_tests: list[str],
    dependency_paths: list[str],
    recommended_patch_targets: list[str],
) -> str:
    sections = [
        ("REPOSITORY CONTEXT", [f"Task-relevant repository context for: {task}."]),
        ("MATCHED FILES", matched_files or ["None"]),
        ("MATCHED ROUTES", [_route_label(route) for route in matched_routes] or ["None"]),
        ("MATCHED FUNCTIONS", [_function_label(function) for function in matched_functions] or ["None"]),
        ("MATCHED CLASSES", [_class_label(class_record) for class_record in matched_classes] or ["None"]),
        ("MATCHED TESTS", matched_tests or ["None"]),
        ("DEPENDENCY PATHS", dependency_paths or ["None"]),
        ("RECOMMENDED PATCH TARGETS", recommended_patch_targets or ["None"]),
    ]
    lines: list[str] = []
    for heading, items in sections:
        lines.append(heading)
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    lines.extend(["CONFIDENCE", "High"])
    return "\n".join(lines).strip()


def _route_label(route: dict[str, Any]) -> str:
    return (
        f"{route.get('method', '')} {route.get('path', '')} -> "
        f"{route.get('handler', '')} ({route.get('file', '')})"
    ).strip()


def _function_label(function: dict[str, Any]) -> str:
    return f"{function.get('name', '')} ({function.get('file', '')}:{function.get('line', '')})"


def _class_label(class_record: dict[str, Any]) -> str:
    methods = class_record.get("methods")
    method_text = ", ".join(str(item) for item in methods[:5]) if isinstance(methods, list) else ""
    suffix = f" methods={method_text}" if method_text else ""
    return f"{class_record.get('name', '')} ({class_record.get('file', '')}:{class_record.get('line', '')}){suffix}"


def _file_dependencies(dependency_graph: dict[str, Any]) -> list[dict[str, Any]]:
    entries = dependency_graph.get("file_dependencies", [])
    return entries if isinstance(entries, list) else []


def _records(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _field_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values())
    return str(value or "")


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"[_/.-]+", " ", text.lower())
    return set(re.findall(r"[a-z][a-z0-9]{2,}", normalized))


def _add_file_score(scores: dict[str, int], file_path: str, score: int) -> None:
    if file_path:
        scores[file_path] = scores.get(file_path, 0) + score


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return "/tests/" in f"/{lowered}" or Path(lowered).name.startswith("test_")


def _artifact_chars(path_text: str) -> int:
    try:
        return len(Path(path_text).read_text(encoding="utf-8"))
    except OSError:
        return 0


def _dedupe(values) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build compact task-relevant repository context.")
    parser.add_argument("run_dir", type=Path, help="Pipeline run directory containing repository_intelligence indexes.")
    parser.add_argument("--task", required=True, help="Task used for deterministic repository context retrieval.")
    parser.add_argument("--json", action="store_true", help="Print compact result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_repository_context(args.task, args.run_dir)
    payload = {
        "task": result.task,
        "matched_files": result.matched_files,
        "matched_functions": len(result.matched_functions),
        "matched_classes": len(result.matched_classes),
        "matched_routes": len(result.matched_routes),
        "matched_tests": result.matched_tests,
        "dependency_paths": result.dependency_paths,
        "context_artifact": result.context_artifact,
        "compact_json_artifact": result.compact_json_artifact,
        "validation_errors": result.validation_errors,
        "warnings": result.warnings,
        "validation_passed": result.validation_passed,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(Path(result.context_artifact).read_text(encoding="utf-8"))
        print(f"\nWrote: {result.context_artifact}")
        print(f"Wrote: {result.compact_json_artifact}")
        if result.warnings:
            print("\nWARNINGS", file=sys.stderr)
            for warning in result.warnings:
                print(f"- {warning}", file=sys.stderr)
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"- {error}", file=sys.stderr)
    return 0 if result.validation_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
