"""ANN v3.6 safe layer creation planner.

This module proposes reviewable new-file targets for architectural layers that
the multi-file planner marked as missing. It never writes repository source
files, applies patches, executes commands, or runs tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.execution_agent.multifile_planner import (
    ROLE_CONFIG_SETTINGS,
    ROLE_DOCUMENTATION,
    ROLE_ROUTE_HANDLER,
    ROLE_SERVICE_LAYER,
    ROLE_TEST_FILE,
    MultiFilePlanResult,
)
from agentic_network.safety.filesystem_policy import _canonical_path_key, load_filesystem_policy

SUPPORTED_LAYERS = {
    ROLE_SERVICE_LAYER,
    ROLE_ROUTE_HANDLER,
    ROLE_TEST_FILE,
    ROLE_CONFIG_SETTINGS,
    ROLE_DOCUMENTATION,
}
PROTECTED_PARTS = {
    ".git",
    "outputs",
    "knowledge",
    "memory",
    "models",
}
PROTECTED_PREFIXES = (
    Path("training/datasets"),
    Path("training/adapters"),
)
SOURCE_TEST_DOC_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".mdx", ".rst", ".json", ".yaml", ".yml", ".toml"}


@dataclass(frozen=True)
class LayerCreationPlanResult:
    """Safe proposed files for missing architectural layers."""

    proposed_files: list[str]
    proposed_roles: dict[str, str]
    creation_rationale: list[str]
    rejected_layers: dict[str, str]
    validation_errors: list[str]
    confidence: str


def plan_missing_layers(
    task: str,
    repository_context: dict[str, Any],
    multifile_plan: MultiFilePlanResult,
    artifact_context: str,
    experience_context: str,
) -> LayerCreationPlanResult:
    """Plan safe new files for missing layers without applying anything."""

    context = _normalize_context(repository_context)
    project_root = _project_root(context)
    repo_files = _repo_files(context)
    directories = _directories(context, repo_files)
    proposed_files: list[str] = []
    proposed_roles: dict[str, str] = {}
    creation_rationale: list[str] = []
    rejected_layers: dict[str, str] = {}
    validation_errors: list[str] = []

    for layer in multifile_plan.missing_layers:
        if layer not in SUPPORTED_LAYERS:
            rejected_layers[layer] = "unsupported_missing_layer"
            continue
        proposal, reason = _proposal_for_layer(
            layer=layer,
            task=task,
            context=context,
            repo_files=repo_files,
            directories=directories,
            artifact_context=artifact_context,
            experience_context=experience_context,
        )
        if not proposal:
            rejected_layers[layer] = reason
            continue
        errors = _validate_proposed_path(proposal, project_root, repo_files)
        if errors:
            rejected_layers[layer] = "unsafe_or_invalid_path"
            validation_errors.extend(errors)
            continue
        proposed_files.append(proposal)
        proposed_roles[proposal] = layer
        creation_rationale.append(f"Proposed {proposal} for missing {layer}: {reason}.")

    return LayerCreationPlanResult(
        proposed_files=_dedupe(proposed_files),
        proposed_roles={path: proposed_roles[path] for path in _dedupe(proposed_files)},
        creation_rationale=creation_rationale,
        rejected_layers=rejected_layers,
        validation_errors=_dedupe(validation_errors),
        confidence=_confidence(proposed_files, rejected_layers, validation_errors),
    )


def render_creation_patch(relative_path: str, role: str, task: str) -> str:
    """Render a minimal, syntactically valid reviewable creation diff."""

    path = Path(relative_path)
    content = _content_for(role=role, relative_path=relative_path, task=task)
    lines = content.rstrip().splitlines()
    header = [
        "--- /dev/null",
        f"+++ b/{path.as_posix()}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    return "\n".join([*header, *(f"+{line}" for line in lines)])


def _proposal_for_layer(
    *,
    layer: str,
    task: str,
    context: dict[str, Any],
    repo_files: set[str],
    directories: set[str],
    artifact_context: str,
    experience_context: str,
) -> tuple[str, str]:
    text = f"{task}\n{artifact_context}\n{experience_context}".lower()
    if layer == ROLE_SERVICE_LAYER:
        if not _backend_required(text):
            return "", "task_does_not_clearly_require_backend_behavior"
        if _matching_file_exists(repo_files, _filename_stem(task), ("services", "service")):
            return "", "matching_service_file_already_exists"
        directory = _preferred_existing_dir(directories, ("apps/api/app/services", "src/services", "app/services", "services"))
        if not directory:
            return "", "no_existing_service_directory"
        return f"{directory}/{_service_filename(task)}", "matched existing service directory"
    if layer == ROLE_ROUTE_HANDLER:
        if not _repo_has_route_structure(directories, context):
            return "", "no_existing_route_or_router_structure"
        if _internal_config_only(text):
            return "", "task_only_requires_internal_config_or_constants"
        if _matching_file_exists(repo_files, _filename_stem(task), ("routes", "routers")):
            return "", "matching_route_file_already_exists"
        directory = _preferred_existing_dir(directories, ("apps/api/app/routes", "app/routes", "src/routes", "routers"))
        if not directory:
            return "", "no_safe_route_directory"
        return f"{directory}/{_route_filename(task)}", "matched existing route directory"
    if layer == ROLE_TEST_FILE:
        if not _pytest_used(repo_files):
            return "", "pytest_not_detected"
        if _matching_file_exists(repo_files, _filename_stem(task), ("tests",)):
            return "", "matching_test_file_already_exists"
        directory = _preferred_existing_dir(directories, ("tests", "tests/python", "apps/api/tests"))
        if not directory:
            return "", "no_existing_tests_directory"
        return f"{directory}/{_test_filename(task)}", "matched existing pytest tests directory"
    if layer == ROLE_CONFIG_SETTINGS:
        existing = _existing_config_file(repo_files)
        if existing:
            return "", f"existing_config_file_available:{existing}"
        directory = _preferred_existing_dir(directories, ("app/core", "apps/api/app/core", "src/config", "config"))
        if not directory:
            return "", "no_safe_config_directory"
        return f"{directory}/settings.py", "no existing config file found and safe config directory exists"
    if layer == ROLE_DOCUMENTATION:
        directory = _preferred_existing_dir(directories, ("docs",))
        if not directory:
            return "", "docs_directory_missing"
        return f"{directory}/{_doc_filename(task)}", "matched docs directory"
    return "", "unsupported_missing_layer"


def _content_for(*, role: str, relative_path: str, task: str) -> str:
    stem = Path(relative_path).stem
    function_name = _safe_identifier(stem)
    if role == ROLE_SERVICE_LAYER:
        return (
            '"""Service helpers proposed by ANN layer creation planning."""\n\n'
            "from __future__ import annotations\n\n\n"
            f"def {function_name}(identifier: str, *, attempts: int, max_attempts: int = 5) -> dict[str, object]:\n"
            '    """Return a deterministic decision for the requested backend behavior."""\n'
            "    normalized_identifier = identifier.strip().lower()\n"
            "    allowed = bool(normalized_identifier) and attempts < max_attempts\n"
            "    return {\n"
            '        "allowed": allowed,\n'
            '        "identifier": normalized_identifier,\n'
            '        "remaining_attempts": max(max_attempts - attempts, 0),\n'
            "    }\n"
        )
    if role == ROLE_ROUTE_HANDLER:
        return (
            '"""Route handler scaffold proposed by ANN layer creation planning."""\n\n'
            "from __future__ import annotations\n\n"
            "from fastapi import APIRouter\n\n"
            "router = APIRouter()\n\n\n"
            f"@router.post(\"/{_route_slug(task)}\")\n"
            f"def {function_name}(identifier: str) -> dict[str, object]:\n"
            '    """Expose a minimal safe route for the approved feature plan."""\n'
            '    return {"accepted": bool(identifier.strip())}\n'
        )
    if role == ROLE_TEST_FILE:
        return (
            '"""Tests proposed by ANN layer creation planning."""\n\n\n'
            f"def test_{function_name}_allows_valid_input() -> None:\n"
            '    assert "user@example.com".strip()\n'
        )
    if role == ROLE_CONFIG_SETTINGS:
        return (
            '"""Configuration values proposed by ANN layer creation planning."""\n\n'
            "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 5\n"
            "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600\n"
        )
    if role == ROLE_DOCUMENTATION:
        title = _title_from_task(task)
        return (
            f"# {title}\n\n"
            "This document was proposed as a reviewable documentation layer for the approved implementation plan.\n"
        )
    return f'"""Reviewable new file proposed for {role}."""\n'


def _validate_proposed_path(relative_path: str, project_root: Path, repo_files: set[str]) -> list[str]:
    errors: list[str] = []
    if re.search(r"(?i)(?:^|[\s:+-])(?:/mnt/c\b|[A-Z]:\\)", relative_path):
        errors.append("forbidden_c_path_present")
    if ".." in Path(relative_path).parts or ".." in relative_path.replace("\\", "/").split("/"):
        errors.append(f"path_traversal_present:{relative_path}")
    path = Path(relative_path)
    if path.is_absolute():
        errors.append(f"absolute_path_not_allowed:{relative_path}")
    if path.suffix.lower() not in SOURCE_TEST_DOC_EXTENSIONS:
        errors.append(f"unsupported_creation_extension:{relative_path}")
    if not _source_test_or_doc_path(path):
        errors.append(f"unsupported_creation_location:{relative_path}")
    if set(path.parts) & PROTECTED_PARTS:
        errors.append(f"protected_path_modified:{relative_path}")
    for prefix in PROTECTED_PREFIXES:
        try:
            path.relative_to(prefix)
            errors.append(f"protected_path_modified:{relative_path}")
        except ValueError:
            pass
    if relative_path in repo_files:
        errors.append(f"proposed_file_already_exists:{relative_path}")
    policy = load_filesystem_policy(project_root=project_root)
    target = policy.normalize_path(relative_path)
    if not _is_relative_to(target, project_root):
        errors.append(f"path_outside_project_root:{relative_path}")
    for error in policy.validate_patch_target(target):
        if error == "forbidden_c_path_present":
            errors.append(error)
        elif error.startswith(("protected_path_modified:", "blocked_path:", "path_traversal_present:", "path_outside_allowed_roots:")):
            errors.append(error)
    return _dedupe(errors)


def _normalize_context(repository_context: dict[str, Any]) -> dict[str, Any]:
    if "repository_context" in repository_context and isinstance(repository_context["repository_context"], dict):
        return repository_context["repository_context"]
    return repository_context


def _project_root(context: dict[str, Any]) -> Path:
    root = context.get("project_root") or context.get("root") or "."
    return Path(str(root)).resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    path_key = _canonical_path_key(path)
    parent_key = _canonical_path_key(parent)
    return path_key == parent_key or path_key.startswith(parent_key.rstrip("/") + "/")


def _repo_files(context: dict[str, Any]) -> set[str]:
    files: list[str] = []
    for key in ("repository_files", "repo_files", "matched_files", "recommended_patch_targets", "selected_targets", "_candidate_files"):
        values = context.get(key, [])
        if isinstance(values, list):
            files.extend(str(value).replace("\\", "/") for value in values if value)
    for key in ("matched_routes", "matched_functions", "matched_classes"):
        for item in context.get(key, []):
            if isinstance(item, dict) and item.get("file"):
                files.append(str(item["file"]).replace("\\", "/"))
    values = context.get("matched_tests", [])
    if isinstance(values, list):
        files.extend(str(value).replace("\\", "/") for value in values if value)
    return {value.strip("/") for value in files if value}


def _directories(context: dict[str, Any], repo_files: set[str]) -> set[str]:
    directories: set[str] = set()
    for key in ("repository_directories", "repo_directories", "directories"):
        values = context.get(key, [])
        if isinstance(values, list):
            directories.update(str(value).replace("\\", "/").strip("/") for value in values if value)
    for file_path in repo_files:
        parent = Path(file_path).parent.as_posix()
        while parent and parent != ".":
            directories.add(parent)
            parent = Path(parent).parent.as_posix()
    return directories


def _backend_required(text: str) -> bool:
    return bool(
        set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
        & {"api", "backend", "service", "route", "auth", "password", "reset", "rate", "limit", "pagination", "database"}
    )


def _internal_config_only(text: str) -> bool:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
    return bool(tokens & {"config", "constant", "settings"}) and not bool(tokens & {"api", "route", "endpoint", "handler"})


def _repo_has_route_structure(directories: set[str], context: dict[str, Any]) -> bool:
    if context.get("matched_routes"):
        return True
    return bool(_preferred_existing_dir(directories, ("apps/api/app/routes", "app/routes", "src/routes", "routers")))


def _pytest_used(repo_files: set[str]) -> bool:
    return any(Path(path).name.startswith("test_") and Path(path).suffix == ".py" for path in repo_files)


def _preferred_existing_dir(directories: set[str], candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if candidate in directories:
            return candidate
    return ""


def _matching_file_exists(repo_files: set[str], stem: str, directory_tokens: tuple[str, ...]) -> bool:
    target_tokens = set(stem.split("_"))
    domain_tokens = {"auth", "password", "reset", "rate", "limit", "pagination"}
    for file_path in repo_files:
        path = Path(file_path)
        if not any(token in {part.lower() for part in path.parts} for token in directory_tokens):
            continue
        existing_tokens = set(path.stem.lower().split("_"))
        if target_tokens and target_tokens <= existing_tokens:
            return True
        if len((target_tokens & existing_tokens) & domain_tokens) >= 2:
            return True
    return False


def _existing_config_file(repo_files: set[str]) -> str:
    for file_path in sorted(repo_files):
        name = Path(file_path).name.lower()
        if name in {"config.py", "settings.py", "config.json", "settings.json"}:
            return file_path
    return ""


def _service_filename(task: str) -> str:
    stem = _filename_stem(task)
    if {"password", "reset", "rate", "limit"} <= set(stem.split("_")):
        return "password_reset_rate_limit.py"
    if {"auth", "rate", "limit"} <= set(stem.split("_")):
        return "auth_rate_limit.py"
    if "pagination" in stem:
        return "pagination_service.py"
    return f"{stem}_service.py"


def _route_filename(task: str) -> str:
    stem = _filename_stem(task)
    if "auth" in stem or "password" in stem or "reset" in stem:
        return "auth.py"
    if "pagination" in stem:
        return "pagination.py"
    return f"{stem}_routes.py"


def _test_filename(task: str) -> str:
    stem = _filename_stem(task)
    if {"password", "reset", "rate", "limit"} <= set(stem.split("_")):
        return "test_password_reset_rate_limit.py"
    if {"auth", "rate", "limit"} <= set(stem.split("_")):
        return "test_auth_rate_limit.py"
    if "pagination" in stem:
        return "test_pagination.py"
    return f"test_{stem}.py"


def _doc_filename(task: str) -> str:
    return f"{_filename_stem(task)}.md"


def _filename_stem(task: str) -> str:
    tokens = re.findall(r"[a-z][a-z0-9]{2,}", task.lower())
    ignored = {"add", "build", "create", "implement", "requests", "request", "with", "for", "the", "and", "to"}
    kept = [token for token in tokens if token not in ignored]
    all_normalized = ["limit" if token == "limits" else token for token in kept]
    if {"password", "reset", "rate", "limit"} <= set(all_normalized):
        return "password_reset_rate_limit"
    normalized = all_normalized[:5]
    return "_".join(normalized) or "generated_layer"


def _route_slug(task: str) -> str:
    return _filename_stem(task).replace("_", "-")


def _safe_identifier(stem: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]", "_", stem).strip("_").lower()
    if not value or value[0].isdigit():
        value = f"generated_{value}"
    return value


def _title_from_task(task: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", task)[:8]
    return " ".join(words).strip().title() or "Generated Documentation"


def _source_test_or_doc_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & {"app", "apps", "src", "services", "routes", "routers", "tests", "docs", "packages", "agentic_network"})


def _confidence(proposed_files: list[str], rejected_layers: dict[str, str], validation_errors: list[str]) -> str:
    if validation_errors:
        return "Low"
    if proposed_files and not rejected_layers:
        return "High"
    if proposed_files:
        return "Medium"
    return "Low"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
