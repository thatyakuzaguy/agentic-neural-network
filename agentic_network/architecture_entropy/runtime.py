"""Deterministic read-only gate for architectural entropy.

The gate detects when repeated local fixes are becoming design debt. It does
not execute code, write files, call models, or apply patches.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

STATUS_ENTROPY_OK = "ENTROPY_OK"
STATUS_ENTROPY_WARNING = "ENTROPY_WARNING"
STATUS_REFACTOR_RECOMMENDED = "REFACTOR_RECOMMENDED"
STATUS_ARCHITECTURE_REVIEW_REQUIRED = "ARCHITECTURE_REVIEW_REQUIRED"

DIFF_PATH_LINE = re.compile(r"(?m)^diff --git a/(.*?) b/(.*?)$")
PATCH_HEADER_LINE = re.compile(r"(?m)^\+\+\+\s+(?:b/)?(.+?)\s*$")
CONTROL_FLOW_LINE = re.compile(r"^\+\s*(?:if|elif|else|for|while|try|except|match|case)\b")
FUNCTION_LINE = re.compile(r"^\+\s*(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
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
MAX_PATCHES_SCANNED = 40
MAX_HISTORY_RUNS = 80


def evaluate_architecture_entropy(
    run_dir: str | Path,
    *,
    runs_root: str | Path | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return entropy/refactor guidance for a run without side effects."""

    resolved_run = Path(run_dir).resolve()
    root = Path(project_root).resolve() if project_root is not None else _infer_project_root(resolved_run)
    history_root = Path(runs_root).resolve() if runs_root is not None else resolved_run.parent
    patch_texts = _patch_texts(resolved_run)
    target_paths = _dedupe(
        path
        for patch_text in patch_texts
        for path in _target_paths(patch_text)
        if path and not _has_protected_part(Path(path))
    )
    added_control_flow = sum(_added_control_flow_count(text) for text in patch_texts)
    added_functions = _dedupe(
        symbol
        for patch_text in patch_texts
        for symbol in FUNCTION_LINE.findall(patch_text)
    )
    history_counts = _history_target_counts(history_root, exclude_run=resolved_run)
    hotspots = _hotspots(target_paths, history_counts)
    complexity = [_complexity_payload(root, path) for path in target_paths]
    complexity = [item for item in complexity if item]
    score, signals = _entropy_score(
        target_paths=target_paths,
        added_control_flow=added_control_flow,
        added_functions=added_functions,
        hotspots=hotspots,
        complexity=complexity,
    )
    status = _status_for_score(score, signals)
    recommendations = _recommendations(status, signals)
    return {
        "version": "1.0",
        "status": status,
        "entropy_score": score,
        "target_paths": target_paths,
        "added_control_flow_count": added_control_flow,
        "added_functions": added_functions,
        "hotspots": hotspots,
        "complexity": complexity,
        "signals": signals,
        "recommendations": recommendations,
        "recommended_next_action": _recommended_next_action(status),
        "fix_policy": {
            "no_more_localized_fixes_when_refactor_required": status
            in {STATUS_REFACTOR_RECOMMENDED, STATUS_ARCHITECTURE_REVIEW_REQUIRED},
            "require_architect_review_before_retry": status
            in {STATUS_REFACTOR_RECOMMENDED, STATUS_ARCHITECTURE_REVIEW_REQUIRED},
            "prefer_design_refactor_over_if_else_patch": added_control_flow >= 3,
            "preserve_tests_and_contract_gates": True,
            "escalate_when_hotspot_churn_persists": True,
        },
        "safety": {
            "read_only": True,
            "no_shell": True,
            "no_install": True,
            "no_network": True,
            "protected_paths_excluded": True,
        },
    }


def _patch_texts(run_dir: Path) -> list[str]:
    candidates: list[Path] = []
    for pattern in (
        "patches/*.diff",
        "retry_patches/*.diff",
        "*retry_patch*.diff",
        "19_retry_patch_*.diff",
    ):
        candidates.extend(run_dir.glob(pattern))
    texts: list[str] = []
    for path in sorted(_dedupe_paths(candidates))[:MAX_PATCHES_SCANNED]:
        if _has_protected_part(path):
            continue
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return texts


def _target_paths(patch_text: str) -> list[str]:
    paths = [new for _old, new in DIFF_PATH_LINE.findall(patch_text)]
    paths.extend(PATCH_HEADER_LINE.findall(patch_text))
    return [_normalize_patch_path(path) for path in paths if _normalize_patch_path(path)]


def _added_control_flow_count(patch_text: str) -> int:
    return sum(1 for line in patch_text.splitlines() if CONTROL_FLOW_LINE.search(line))


