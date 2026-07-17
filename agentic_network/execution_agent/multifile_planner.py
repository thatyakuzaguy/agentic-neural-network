"""ANN v3.5 multi-file implementation planner.

The planner is intentionally patch-only: it decides which existing files should be patched
together, but it never writes repository source files, applies diffs, executes code, or runs tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLAN_RATE_LIMITING = "RATE_LIMITING_FEATURE"
PLAN_PAGINATION = "PAGINATION_FEATURE"
PLAN_AUTH_GUARD = "AUTH_GUARD_FEATURE"
PLAN_DOCUMENTATION_ONLY = "DOCUMENTATION_ONLY"
PLAN_UNKNOWN = "UNKNOWN_FEATURE"

ROLE_CONFIG_SETTINGS = "CONFIG_SETTINGS"
ROLE_SERVICE_LAYER = "SERVICE_LAYER"
ROLE_ROUTE_HANDLER = "ROUTE_HANDLER"
ROLE_TEST_FILE = "TEST_FILE"
ROLE_MIDDLEWARE = "MIDDLEWARE"
ROLE_UI_COMPONENT = "UI_COMPONENT"
ROLE_DOCUMENTATION = "DOCUMENTATION"
ROLE_FILES_TO_CREATE = "FILES_TO_CREATE"
ROLE_UNKNOWN = "UNKNOWN"

PLAN_ROLE_ORDER = {
    PLAN_RATE_LIMITING: [
        ROLE_CONFIG_SETTINGS,
        ROLE_SERVICE_LAYER,
        ROLE_ROUTE_HANDLER,
        ROLE_TEST_FILE,
        ROLE_MIDDLEWARE,
    ],
    PLAN_PAGINATION: [
        ROLE_ROUTE_HANDLER,
        ROLE_SERVICE_LAYER,
        ROLE_TEST_FILE,
        ROLE_UI_COMPONENT,
    ],
    PLAN_AUTH_GUARD: [
        ROLE_SERVICE_LAYER,
        ROLE_ROUTE_HANDLER,
        ROLE_MIDDLEWARE,
        ROLE_TEST_FILE,
    ],
    PLAN_DOCUMENTATION_ONLY: [ROLE_DOCUMENTATION],
    PLAN_UNKNOWN: [
        ROLE_SERVICE_LAYER,
        ROLE_ROUTE_HANDLER,
        ROLE_CONFIG_SETTINGS,
        ROLE_TEST_FILE,
        ROLE_DOCUMENTATION,
        ROLE_UNKNOWN,
    ],
}

REQUIRED_ROLES = {
    PLAN_RATE_LIMITING: [ROLE_CONFIG_SETTINGS, ROLE_SERVICE_LAYER, ROLE_ROUTE_HANDLER, ROLE_TEST_FILE],
    PLAN_PAGINATION: [ROLE_ROUTE_HANDLER, ROLE_SERVICE_LAYER, ROLE_TEST_FILE],
    PLAN_AUTH_GUARD: [ROLE_SERVICE_LAYER, ROLE_ROUTE_HANDLER, ROLE_MIDDLEWARE, ROLE_TEST_FILE],
    PLAN_DOCUMENTATION_ONLY: [ROLE_DOCUMENTATION],
    PLAN_UNKNOWN: [],
}


@dataclass(frozen=True)
class MultiFilePlanResult:
    """Coordinated implementation plan for the Execution Agent."""

    plan_type: str
    selected_files: list[str]
    file_roles: dict[str, str]
    implementation_order: list[str]
    rationale: list[str]
    missing_layers: list[str]
    confidence: str


def plan_multifile_implementation(
    task: str,
    repository_context: dict[str, Any],
    artifact_context: str,
    experience_context: str,
    max_files: int = 5,
) -> MultiFilePlanResult:
    """Plan a coordinated set of files for a feature implementation patch."""

    plan_type = _plan_type(task, artifact_context)
    context = _normalize_context(repository_context)
    explicit_ui = _mentions_ui(task)
    candidate_paths = _candidate_paths(context)
    role_candidates: dict[str, list[str]] = {}
    route_files = _route_files(context)

    for path in candidate_paths:
        role = classify_multifile_role(path, route_files=route_files)
        if role == ROLE_UI_COMPONENT and not explicit_ui:
            continue
        if role == ROLE_MIDDLEWARE and not _middleware_allowed(plan_type, task, path, context):
            continue
        if role == ROLE_UNKNOWN and plan_type != PLAN_UNKNOWN:
            continue
        score = _score_path(path, role, plan_type, task, artifact_context, experience_context, context)
        role_candidates.setdefault(role, []).append(f"{score:04d}:{path}")

    selected_files: list[str] = []
    file_roles: dict[str, str] = {}
    rationale: list[str] = []
    for role in PLAN_ROLE_ORDER[plan_type]:
        ranked = sorted(role_candidates.get(role, []), reverse=True)
        if not ranked:
            continue
        path = ranked[0].split(":", 1)[1]
        if path in selected_files:
            continue
        selected_files.append(path)
        file_roles[path] = role
        rationale.append(f"Selected {path} as {role} for {plan_type}.")
        if len(selected_files) >= max_files:
            break

    if plan_type == PLAN_UNKNOWN and len(selected_files) < max_files:
        for path in candidate_paths:
            if path in selected_files:
                continue
            role = classify_multifile_role(path, route_files=route_files)
            if role == ROLE_UI_COMPONENT and not explicit_ui:
                continue
            selected_files.append(path)
            file_roles[path] = role
            rationale.append(f"Selected fallback target {path} as {role}.")
            if len(selected_files) >= max_files:
                break

    missing_layers = [
        role
        for role in REQUIRED_ROLES[plan_type]
        if role not in set(file_roles.values())
    ]
    implementation_order = [
        path
        for role in PLAN_ROLE_ORDER[plan_type]
        for path in selected_files
        if file_roles.get(path) == role
    ]
    confidence = _confidence(plan_type, selected_files, missing_layers)
    if missing_layers:
        rationale.append("Missing required layers were recorded instead of inventing unsafe targets.")
    if plan_type == PLAN_DOCUMENTATION_ONLY:
        rationale.append("Task appears documentation-only; selected markdown documentation targets.")

    return MultiFilePlanResult(
        plan_type=plan_type,
        selected_files=selected_files,
        file_roles=file_roles,
        implementation_order=implementation_order,
        rationale=rationale,
        missing_layers=missing_layers,
        confidence=confidence,
    )


def classify_multifile_role(path_text: str, *, route_files: set[str] | None = None) -> str:
    """Classify a repository-relative file path into a multi-file implementation role."""

    path = Path(path_text)
    lowered = path_text.lower()
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    suffix = path.suffix.lower()
    if path_text in (route_files or set()):
        return ROLE_ROUTE_HANDLER
    if suffix in {".md", ".mdx", ".rst"} or parts & {"docs", "documentation"}:
        return ROLE_DOCUMENTATION
    if path_text.startswith("tests/") or "/tests/" in path_text or name.startswith("test_") or name.endswith("_test.py"):
        return ROLE_TEST_FILE
    if suffix in {".tsx", ".jsx"} or parts & {"ui", "frontend", "components", "pages", "views", "templates", "static"}:
        return ROLE_UI_COMPONENT
    if name in {"config.py", "settings.py", "config.json", "settings.json"} or parts & {"config", "settings"}:
        return ROLE_CONFIG_SETTINGS
    if "middleware" in lowered or "middlewares" in parts:
        return ROLE_MIDDLEWARE
    if parts & {"routes", "routers", "router", "api", "controllers", "endpoints"} or name in {"routes.py", "router.py", "views.py"}:
        return ROLE_ROUTE_HANDLER
    if parts & {"services", "service", "domain", "use_cases", "usecases", "core", "auth"} or any(
        token in lowered for token in ("service", "password_reset", "reset_service", "auth_guard", "account_recovery")
    ):
        return ROLE_SERVICE_LAYER
    return ROLE_UNKNOWN


def _plan_type(task: str, artifact_context: str) -> str:
    text = f"{task}\n{artifact_context}".lower()
    if _documentation_only(text):
        return PLAN_DOCUMENTATION_ONLY
    if any(token in text for token in ("auth guard", "authorization guard", "permission guard", "rbac guard", "require permission")):
        return PLAN_AUTH_GUARD
    if any(token in text for token in ("rate limit", "rate-limit", "ratelimit", "throttle", "password reset", "account recovery")):
        return PLAN_RATE_LIMITING
    if any(token in text for token in ("pagination", "paginate", "page size", "cursor", "product search")):
        return PLAN_PAGINATION
    return PLAN_UNKNOWN


def _documentation_only(text: str) -> bool:
    doc_words = {"document", "documentation", "readme", "docs", "guide"}
    implementation_words = {"implement", "add", "build", "code", "route", "service", "test"}
    tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
    return bool(tokens & doc_words) and not bool(tokens & implementation_words)


def _normalize_context(repository_context: dict[str, Any]) -> dict[str, Any]:
    if "repository_context" in repository_context and isinstance(repository_context["repository_context"], dict):
        return repository_context["repository_context"]
    return repository_context


def _candidate_paths(context: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in (
        "recommended_patch_targets",
        "selected_targets",
        "matched_files",
        "dependency_paths",
        "matched_tests",
        "_candidate_files",
    ):
        values = context.get(key, [])
        if isinstance(values, list):
            candidates.extend(str(value) for value in values if value)
    for route in context.get("matched_routes", []):
        if isinstance(route, dict) and route.get("file"):
            candidates.append(str(route["file"]))
    for key in ("matched_functions", "matched_classes"):
        for item in context.get(key, []):
            if isinstance(item, dict) and item.get("file"):
                candidates.append(str(item["file"]))
    return _dedupe(candidates)


def _route_files(context: dict[str, Any]) -> set[str]:
    return {
        str(route.get("file", ""))
        for route in context.get("matched_routes", [])
        if isinstance(route, dict) and route.get("file")
    }


def _mentions_ui(task: str) -> bool:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{1,}", task.lower()))
    return bool(tokens & {"ui", "frontend", "interface", "component", "screen", "page", "button"})


def _middleware_allowed(plan_type: str, task: str, path: str, context: dict[str, Any]) -> bool:
    lowered_task = task.lower()
    if "middleware" in lowered_task:
        return True
    if plan_type == PLAN_AUTH_GUARD:
        return True
    lowered_path = path.lower()
    return any(str(dep).lower() == lowered_path for dep in context.get("dependency_paths", []))


def _score_path(
    path: str,
    role: str,
    plan_type: str,
    task: str,
    artifact_context: str,
    experience_context: str,
    context: dict[str, Any],
) -> int:
    score = 100 - PLAN_ROLE_ORDER[plan_type].index(role) * 10 if role in PLAN_ROLE_ORDER[plan_type] else 10
    haystack = f"{task}\n{artifact_context}\n{experience_context}".lower()
    path_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", path.lower()))
    text_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", haystack))
    score += min(30, 5 * len(path_tokens & text_tokens))
    if path in [str(value) for value in context.get("recommended_patch_targets", [])]:
        score += 20
    if path in [str(value) for value in context.get("selected_targets", [])]:
        score += 15
    if role == ROLE_TEST_FILE and ("test" in path.lower() or "tests" in path.lower()):
        score += 8
    if role == ROLE_CONFIG_SETTINGS and plan_type == PLAN_RATE_LIMITING:
        score += 12
    if "auth" in path.lower() and plan_type in {PLAN_RATE_LIMITING, PLAN_AUTH_GUARD}:
        score += 12
    if "product" in path.lower() and plan_type == PLAN_PAGINATION:
        score += 12
    return score


def _confidence(plan_type: str, selected_files: list[str], missing_layers: list[str]) -> str:
    if not selected_files:
        return "Low"
    if plan_type == PLAN_UNKNOWN:
        return "Medium"
    if not missing_layers:
        return "High"
    return "Medium" if len(selected_files) >= 2 else "Low"


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