def _history_target_counts(runs_root: Path, *, exclude_run: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not runs_root.exists() or not runs_root.is_dir():
        return counts
    run_dirs = [
        path
        for path in sorted(runs_root.iterdir(), reverse=True)
        if path.is_dir() and path.resolve() != exclude_run
    ][:MAX_HISTORY_RUNS]
    for run_dir in run_dirs:
        summary = _read_json(run_dir / "summary.json")
        for value in _flatten_output_files(summary.get("output_files", {})):
            path = Path(str(value))
            if path.suffix != ".diff" or not path.exists() or _has_protected_part(path):
                continue
            try:
                for target in _target_paths(path.read_text(encoding="utf-8", errors="replace")):
                    counts[target] += 1
            except OSError:
                continue
        for patch_text in _patch_texts(run_dir):
            for target in _target_paths(patch_text):
                counts[target] += 1
    return counts


def _hotspots(target_paths: list[str], history_counts: Counter[str]) -> list[dict[str, Any]]:
    payload = []
    for path in target_paths:
        prior = history_counts.get(path, 0)
        if prior <= 0:
            continue
        payload.append(
            {
                "path": path,
                "prior_patch_count": prior,
                "reason": "Repeated localized patches touched this target in previous runs.",
            }
        )
    payload.sort(key=lambda item: (-int(item["prior_patch_count"]), str(item["path"])))
    return payload[:8]


def _complexity_payload(project_root: Path, relative_path: str) -> dict[str, Any]:
    path = (project_root / relative_path).resolve()
    if _has_protected_part(path) or not path.is_file() or not _is_relative_to(path, project_root):
        return {}
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    lines = source.splitlines()
    payload: dict[str, Any] = {
        "path": relative_path,
        "line_count": len(lines),
        "max_indent": _max_indent(lines),
    }
    if path.suffix == ".py":
        payload.update(_python_complexity(source))
    return payload


def _python_complexity(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"python_parse_failed": True}
    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        functions.append(
            {
                "symbol": node.name,
                "line_count": end - start + 1,
                "branch_count": _branch_count(node),
                "max_nested_depth": _nested_depth(node),
            }
        )
    functions.sort(key=lambda item: (-int(item["branch_count"]), -int(item["line_count"]), str(item["symbol"])))
    return {"largest_functions": functions[:5]}


def _entropy_score(
    *,
    target_paths: list[str],
    added_control_flow: int,
    added_functions: list[str],
    hotspots: list[dict[str, Any]],
    complexity: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if len(target_paths) >= 6:
        score += 16
        signals.append("broad_patch_surface")
    if added_control_flow >= 3:
        score += min(added_control_flow * 8, 32)
        signals.append("control_flow_accretion")
    if len(added_functions) >= 4:
        score += 14
        signals.append("new_function_sprawl")
    for hotspot in hotspots:
        prior = int(hotspot["prior_patch_count"])
        if prior >= 3:
            score += 26
            signals.append("repeated_hotspot_churn")
            break
        if prior >= 1:
            score += 10
            signals.append("hotspot_churn")
            break
    for item in complexity:
        if int(item.get("line_count", 0)) >= 220 or int(item.get("max_indent", 0)) >= 20:
            score += 18
            signals.append("large_or_deep_file")
        for function in item.get("largest_functions", []):
            if int(function.get("line_count", 0)) >= 80 or int(function.get("branch_count", 0)) >= 12:
                score += 24
                signals.append("complex_function_hotspot")
                break
    if "complex_function_hotspot" in signals and added_control_flow > 0:
        score += 20
        signals.append("localized_patch_on_complex_hotspot")
    return min(score, 100), _dedupe(signals)


def _status_for_score(score: int, signals: list[str]) -> str:
    signal_set = set(signals)
    if (
        score >= 70
        or {"complex_function_hotspot", "control_flow_accretion"}.issubset(signal_set)
        or {"complex_function_hotspot", "localized_patch_on_complex_hotspot"}.issubset(signal_set)
        or {"repeated_hotspot_churn", "control_flow_accretion"}.issubset(signal_set)
    ):
        return STATUS_ARCHITECTURE_REVIEW_REQUIRED
    if score >= 45 or "repeated_hotspot_churn" in signals:
        return STATUS_REFACTOR_RECOMMENDED
    if score >= 20:
        return STATUS_ENTROPY_WARNING
    return STATUS_ENTROPY_OK


def _recommendations(status: str, signals: list[str]) -> list[str]:
    if status == STATUS_ENTROPY_OK:
        return ["Continue normal gated patch flow."]
    recommendations = ["Run Architect/Reviewer refactor analysis before more localized fixes."]
    if "control_flow_accretion" in signals:
        recommendations.append("Replace repeated conditionals with a clearer abstraction, policy object, or strategy boundary.")
    if "repeated_hotspot_churn" in signals or "hotspot_churn" in signals:
        recommendations.append("Inspect hotspot history and create a design-level repair instead of another single-function patch.")
    if "complex_function_hotspot" in signals:
        recommendations.append("Split large or high-branch functions behind stable interfaces before adding more edge cases.")
    return recommendations


def _recommended_next_action(status: str) -> str:
    if status in {STATUS_ARCHITECTURE_REVIEW_REQUIRED, STATUS_REFACTOR_RECOMMENDED}:
        return "run_architecture_refactor_review"
    if status == STATUS_ENTROPY_WARNING:
        return "record_entropy_warning_and_continue_guarded"
    return "continue_guarded_patch_flow"


def _infer_project_root(run_dir: Path) -> Path:
    for parent in [run_dir, *run_dir.parents]:
        if (parent / "agentic_network").is_dir() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd().resolve()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _flatten_output_files(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _flatten_output_files(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _flatten_output_files(nested)]
    return []


def _normalize_patch_path(path: str) -> str:
    value = path.strip().replace("\\", "/")
    if value == "/dev/null":
        return ""
    if value.startswith(("a/", "b/")):
        value = value[2:]
    return value.strip("/")


def _branch_count(node: ast.AST) -> int:
    branch_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler, ast.Match, ast.BoolOp, ast.IfExp)
    return sum(1 for child in ast.walk(node) if isinstance(child, branch_nodes))


def _nested_depth(node: ast.AST) -> int:
    branch_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)

    def visit(current: ast.AST, depth: int) -> int:
        next_depth = depth + 1 if isinstance(current, branch_nodes) else depth
        child_depths = [visit(child, next_depth) for child in ast.iter_child_nodes(current)]
        return max([next_depth, *child_depths])

    return visit(node, 0)


def _max_indent(lines: list[str]) -> int:
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    return max(indents, default=0)


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _dedupe(values: list[str] | Any) -> list[str]:
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
