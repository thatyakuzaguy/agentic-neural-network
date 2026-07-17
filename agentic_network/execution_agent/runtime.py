"""Patch-only Execution Agent runtime."""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from agentic_network.execution_agent.synthesizer import (
    REAL_IMPLEMENTATION_STRATEGIES,
    STRATEGY_FALLBACK_SOURCE_AWARE,
    SynthesizedPatchResult,
    synthesize_patch,
)
from agentic_network.execution_agent.multifile_planner import (
    plan_multifile_implementation,
)
from agentic_network.execution_agent.layer_creation_planner import (
    LayerCreationPlanResult,
    plan_missing_layers,
    render_creation_patch,
)
from agentic_network.safety.filesystem_policy import _canonical_path_key, load_filesystem_policy

EXECUTION_PLAN_OUTPUT_FILE = "11_execution_plan.md"
PATCHES_DIR = "patches"
STATUS_NO_APPLICABLE_TARGETS = "NO_APPLICABLE_TARGETS"
STATUS_VALID_WITHOUT_PATCHES = "VALID_WITHOUT_PATCHES"

SOURCE_FILES = {
    "user": ("00_user_request.md",),
    "experience": ("24_experience_context.md",),
    "code": ("03_code_revised.md", "03_code.md"),
    "tests": ("04_tests_revised.md", "04_tests.md"),
    "security": ("05_security_revised.md", "05_security.md"),
    "final": ("08_final_review.md",),
}
SECTION_KEYS = {
    "EXECUTION SUMMARY": "execution_summary",
    "FILES TO MODIFY": "files_to_modify",
    "FILES TO CREATE": "files_to_create",
    "FILES TO REVIEW": "files_to_review",
    "PATCH STRATEGY": "patch_strategy",
    "EXPECTED TEST IMPACT": "expected_test_impact",
    "SECURITY CONSIDERATIONS": "security_considerations",
    "EXECUTION CONFIDENCE": "execution_confidence",
}
REQUIRED_SECTIONS = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in REQUIRED_SECTIONS) + r")\s*$",
    re.IGNORECASE,
)
GENERIC_SECTION_LINE = re.compile(r"^\s*([A-Z][A-Z0-9 /_-]{2,})\s*$")
BULLET_LINE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
NUMBERED_LIST_LINE = re.compile(r"^\s*\d+[\.)]\s+(.+?)\s*$")
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s|\+)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|python\s+-m\s+pytest\b|(?<!import\s)pytest\b|npm\s+|yarn\s+|"
    r"curl\b|wget\b|git\s+apply\b|apply_patch\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\(|shell\s*=\s*True)"
)
SHELL_SCRIPT_PATTERN = re.compile(r"(?m)^\s*#!\s*/(?:usr/bin/env\s+)?(?:bash|sh|zsh|powershell|pwsh)\b")
WINDOWS_C_PATH_PATTERN = re.compile(r"(?i)(?:^|\s)(?:/mnt/c\b|[A-Z]:\\)")
ABSOLUTE_MOUNT_PATH_PATTERN = re.compile(r"(?<!\w)(/mnt/[a-zA-Z]/[^\s)\]]+)")
PATH_LIKE_TOKEN = re.compile(r"(?<![\w.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)")

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".toml", ".yaml", ".yml"}
TARGET_ROUTE_HANDLER = "ROUTE_HANDLER"
TARGET_SERVICE_LAYER = "SERVICE_LAYER"
TARGET_CONFIG_SETTINGS = "CONFIG_SETTINGS"
TARGET_MIDDLEWARE = "MIDDLEWARE"
TARGET_UI_COMPONENT = "UI_COMPONENT"
TARGET_TEST_FILE = "TEST_FILE"
TARGET_UNKNOWN = "UNKNOWN"
TARGET_CLASSES = {
    TARGET_ROUTE_HANDLER,
    TARGET_SERVICE_LAYER,
    TARGET_CONFIG_SETTINGS,
    TARGET_MIDDLEWARE,
    TARGET_UI_COMPONENT,
    TARGET_TEST_FILE,
    TARGET_UNKNOWN,
}
EXCLUDED_DIR_PARTS = {
    ".git",
    "outputs",
    "knowledge",
    "memory",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "data",
    "results",
    "migration-backups",
    "unsloth_compiled_cache",
    ".mypy_cache",
    ".ms-playwright",
    ".ruff_cache",
    ".venv-qlora",
    "docker",
    "generated-projects",
    "logs",
    "models",
    "releases",
}
EXCLUDED_PREFIXES = (Path("training/datasets"), Path("training/adapters"))
GENERIC_HINT_WORDS = {
    "api",
    "app",
    "auth",
    "config",
    "handler",
    "limit",
    "login",
    "password",
    "product",
    "rate",
    "reset",
    "route",
    "search",
    "service",
    "test",
    "throttle",
}
KEYWORD_GROUPS = {
    "password": ("auth", "password", "reset", "login", "account", "user"),
    "reset": ("auth", "password", "reset", "login", "account", "user"),
    "auth": ("auth", "password", "reset", "login", "account", "user"),
    "login": ("auth", "password", "reset", "login", "account", "user"),
    "rate": ("rate", "limit", "throttle", "auth", "quota"),
    "limit": ("rate", "limit", "throttle", "auth", "quota"),
    "throttle": ("rate", "limit", "throttle", "auth", "quota"),
    "product": ("product", "search", "pagination", "catalog"),
    "search": ("product", "search", "pagination", "query"),
    "pagination": ("product", "search", "pagination", "page"),
    "sms": ("sms", "notification", "message", "phone"),
    "notification": ("sms", "notification", "message", "email"),
}


@dataclass(frozen=True)
class TargetSelectionResult:
    """Repository-context target selection with architectural ranking metadata."""

    selected_targets: list[str]
    rejected_targets: list[str]
    target_classes: dict[str, str]
    target_selection_reasons: dict[str, str]
    confidence: str


@dataclass(frozen=True)
class ExecutionPlanResult:
    """Metadata and generated content for an approved patch proposal run."""

    run_dir: str
    final_decision: str
    execution_plan: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    artifact_path: str
    patch_paths: list[str]
    refused: bool
    source_aware: bool = True
    applicable_patch_count: int = 0
    no_target_reason: str = ""
    candidate_files: list[str] | None = None
    synthesizer_used: bool = False
    synthesizer_strategy: str = ""
    synthesizer_fallback_reason: str = ""
    memory_used: bool = False
    memory_patterns_used: list[str] | None = None
    behavior_synthesized: bool = False
    behavior_strategy: str = ""
    real_implementation: bool = False
    repository_intelligence_used: bool = False
    route_detected: bool = False
    dependency_path_found: bool = False
    repository_context_used: bool = False
    repository_context_files: int = 0
    repository_context_routes: int = 0
    repository_context_functions: int = 0
    repository_context_tests: int = 0
    repository_context_chars: int = 0
    target_selection_used: bool = False
    selected_targets: list[str] | None = None
    rejected_targets: list[str] | None = None
    target_classes: dict[str, str] | None = None
    target_selection_reasons: dict[str, str] | None = None
    target_selection_confidence: str = ""
    multifile_plan_used: bool = False
    multifile_plan_type: str = ""
    multifile_selected_files: list[str] | None = None
    multifile_file_roles: dict[str, str] | None = None
    multifile_implementation_order: list[str] | None = None
    multifile_missing_layers: list[str] | None = None
    multifile_confidence: str = ""
    multifile_rationale: list[str] | None = None
    layer_creation_used: bool = False
    layer_proposed_files: list[str] | None = None
    layer_rejected_layers: dict[str, str] | None = None
    layer_creation_rationale: list[str] | None = None
    layer_creation_validation_errors: list[str] | None = None
    layer_creation_confidence: str = ""

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors

    @property
    def patch_count(self) -> int:
        return len(self.patch_paths)


def generate_execution_plan(run_dir: Path) -> ExecutionPlanResult:
    """Generate source-aware execution plan and patch proposal files for an approved ANN run."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    sources = _load_sources(resolved_run_dir, warnings)
    final_decision = _extract_final_decision(sources.get("final", ""))
    patches_dir = resolved_run_dir / PATCHES_DIR
    artifact_path = resolved_run_dir / EXECUTION_PLAN_OUTPUT_FILE

    if final_decision != "Approved":
        execution_plan = _render_refusal(final_decision)
        parsed_sections = parse_execution_plan_sections(execution_plan)
        validation_errors = validate_execution_plan(
            execution_plan=execution_plan,
            parsed_sections=parsed_sections,
            patch_texts=[],
            project_root=_project_root(),
        )
        validation_errors.append("final_decision_not_approved")
        artifact_path.write_text(execution_plan.rstrip() + "\n", encoding="utf-8")
        return ExecutionPlanResult(
            run_dir=str(resolved_run_dir),
            final_decision=final_decision or "Unknown",
            execution_plan=execution_plan,
            parsed_sections=parsed_sections,
            warnings=warnings,
            validation_errors=_dedupe(validation_errors),
            artifact_path=str(artifact_path),
            patch_paths=[],
            refused=True,
            source_aware=True,
            applicable_patch_count=0,
            no_target_reason="final_decision_not_approved",
            candidate_files=[],
            synthesizer_used=False,
            synthesizer_strategy="",
            synthesizer_fallback_reason="",
        )

    code_sections = _extract_sections(sources.get("code", ""))
    test_sections = _extract_sections(sources.get("tests", ""))
    security_sections = _extract_sections(sources.get("security", ""))
    files_to_modify = _candidate_items(code_sections.get("FILES TO MODIFY", []))
    files_to_create = _candidate_items(code_sections.get("NEW FILES", []))
    code_changes = _candidate_items(code_sections.get("CODE CHANGES", []))
    test_items = _candidate_items(
        code_sections.get("TESTS TO ADD", [])
        + test_sections.get("TEST SCENARIOS", [])
        + test_sections.get("TEST CASES", [])
    )
    security_items = _candidate_items(
        security_sections.get("SECURITY FINDINGS", [])
        + security_sections.get("MITIGATIONS", [])
        + security_sections.get("RESIDUAL RISKS", [])
    )
    project_root = _project_root()
    repo_files = _scan_repository_files(project_root)
    artifact_context = "\n".join(sources.values())
    repository_context = _load_repository_context(resolved_run_dir, warnings)
    repository_intelligence = repository_context or _load_repository_intelligence(resolved_run_dir, warnings)
    raw_candidate_files = _select_candidate_files(
        repo_files=repo_files,
        artifact_text=artifact_context,
        files_to_modify=files_to_modify,
        files_to_create=files_to_create,
        repository_intelligence=repository_intelligence,
        max_candidates=12,
    )
    selection_context = _repository_context_payload(repository_context)
    if selection_context:
        selection_context = {
            **selection_context,
            "_candidate_files": raw_candidate_files,
        }
    target_selection = select_patch_targets_from_repository_context(
        task=sources.get("user", "") or artifact_context,
        repository_context=selection_context,
        artifact_context=artifact_context,
        max_targets=5,
    )
    experience_context = sources.get("experience", "")
    multifile_plan = plan_multifile_implementation(
        task=sources.get("user", "") or artifact_context,
        repository_context={
            **selection_context,
            "project_root": str(project_root),
            "repository_files": repo_files,
            "repository_directories": _repository_directories(repo_files, project_root),
            "selected_targets": target_selection.selected_targets,
            "rejected_targets": target_selection.rejected_targets,
            "target_classes": target_selection.target_classes,
        },
        artifact_context=artifact_context,
        experience_context=experience_context,
        max_files=5,
    )
    layer_creation_plan = _plan_layer_creations(
        task=sources.get("user", "") or artifact_context,
        repository_context={
            **selection_context,
            "project_root": str(project_root),
            "repository_files": repo_files,
            "repository_directories": _repository_directories(repo_files, project_root),
            "selected_targets": target_selection.selected_targets,
            "rejected_targets": target_selection.rejected_targets,
            "target_classes": target_selection.target_classes,
        },
        multifile_plan=multifile_plan,
        artifact_context=artifact_context,
        experience_context=experience_context,
    )
    candidate_files = (
        multifile_plan.implementation_order
        or target_selection.selected_targets
        or raw_candidate_files[:3]
    )
    memory_patterns_used = _memory_patterns_used(experience_context)
    memory_used = _memory_context_has_matches(experience_context, memory_patterns_used)
    no_target_reason = "" if candidate_files else "no_safe_repository_target_matched_artifacts"
    files_to_review = candidate_files or _dedupe(files_to_modify + files_to_create) or [
        "Candidate: approved implementation targets from revised artifacts."
    ]

    execution_plan = _render_execution_plan(
        files_to_modify=candidate_files or files_to_modify or ["Candidate: approved implementation target file."],
        files_to_create=layer_creation_plan.proposed_files or files_to_create or ["None"],
        files_to_review=files_to_review,
        code_changes=code_changes or ["Implement the approved revised code plan in the smallest reviewable change."],
        test_items=test_items or ["Review behavior-level tests described in the revised test artifact."],
        security_items=security_items or ["Preserve security mitigations described in the revised security artifact."],
        no_target_reason=no_target_reason,
    )
    patch_texts, synthesis_results = _render_patch_texts(
        candidate_files=candidate_files,
        code_changes=code_changes,
        test_items=test_items,
        security_items=security_items,
        project_root=project_root,
        artifact_context=artifact_context,
        layer_creation_plan=layer_creation_plan,
        task=sources.get("user", "") or artifact_context,
    )
    synthesizer_used = any(
        result.success and result.strategy != STRATEGY_FALLBACK_SOURCE_AWARE
        for result in synthesis_results
    )
    synthesizer_strategy = _synthesis_strategy(synthesis_results)
    synthesizer_fallback_reason = _synthesis_fallback_reason(synthesis_results)
    behavior_strategy = _behavior_strategy(synthesis_results)
    behavior_synthesized = bool(behavior_strategy)
    route_detected = _repository_route_detected(repository_intelligence, "\n".join(sources.values()))
    dependency_path_found = _repository_dependency_path_found(repository_intelligence, candidate_files)
    parsed_sections = parse_execution_plan_sections(execution_plan)
    validation_errors = validate_execution_plan(
        execution_plan=execution_plan,
        parsed_sections=parsed_sections,
        patch_texts=patch_texts,
        project_root=project_root,
    )

    artifact_path.write_text(execution_plan.rstrip() + "\n", encoding="utf-8")
    patch_paths: list[str] = []
    if patch_texts:
        patches_dir.mkdir(parents=True, exist_ok=True)
    for index, patch_text in enumerate(patch_texts, start=1):
        patch_path = patches_dir / f"patch_{index:03d}.diff"
        patch_path.write_text(patch_text.rstrip() + "\n", encoding="utf-8")
        patch_paths.append(str(patch_path))

    return ExecutionPlanResult(
        run_dir=str(resolved_run_dir),
        final_decision=final_decision,
        execution_plan=execution_plan,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        artifact_path=str(artifact_path),
        patch_paths=patch_paths,
        refused=False,
        source_aware=True,
        applicable_patch_count=len(patch_paths),
        no_target_reason=no_target_reason,
        candidate_files=candidate_files,
        synthesizer_used=synthesizer_used,
        synthesizer_strategy=synthesizer_strategy,
        synthesizer_fallback_reason=synthesizer_fallback_reason,
        memory_used=memory_used,
        memory_patterns_used=memory_patterns_used,
        behavior_synthesized=behavior_synthesized,
        behavior_strategy=behavior_strategy,
        real_implementation=behavior_synthesized,
        repository_intelligence_used=bool(repository_intelligence),
        route_detected=route_detected,
        dependency_path_found=dependency_path_found,
        repository_context_used=bool(repository_context),
        repository_context_files=_repository_context_count(repository_context, "matched_files"),
        repository_context_routes=_repository_context_count(repository_context, "matched_routes"),
        repository_context_functions=_repository_context_count(repository_context, "matched_functions"),
        repository_context_tests=_repository_context_count(repository_context, "matched_tests"),
        repository_context_chars=_repository_context_chars(resolved_run_dir),
        target_selection_used=bool(target_selection.selected_targets or target_selection.rejected_targets),
        selected_targets=target_selection.selected_targets,
        rejected_targets=target_selection.rejected_targets,
        target_classes=target_selection.target_classes,
        target_selection_reasons=target_selection.target_selection_reasons,
        target_selection_confidence=target_selection.confidence,
        multifile_plan_used=bool(multifile_plan.selected_files),
        multifile_plan_type=multifile_plan.plan_type,
        multifile_selected_files=multifile_plan.selected_files,
        multifile_file_roles=multifile_plan.file_roles,
        multifile_implementation_order=multifile_plan.implementation_order,
        multifile_missing_layers=multifile_plan.missing_layers,
        multifile_confidence=multifile_plan.confidence,
        multifile_rationale=multifile_plan.rationale,
        layer_creation_used=bool(layer_creation_plan.proposed_files),
        layer_proposed_files=layer_creation_plan.proposed_files,
        layer_rejected_layers=layer_creation_plan.rejected_layers,
        layer_creation_rationale=layer_creation_plan.creation_rationale,
        layer_creation_validation_errors=layer_creation_plan.validation_errors,
        layer_creation_confidence=layer_creation_plan.confidence,
    )


def parse_execution_plan_sections(content: str) -> dict[str, list[str] | str]:
    """Parse the fixed Execution Agent plan format."""

    parsed: dict[str, list[str] | str] = {}
    current_heading: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = SECTION_LINE.match(line)
        if match:
            current_heading = match.group(1).upper()
            key = SECTION_KEYS[current_heading]
            parsed[key] = "" if current_heading == "EXECUTION CONFIDENCE" else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading == "EXECUTION CONFIDENCE":
            parsed[key] = line.lstrip("- ").strip()
        elif line.startswith(("- ", "* ")):
            value = parsed.setdefault(key, [])
            if isinstance(value, list):
                value.append(line[2:].strip())
    return parsed


def validate_execution_plan(
    *,
    execution_plan: str,
    parsed_sections: dict[str, list[str] | str],
    patch_texts: list[str],
    project_root: Path,
) -> list[str]:
    """Validate execution plan and source-aware patch proposal safety contract."""

    errors: list[str] = []
    counts = _section_counts(execution_plan)
    for title, key in SECTION_KEYS.items():
        count = counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section:{title}")
        elif count > 1:
            errors.append(f"duplicate_section:{title}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section:{title}")
    for title, key in SECTION_KEYS.items():
        value = parsed_sections.get(key, "")
        if title == "EXECUTION CONFIDENCE":
            if str(value).strip() != "High":
                errors.append("execution_confidence_not_high")
        elif not isinstance(value, list) or not value:
            errors.append(f"empty_section:{title}")

    combined = "\n".join([execution_plan, *patch_texts])
    if FORBIDDEN_COMMAND_PATTERN.search(combined):
        errors.append("executable_command_present")
    if SHELL_SCRIPT_PATTERN.search(combined):
        errors.append("shell_script_present")
    if WINDOWS_C_PATH_PATTERN.search(combined):
        errors.append("forbidden_c_path_present")
    policy = load_filesystem_policy(project_root=project_root)
    for absolute_path in ABSOLUTE_MOUNT_PATH_PATTERN.findall(combined):
        if policy.is_path_blocked(absolute_path):
            errors.append("forbidden_c_path_present")
        elif not _is_under_project_root(absolute_path, project_root):
            errors.append(f"path_outside_project_root:{absolute_path}")
        errors.extend(_policy_errors_for_execution_path(policy, absolute_path))
    for patch_text in patch_texts:
        errors.extend(_validate_source_aware_patch(patch_text, project_root))
    return _dedupe(errors)


def _load_sources(run_dir: Path, warnings: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key, filenames in SOURCE_FILES.items():
        content = ""
        for filename in filenames:
            path = run_dir / filename
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                break
        if not content:
            warnings.append(f"missing_artifact:{filenames[0]}")
        sources[key] = content
    return sources


def _load_repository_intelligence(run_dir: Path, warnings: list[str]) -> dict[str, object]:
    intelligence_dir = run_dir / "repository_intelligence"
    if not intelligence_dir.exists():
        warnings.append("missing_repository_intelligence")
        return {}
    payload: dict[str, object] = {}
    for key, filename in (
        ("routes", "routes.json"),
        ("call_graph", "call_graph.json"),
        ("dependency_graph", "dependency_graph.json"),
        ("tests_map", "tests_map.json"),
    ):
        path = intelligence_dir / filename
        if not path.exists():
            warnings.append(f"missing_repository_intelligence:{filename}")
            continue
        try:
            payload[key] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append(f"invalid_repository_intelligence:{filename}")
    return payload


def _load_repository_context(run_dir: Path, warnings: list[str]) -> dict[str, object]:
    json_path = run_dir / "26_repository_context.json"
    if not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_repository_context_json")
        return {}
    if not isinstance(payload, dict):
        warnings.append("invalid_repository_context_shape")
        return {}
    context: dict[str, object] = {
        "repository_context": payload,
        "routes": payload.get("matched_routes", []),
        "tests_map": _tests_map_from_context(payload),
        "dependency_graph": _dependency_graph_from_context(payload),
        "recommended_patch_targets": payload.get("recommended_patch_targets", []),
        "matched_files": payload.get("matched_files", []),
    }
    return context


def _repository_context_payload(repository_context: dict[str, object]) -> dict[str, object]:
    payload = repository_context.get("repository_context", {}) if repository_context else {}
    return payload if isinstance(payload, dict) else {}


def select_patch_targets_from_repository_context(
    task: str,
    repository_context: dict[str, object],
    artifact_context: str,
    max_targets: int = 3,
) -> TargetSelectionResult:
    """Select architecturally appropriate patch targets from compact repository context."""

    if max_targets <= 0 or not repository_context:
        return TargetSelectionResult([], [], {}, {}, "Low")

    text = " ".join([task, artifact_context]).lower()
    task_intent = _task_intent(task)
    intent = _task_intent(text)
    intent["explicit_middleware"] = task_intent["explicit_middleware"]
    intent["explicit_ui"] = task_intent["explicit_ui"]
    intent["tests"] = task_intent["tests"]
    candidate_paths = _repository_context_candidate_paths(repository_context)
    if not candidate_paths:
        return TargetSelectionResult([], [], {}, {}, "Low")

    route_files = {
        str(route.get("file", ""))
        for route in repository_context.get("matched_routes", [])
        if isinstance(route, dict) and route.get("file")
    }
    target_classes = {path: classify_patch_target(path, route_files=route_files) for path in candidate_paths}
    rejected: list[str] = []
    reasons: dict[str, str] = {}
    scored: list[tuple[int, int, str]] = []
    for path in candidate_paths:
        target_class = target_classes[path]
        allowed, reason = _target_class_allowed(target_class, intent, path, repository_context)
        if not allowed:
            rejected.append(path)
            reasons[path] = reason
            continue
        score = _target_selection_score(path, target_class, intent, text, repository_context)
        reasons[path] = _target_selection_reason(path, target_class, score, intent)
        scored.append((score, _target_preference_index(target_class, intent), path))

    scored.sort(key=lambda item: (-item[0], item[1], item[2].count("/"), item[2]))
    selected = _balanced_target_selection(scored, target_classes, intent, max_targets)
    confidence = "High" if selected and (intent["backend_security"] or intent["rate_limit"]) else "Medium" if selected else "Low"
    return TargetSelectionResult(
        selected_targets=selected,
        rejected_targets=_dedupe(rejected),
        target_classes={path: target_classes[path] for path in _dedupe(selected + rejected)},
        target_selection_reasons={path: reasons[path] for path in _dedupe(selected + rejected) if path in reasons},
        confidence=confidence,
    )


def classify_patch_target(path_text: str, *, route_files: set[str] | None = None) -> str:
    """Classify a repository-relative path by likely architectural layer."""

    path = Path(path_text)
    lowered = path_text.lower()
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    suffix = path.suffix.lower()
    if path_text in (route_files or set()):
        return TARGET_ROUTE_HANDLER
    if path_text.startswith("tests/") or "/tests/" in path_text or name.startswith("test_") or name.endswith("_test.py"):
        return TARGET_TEST_FILE
    if suffix in {".tsx", ".jsx"} or parts & {"ui", "frontend", "components", "component", "pages", "views", "templates", "static"}:
        return TARGET_UI_COMPONENT
    if name in {"config.py", "settings.py", "config.json", "settings.json"} or parts & {"config", "settings"}:
        return TARGET_CONFIG_SETTINGS
    if "middleware" in lowered or "middlewares" in parts:
        return TARGET_MIDDLEWARE
    if parts & {"routes", "routers", "router", "api", "controllers", "endpoints"} or name in {"routes.py", "router.py", "views.py"}:
        return TARGET_ROUTE_HANDLER
    if parts & {"services", "service", "domain", "use_cases", "usecases", "core", "auth"} or any(
        token in lowered for token in ("service", "password_reset", "reset_service", "auth_guard", "account_recovery")
    ):
        return TARGET_SERVICE_LAYER
    return TARGET_UNKNOWN


def _task_intent(text: str) -> dict[str, bool]:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{1,}", text.lower()))
    return {
        "auth": bool(tokens & {"auth", "login", "password", "reset", "account", "recovery", "permission", "session"}),
        "rate_limit": bool(("rate" in tokens and "limit" in tokens) or tokens & {"ratelimit", "throttle", "throttling", "abuse"}),
        "backend_security": bool(tokens & {"auth", "login", "password", "reset", "account", "recovery", "rate", "limit", "abuse", "security"}),
        "explicit_middleware": "middleware" in tokens or "middlewares" in tokens,
        "explicit_ui": bool(tokens & {"ui", "frontend", "interface", "component", "screen", "page", "button"}),
        "tests": bool(tokens & {"test", "tests", "pytest", "regression"}),
        "constants": bool(tokens & {"constant", "constants", "config", "settings", "window", "attempts", "threshold"}),
    }


def _repository_context_candidate_paths(repository_context: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    for key in ("recommended_patch_targets", "_candidate_files", "matched_files", "dependency_paths", "matched_tests"):
        values = repository_context.get(key, [])
        if isinstance(values, list):
            candidates.extend(str(value) for value in values if value)
    routes = repository_context.get("matched_routes", [])
    if isinstance(routes, list):
        for route in routes:
            if isinstance(route, dict) and route.get("file"):
                candidates.append(str(route["file"]))
    functions = repository_context.get("matched_functions", [])
    classes = repository_context.get("matched_classes", [])
    for item in [*functions, *classes]:
        if isinstance(item, dict) and item.get("file"):
            candidates.append(str(item["file"]))
    deduped = _dedupe(candidates)
    existing_candidates = repository_context.get("_candidate_files", [])
    if isinstance(existing_candidates, list) and existing_candidates:
        existing = {str(path) for path in existing_candidates if path}
        return [path for path in deduped if path in existing]
    return deduped


def _target_class_allowed(
    target_class: str,
    intent: dict[str, bool],
    path: str,
    repository_context: dict[str, object],
) -> tuple[bool, str]:
    if target_class == TARGET_UI_COMPONENT and intent["backend_security"] and not intent["explicit_ui"]:
        return False, "Rejected UI component for backend/security/auth task without explicit frontend intent."
    if target_class == TARGET_MIDDLEWARE and not intent["explicit_middleware"] and not _middleware_context_justified(path, repository_context):
        return False, "Rejected middleware target because task did not explicitly request middleware and context did not require it."
    return True, f"Allowed {target_class} target for task intent."


def _middleware_context_justified(path: str, repository_context: dict[str, object]) -> bool:
    lowered = path.lower()
    if "middleware" not in lowered:
        return False
    for dependency in repository_context.get("dependency_paths", []):
        if str(dependency).lower() == lowered:
            return True
    for route in repository_context.get("matched_routes", []):
        if not isinstance(route, dict):
            continue
        haystack = " ".join(str(route.get(key, "")) for key in ("file", "handler", "path")).lower()
        if "middleware" in haystack:
            return True
    return False


def _target_selection_score(
    path: str,
    target_class: str,
    intent: dict[str, bool],
    text: str,
    repository_context: dict[str, object],
) -> int:
    score = 0
    preference = _target_preference_index(target_class, intent)
    score += max(0, 70 - preference * 10)
    lowered = path.lower()
    path_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", lowered))
    text_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
    score += min(24, 4 * len(path_tokens & text_tokens))
    if path in [str(value) for value in repository_context.get("recommended_patch_targets", []) if value]:
        score += 18
    if path in [str(value) for value in repository_context.get("matched_files", []) if value]:
        score += 8
    if target_class == TARGET_CONFIG_SETTINGS and (intent["rate_limit"] or intent["constants"]):
        score += 16
    if target_class == TARGET_TEST_FILE and intent["tests"]:
        score += 8
    if target_class == TARGET_UNKNOWN:
        score -= 20
    return score


def _target_preference_index(target_class: str, intent: dict[str, bool]) -> int:
    if intent["explicit_ui"]:
        order = [TARGET_UI_COMPONENT, TARGET_ROUTE_HANDLER, TARGET_SERVICE_LAYER, TARGET_TEST_FILE, TARGET_CONFIG_SETTINGS, TARGET_MIDDLEWARE, TARGET_UNKNOWN]
    elif intent["explicit_middleware"]:
        order = [TARGET_MIDDLEWARE, TARGET_SERVICE_LAYER, TARGET_ROUTE_HANDLER, TARGET_CONFIG_SETTINGS, TARGET_TEST_FILE, TARGET_UNKNOWN, TARGET_UI_COMPONENT]
    elif intent["backend_security"]:
        order = [TARGET_SERVICE_LAYER, TARGET_ROUTE_HANDLER, TARGET_CONFIG_SETTINGS, TARGET_TEST_FILE, TARGET_MIDDLEWARE, TARGET_UI_COMPONENT, TARGET_UNKNOWN]
    else:
        order = [TARGET_SERVICE_LAYER, TARGET_ROUTE_HANDLER, TARGET_CONFIG_SETTINGS, TARGET_TEST_FILE, TARGET_UNKNOWN, TARGET_MIDDLEWARE, TARGET_UI_COMPONENT]
    try:
        return order.index(target_class)
    except ValueError:
        return len(order)


def _target_selection_reason(path: str, target_class: str, score: int, intent: dict[str, bool]) -> str:
    intent_label = "backend security" if intent["backend_security"] else "general implementation"
    return f"Selected as {target_class} with score {score} for {intent_label} task: {path}."


def _balanced_target_selection(
    scored: list[tuple[int, int, str]],
    target_classes: dict[str, str],
    intent: dict[str, bool],
    max_targets: int,
) -> list[str]:
    if not scored:
        return []
    selected: list[str] = []
    by_class: dict[str, list[str]] = {}
    for _score, _preference, path in scored:
        by_class.setdefault(target_classes[path], []).append(path)

    if intent["rate_limit"] and not intent["explicit_middleware"] and not intent["explicit_ui"]:
        class_groups = (
            (TARGET_SERVICE_LAYER,),
            (TARGET_ROUTE_HANDLER,),
            (TARGET_TEST_FILE,),
            (TARGET_CONFIG_SETTINGS,),
        ) if intent["tests"] else (
            (TARGET_SERVICE_LAYER,),
            (TARGET_ROUTE_HANDLER,),
            (TARGET_CONFIG_SETTINGS,),
            (TARGET_TEST_FILE,),
        )
        for class_group in class_groups:
            for target_class in class_group:
                for path in by_class.get(target_class, []):
                    if path not in selected:
                        selected.append(path)
                        break
                if len(selected) >= max_targets or selected[-1:] and target_classes[selected[-1]] in class_group:
                    break
            if len(selected) >= max_targets:
                return selected[:max_targets]
        if selected:
            return selected[:max_targets]

    for _score, _preference, path in scored:
        if path not in selected:
            selected.append(path)
        if len(selected) >= max_targets:
            break
    return selected[:max_targets]


def _tests_map_from_context(payload: dict[str, object]) -> dict[str, list[str]]:
    files = payload.get("matched_files", [])
    tests = payload.get("matched_tests", [])
    if not isinstance(files, list) or not isinstance(tests, list):
        return {}
    return {str(file): [str(test) for test in tests] for file in files}


def _dependency_graph_from_context(payload: dict[str, object]) -> dict[str, object]:
    files = [str(path) for path in payload.get("matched_files", []) if path]
    dependencies = [str(path) for path in payload.get("dependency_paths", []) if path]
    return {
        "file_dependencies": [
            {
                "file": file,
                "depends_on": dependencies,
                "depended_by": [],
            }
            for file in files
        ]
    }


def _repository_context_count(repository_context: dict[str, object], key: str) -> int:
    payload = repository_context.get("repository_context", {}) if repository_context else {}
    if not isinstance(payload, dict):
        return 0
    value = payload.get(key, [])
    return len(value) if isinstance(value, list) else 0


def _repository_context_chars(run_dir: Path) -> int:
    total = 0
    for filename in ("26_repository_context.md", "26_repository_context.json"):
        path = run_dir / filename
        if path.exists():
            total += len(path.read_text(encoding="utf-8"))
    return total


def _extract_final_decision(final_review: str) -> str:
    lines = final_review.splitlines()
    for index, line in enumerate(lines):
        if line.strip().upper() == "FINAL DECISION":
            for candidate in lines[index + 1 :]:
                value = candidate.strip().lstrip("- ").strip()
                if value:
                    return value
    return "Unknown"


def _extract_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading_match = GENERIC_SECTION_LINE.match(stripped)
        if heading_match and not stripped.startswith(("-", "*")):
            current_heading = heading_match.group(1).upper()
            sections.setdefault(current_heading, [])
            continue
        bullet_match = BULLET_LINE.match(stripped) or NUMBERED_LIST_LINE.match(stripped)
        if current_heading and bullet_match:
            item = _sanitize_item(bullet_match.group(1))
            if item:
                sections.setdefault(current_heading, []).append(item)
    return sections


def _candidate_items(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        sanitized = _sanitize_item(item)
        if not sanitized:
            continue
        if sanitized.lower() in {"none", "n/a", "not applicable"}:
            cleaned.append("None")
        else:
            cleaned.append(sanitized)
    return _dedupe(cleaned)


def _render_execution_plan(
    *,
    files_to_modify: list[str],
    files_to_create: list[str],
    files_to_review: list[str],
    code_changes: list[str],
    test_items: list[str],
    security_items: list[str],
    no_target_reason: str = "",
) -> str:
    patch_strategy = [
        "Create source-aware reviewable patch proposal files under the run directory patches folder.",
        "Use actual repository-relative paths and existing source context when a safe target is found.",
        "Do not apply patches or change repository source files during this stage.",
    ]
    if no_target_reason:
        patch_strategy.append(f"No source patch generated because {no_target_reason}.")
    lines: list[str] = []
    for heading, items in (
        ("EXECUTION SUMMARY", code_changes[:5]),
        ("FILES TO MODIFY", files_to_modify),
        ("FILES TO CREATE", files_to_create),
        ("FILES TO REVIEW", files_to_review),
        ("PATCH STRATEGY", patch_strategy),
        ("EXPECTED TEST IMPACT", test_items[:6]),
        ("SECURITY CONSIDERATIONS", security_items[:6]),
    ):
        lines.append(heading)
        lines.extend(f"- {item}" for item in _dedupe(items))
        lines.append("")
    lines.extend(["EXECUTION CONFIDENCE", "High"])
    return "\n".join(lines).strip()


def _render_refusal(final_decision: str) -> str:
    decision = final_decision or "Unknown"
    return "\n".join(
        [
            "EXECUTION SUMMARY",
            f"- Refused patch proposal generation because FINAL DECISION is {decision}.",
            "",
            "FILES TO MODIFY",
            "- None",
            "",
            "FILES TO CREATE",
            "- None",
            "",
            "FILES TO REVIEW",
            "- 08_final_review.md",
            "",
            "PATCH STRATEGY",
            "- No patch proposals are generated unless Final Reviewer approves the run.",
            "",
            "EXPECTED TEST IMPACT",
            "- None",
            "",
            "SECURITY CONSIDERATIONS",
            "- Preserve the final review rejection until upstream artifacts are approved.",
            "",
            "EXECUTION CONFIDENCE",
            "High",
        ]
    )


def _render_patch_texts(
    *,
    candidate_files: list[str],
    code_changes: list[str],
    test_items: list[str],
    security_items: list[str],
    project_root: Path,
    artifact_context: str,
    layer_creation_plan: LayerCreationPlanResult | None = None,
    task: str = "",
) -> tuple[list[str], list[SynthesizedPatchResult]]:
    patches: list[str] = []
    synthesis_results: list[SynthesizedPatchResult] = []
    for target in candidate_files[:5]:
        body_items = _dedupe(code_changes[:4] + test_items[:2] + security_items[:2]) or [
            "Implement the approved revised artifact plan."
        ]
        result = synthesize_patch(
            project_root / target,
            artifact_context="\n".join([artifact_context, *body_items]),
            repository_context={"project_root": str(project_root)},
        )
        synthesis_results.append(result)
        patch_text = result.unified_diff
        if not patch_text and result.strategy != STRATEGY_FALLBACK_SOURCE_AWARE:
            patch_text = _render_source_patch(target, body_items, project_root)
            if patch_text:
                synthesis_results.append(
                    SynthesizedPatchResult(
                        success=True,
                        strategy=STRATEGY_FALLBACK_SOURCE_AWARE,
                        fallback_reason=result.fallback_reason,
                        unified_diff=patch_text,
                    )
                )
        if patch_text:
            patches.append(patch_text)
    if layer_creation_plan is not None:
        for relative in layer_creation_plan.proposed_files:
            role = layer_creation_plan.proposed_roles.get(relative, "FILES_TO_CREATE")
            patches.append(render_creation_patch(relative, role, task or artifact_context))
    return patches, synthesis_results


def _plan_layer_creations(
    *,
    task: str,
    repository_context: dict[str, object],
    multifile_plan,
    artifact_context: str,
    experience_context: str,
) -> LayerCreationPlanResult:
    if not multifile_plan.missing_layers:
        return LayerCreationPlanResult(
            proposed_files=[],
            proposed_roles={},
            creation_rationale=[],
            rejected_layers={},
            validation_errors=[],
            confidence="High",
        )
    return plan_missing_layers(
        task=task,
        repository_context=repository_context,
        multifile_plan=multifile_plan,
        artifact_context=artifact_context,
        experience_context=experience_context,
    )


def _memory_patterns_used(experience_context: str) -> list[str]:
    section = _section_body(experience_context, "REUSABLE PATTERNS")
    patterns: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip()
        if item and item != "No reusable patterns matched.":
            patterns.append(item.rstrip("."))
    return _dedupe(patterns)


def _memory_context_has_matches(experience_context: str, patterns: list[str]) -> bool:
    if not experience_context.strip():
        return False
    if "No matching engineering experience memory found." in experience_context:
        return False
    constants = _section_body(experience_context, "REUSABLE CONSTANTS")
    repairs = _section_body(experience_context, "RELEVANT REPAIRS")
    return bool(
        patterns
        or (constants and "No reusable constants matched." not in constants)
        or (repairs and "No relevant repairs matched." not in repairs)
    )


def _section_body(content: str, heading: str) -> str:
    lines = content.splitlines()
    current = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == heading.upper():
            current = True
            collected = []
            continue
        if current and stripped and stripped.upper() == stripped and not stripped.startswith("-"):
            break
        if current:
            collected.append(line)
    return "\n".join(collected).strip()


def _synthesis_strategy(results: list[SynthesizedPatchResult]) -> str:
    for result in results:
        if result.success and result.strategy != STRATEGY_FALLBACK_SOURCE_AWARE:
            return result.strategy
    for result in results:
        if result.success:
            return result.strategy
    return results[0].strategy if results else ""


def _synthesis_fallback_reason(results: list[SynthesizedPatchResult]) -> str:
    for result in results:
        if result.fallback_reason:
            return result.fallback_reason
    return ""


def _behavior_strategy(results: list[SynthesizedPatchResult]) -> str:
    for result in results:
        if result.success and result.strategy in REAL_IMPLEMENTATION_STRATEGIES:
            return result.strategy
    return ""


def _scan_repository_files(project_root: Path) -> list[str]:
    files: list[str] = []
    max_files = 5000
    for root in _scan_roots(project_root):
        for directory, dirnames, filenames in os.walk(root):
            directory_path = Path(directory)
            try:
                directory_relative = directory_path.relative_to(project_root)
            except ValueError:
                dirnames[:] = []
                continue
            if _is_excluded_directory(directory_relative):
                dirnames[:] = []
                continue
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not _is_excluded_directory(directory_relative / dirname)
            ]
            for filename in filenames:
                try:
                    relative = (directory_path / filename).relative_to(project_root)
                except ValueError:
                    continue
                if _is_safe_repo_file(relative):
                    files.append(relative.as_posix())
                    if len(files) >= max_files:
                        return sorted(_dedupe(files))
    try:
        root_children = list(project_root.iterdir())
    except OSError:
        root_children = []
    for child in root_children:
        if child.is_file():
            try:
                relative = child.relative_to(project_root)
            except ValueError:
                continue
            if _is_safe_repo_file(relative):
                files.append(relative.as_posix())
    return sorted(_dedupe(files))


def _repository_directories(repo_files: list[str], project_root: Path | None = None) -> list[str]:
    directories: set[str] = set()
    for file_path in repo_files:
        parent = Path(file_path).parent
        while parent.as_posix() not in {"", "."}:
            directories.add(parent.as_posix())
            parent = parent.parent
    if project_root is not None:
        for root in _scan_roots(project_root):
            for directory, dirnames, _filenames in os.walk(root):
                directory_path = Path(directory)
                try:
                    relative = directory_path.relative_to(project_root)
                except ValueError:
                    dirnames[:] = []
                    continue
                if _is_excluded_directory(relative):
                    dirnames[:] = []
                    continue
                if relative.as_posix() not in {"", "."}:
                    directories.add(relative.as_posix())
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not _is_excluded_directory(relative / dirname)
                ]
    return sorted(directories)


def _scan_roots(project_root: Path) -> list[Path]:
    preferred = (
        "agentic_network",
        "app",
        "apps",
        "src",
        "lib",
        "packages",
        "scripts",
        "tests",
        "docs",
        "dataset_curation",
    )
    roots = [project_root / name for name in preferred if (project_root / name).is_dir()]
    return roots or [project_root]


def _is_excluded_directory(relative: Path) -> bool:
    if set(relative.parts) & EXCLUDED_DIR_PARTS:
        return True
    for prefix in EXCLUDED_PREFIXES:
        try:
            relative.relative_to(prefix)
            return True
        except ValueError:
            pass
    return False


def _is_safe_repo_file(relative: Path) -> bool:
    if relative.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if set(relative.parts) & EXCLUDED_DIR_PARTS:
        return False
    for prefix in EXCLUDED_PREFIXES:
        try:
            relative.relative_to(prefix)
            return False
        except ValueError:
            pass
    return True


def _select_candidate_files(
    *,
    repo_files: list[str],
    artifact_text: str,
    files_to_modify: list[str],
    files_to_create: list[str],
    repository_intelligence: dict[str, object] | None = None,
    max_candidates: int = 3,
) -> list[str]:
    explicit = _explicit_existing_paths(repo_files, files_to_modify + files_to_create)
    if explicit:
        return explicit[:max_candidates]
    hints = _artifact_hints(artifact_text, files_to_modify, files_to_create)
    intelligence_candidates = _repository_intelligence_candidates(
        repository_intelligence or {},
        repo_files,
        hints,
        artifact_text,
    )
    if intelligence_candidates:
        return intelligence_candidates[:max_candidates]
    preferred = _preferred_synthesis_files(repo_files, hints)
    if preferred:
        return preferred[:max_candidates]
    scored: list[tuple[int, str]] = []
    for relative in repo_files:
        score = _candidate_score(relative, hints)
        if score > 0:
            scored.append((score, relative))
    scored.sort(key=lambda item: (-item[0], _candidate_sort_bucket(item[1]), item[1]))
    return [relative for _, relative in scored[:max_candidates]]


def _preferred_synthesis_files(repo_files: list[str], hints: set[str]) -> list[str]:
    if {"password", "reset", "rate", "limit"} <= hints:
        behavior_candidates = [
            relative
            for relative in repo_files
            if Path(relative).suffix == ".py"
            and not (relative.startswith("tests/") or "/tests/" in relative)
            and any(
                token in relative.lower()
                for token in ("auth", "password", "reset", "rate", "limit", "middleware", "service", "route")
            )
        ]
        if behavior_candidates:
            return sorted(behavior_candidates, key=lambda value: (_candidate_sort_bucket(value), value.count("/"), value))
        config_candidates = [
            relative
            for relative in repo_files
            if Path(relative).name == "config.py" and not relative.startswith("tests/")
        ]
        if config_candidates:
            return sorted(config_candidates, key=lambda value: (value.count("/"), value))
    return []


def _repository_intelligence_candidates(
    repository_intelligence: dict[str, object],
    repo_files: list[str],
    hints: set[str],
    artifact_text: str,
) -> list[str]:
    if not repository_intelligence:
        return []
    repo_set = set(repo_files)
    candidates: list[str] = []
    recommended = repository_intelligence.get("recommended_patch_targets", [])
    if isinstance(recommended, list):
        candidates.extend(str(path) for path in recommended if str(path) in repo_set)
    matched_files = repository_intelligence.get("matched_files", [])
    if isinstance(matched_files, list):
        candidates.extend(str(path) for path in matched_files if str(path) in repo_set)
    route_files = _matching_route_files(repository_intelligence, hints, artifact_text)
    candidates.extend(path for path in route_files if path in repo_set)
    dependency_files = _dependency_files_for(repository_intelligence, route_files)
    candidates.extend(path for path in dependency_files if path in repo_set)
    tests = _tests_for_files(repository_intelligence, candidates)
    candidates.extend(path for path in tests if path in repo_set)
    if not candidates:
        dependency_graph = repository_intelligence.get("dependency_graph", {})
        if isinstance(dependency_graph, dict):
            for entry in dependency_graph.get("file_dependencies", []):
                if not isinstance(entry, dict):
                    continue
                file_path = str(entry.get("file", ""))
                if file_path in repo_set and _path_matches_hints(file_path, hints):
                    candidates.append(file_path)
    return _dedupe(candidates)


def _matching_route_files(
    repository_intelligence: dict[str, object],
    hints: set[str],
    artifact_text: str,
) -> list[str]:
    routes = repository_intelligence.get("routes", [])
    if not isinstance(routes, list):
        return []
    text_tokens = _artifact_hints(artifact_text, [], [])
    generic_route_tokens = {"api", "app", "route", "routes", "router", "handler", "test", "tests"}
    tokens = (hints | text_tokens) - generic_route_tokens
    if not tokens:
        return []
    matched: list[str] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        haystack = " ".join(
            str(route.get(key, ""))
            for key in ("path", "handler", "file", "method")
        ).lower()
        route_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", haystack))
        if tokens & route_tokens:
            file_path = str(route.get("file", ""))
            if file_path:
                matched.append(file_path)
    return _dedupe(matched)


def _dependency_files_for(repository_intelligence: dict[str, object], source_files: list[str]) -> list[str]:
    if not source_files:
        return []
    dependency_graph = repository_intelligence.get("dependency_graph", {})
    if not isinstance(dependency_graph, dict):
        return []
    source_set = set(source_files)
    matches: list[str] = []
    for entry in dependency_graph.get("file_dependencies", []):
        if not isinstance(entry, dict):
            continue
        file_path = str(entry.get("file", ""))
        if file_path in source_set:
            matches.extend(str(path) for path in entry.get("depends_on", []) if path)
        depended_by = [str(path) for path in entry.get("depended_by", []) if path]
        if file_path and any(source in depended_by for source in source_set):
            matches.append(file_path)
    return _dedupe(matches)


def _tests_for_files(repository_intelligence: dict[str, object], source_files: list[str]) -> list[str]:
    tests_map = repository_intelligence.get("tests_map", {})
    if not isinstance(tests_map, dict):
        return []
    tests: list[str] = []
    for source in source_files:
        values = tests_map.get(source, [])
        if isinstance(values, list):
            tests.extend(str(value) for value in values if value)
    return _dedupe(tests)


def _path_matches_hints(path_text: str, hints: set[str]) -> bool:
    lowered = path_text.lower()
    return any(hint in lowered for hint in hints)


def _repository_route_detected(repository_intelligence: dict[str, object], artifact_text: str) -> bool:
    hints = _artifact_hints(artifact_text, [], [])
    return bool(_matching_route_files(repository_intelligence, hints, artifact_text))


def _repository_dependency_path_found(
    repository_intelligence: dict[str, object],
    candidate_files: list[str],
) -> bool:
    if not repository_intelligence or not candidate_files:
        return False
    dependencies = _dependency_files_for(repository_intelligence, candidate_files)
    tests = _tests_for_files(repository_intelligence, candidate_files)
    return bool(dependencies or tests)


def _explicit_existing_paths(repo_files: list[str], items: list[str]) -> list[str]:
    repo_set = set(repo_files)
    matches: list[str] = []
    for item in items:
        for path_text in PATH_LIKE_TOKEN.findall(item):
            normalized = path_text.strip().strip("`.,")
            if normalized in repo_set:
                matches.append(normalized)
    return _dedupe(matches)


def _artifact_hints(artifact_text: str, files_to_modify: list[str], files_to_create: list[str]) -> set[str]:
    text = " ".join([artifact_text, *files_to_modify, *files_to_create]).lower()
    tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
    hints = {token for token in tokens if token in GENERIC_HINT_WORDS}
    for token in tokens:
        hints.update(KEYWORD_GROUPS.get(token, ()))
    return hints


def _candidate_score(relative: str, hints: set[str]) -> int:
    lowered = relative.lower()
    name = Path(relative).name.lower()
    score = 0
    for hint in hints:
        if hint in lowered:
            score += 4 if hint in name else 2
    if relative.startswith("tests/") or "/tests/" in relative:
        score -= 4
        score += 1 if hints & {"test", "auth", "password", "rate", "limit"} else 0
    if Path(relative).suffix == ".py":
        score += 1
    return score


def _candidate_sort_bucket(relative: str) -> int:
    if relative.startswith("tests/") or "/tests/" in relative:
        return 2
    if relative.endswith((".md", ".json", ".toml", ".yaml", ".yml")):
        return 1
    return 0


def _render_source_patch(relative: str, body_items: list[str], project_root: Path) -> str:
    target = project_root / relative
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return ""
    if not lines:
        return ""
    insert_index = _insertion_index(lines)
    old_start = insert_index + 1
    context_line = lines[insert_index]
    comment = _comment_for_file(relative, body_items)
    if comment in lines:
        return ""
    return "\n".join(
        [
            f"--- a/{relative}",
            f"+++ b/{relative}",
            f"@@ -{old_start},1 +{old_start},2 @@",
            f" {context_line}",
            f"+{comment}",
        ]
    )


def _insertion_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#!", "# -*-", "//", "/*", "*")):
            return index
    return 0


def _comment_for_file(relative: str, body_items: list[str]) -> str:
    summary = _summarize_patch_note(body_items)
    suffix = Path(relative).suffix.lower()
    if suffix == ".py":
        return f"# ANN patch proposal: {summary}"
    if suffix in {".js", ".ts", ".tsx", ".jsx"}:
        return f"// ANN patch proposal: {summary}"
    return f"<!-- ANN patch proposal: {summary} -->"


def _summarize_patch_note(body_items: list[str]) -> str:
    text = body_items[0] if body_items else "review this file for the approved implementation plan"
    text = re.sub(r"[^A-Za-z0-9 ,.;:_/-]", "", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(text) > 120:
        text = text[:117].rstrip() + "..."
    return text or "review this file for the approved implementation plan"


def _validate_source_aware_patch(patch_text: str, project_root: Path) -> list[str]:
    errors: list[str] = []
    policy = load_filesystem_policy(project_root=project_root)
    lines = patch_text.splitlines()
    if len(lines) < 5:
        return ["patch_too_short"]
    if lines[0].strip() == "--- /dev/null":
        return _validate_creation_patch(lines, project_root, policy)
    if lines[0].startswith("--- old") or lines[1].startswith("+++ new"):
        errors.append("placeholder_patch_header_present")
    old_match = re.match(r"^--- a/(.+)$", lines[0])
    new_match = re.match(r"^\+\+\+ b/(.+)$", lines[1])
    if not old_match or not new_match:
        errors.append("patch_unified_headers_invalid")
        return errors
    if old_match.group(1) != new_match.group(1):
        errors.append("patch_header_paths_mismatch")
    relative = Path(old_match.group(1))
    if not _is_safe_repo_file(relative):
        errors.append(f"patch_target_protected_or_unsupported:{relative.as_posix()}")
    target = policy.normalize_path(relative)
    if not _is_under_project_root(str(target), project_root):
        errors.append(f"path_outside_project_root:{target}")
    for error in policy.validate_patch_target(target):
        if error == "forbidden_c_path_present":
            errors.append("forbidden_c_path_present")
        elif error.startswith("protected_path_modified:"):
            errors.append(f"patch_target_protected_or_unsupported:{relative.as_posix()}")
        elif error.startswith("path_traversal_present:"):
            errors.append(error)
    if not target.exists():
        errors.append(f"patch_target_missing:{relative.as_posix()}")
    hunk_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$", lines[2])
    if not hunk_match:
        errors.append("patch_hunk_header_invalid")
    context_lines = [line[1:] for line in lines[3:] if line.startswith(" ")]
    if not context_lines:
        errors.append("patch_context_missing")
    elif target.exists():
        try:
            target_text = target.read_text(encoding="utf-8")
            target_lines = target_text.splitlines()
        except (UnicodeDecodeError, OSError):
            errors.append(f"patch_target_unreadable:{relative.as_posix()}")
        else:
            if not any(context in target_lines for context in context_lines):
                errors.append(f"patch_context_not_found:{relative.as_posix()}")
            try:
                patched_text = _apply_simple_unified_diff(target_text, patch_text)
            except ValueError as exc:
                errors.append(f"patch_context_invalid:{exc}")
            else:
                if target.suffix == ".py":
                    try:
                        ast.parse(patched_text)
                    except SyntaxError:
                        errors.append("python_ast_invalid_after_patch")
                if target.suffix == ".json":
                    try:
                        json.loads(patched_text)
                    except json.JSONDecodeError:
                        errors.append("json_invalid_after_patch")
    if not any(line.startswith("+") and not line.startswith("+++") for line in lines[3:]):
        errors.append("patch_addition_missing")
    return errors


def _validate_creation_patch(lines: list[str], project_root: Path, policy) -> list[str]:
    errors: list[str] = []
    new_match = re.match(r"^\+\+\+ b/(.+)$", lines[1])
    if not new_match:
        return ["patch_creation_header_invalid"]
    relative_text = new_match.group(1)
    relative = Path(relative_text)
    if relative.is_absolute():
        errors.append(f"path_outside_project_root:{relative_text}")
    if not _is_safe_repo_file(relative):
        errors.append(f"patch_target_protected_or_unsupported:{relative.as_posix()}")
    target = policy.normalize_path(relative)
    if not _is_under_project_root(str(target), project_root):
        errors.append(f"path_outside_project_root:{target}")
    for error in policy.validate_patch_target(target):
        if error == "forbidden_c_path_present":
            errors.append("forbidden_c_path_present")
        elif error.startswith("protected_path_modified:"):
            errors.append(f"patch_target_protected_or_unsupported:{relative.as_posix()}")
        elif error.startswith("path_traversal_present:"):
            errors.append(error)
    if target.exists():
        errors.append(f"patch_creation_target_exists:{relative.as_posix()}")
    hunk_match = re.match(r"^@@ -0,0 \+1,(\d+) @@$", lines[2])
    if not hunk_match:
        errors.append("patch_hunk_header_invalid")
    additions = [line[1:] for line in lines[3:] if line.startswith("+") and not line.startswith("+++")]
    if not additions:
        errors.append("patch_addition_missing")
    else:
        expected_count = int(hunk_match.group(1)) if hunk_match else -1
        if expected_count != -1 and expected_count != len(additions):
            errors.append("patch_hunk_line_count_mismatch")
        content = "\n".join(additions) + "\n"
        if target.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError:
                errors.append("python_ast_invalid_after_patch")
        if target.suffix == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError:
                errors.append("json_invalid_after_patch")
    return _dedupe(errors)


def _apply_simple_unified_diff(old_text: str, patch_text: str) -> str:
    old_lines = old_text.splitlines()
    result: list[str] = []
    source_index = 0
    lines = patch_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("@@ "):
            index += 1
            continue
        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not match:
            raise ValueError("invalid_hunk_header")
        old_start = int(match.group(1))
        expected_index = max(old_start - 1, 0)
        if expected_index < source_index:
            raise ValueError("overlapping_hunks")
        result.extend(old_lines[source_index:expected_index])
        source_index = expected_index
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            hunk_line = lines[index]
            if hunk_line.startswith(("--- ", "+++ ")):
                index += 1
                continue
            if not hunk_line:
                raise ValueError("empty_hunk_line")
            marker = hunk_line[0]
            value = hunk_line[1:]
            if marker == " ":
                if source_index >= len(old_lines) or old_lines[source_index] != value:
                    raise ValueError("context_mismatch")
                result.append(old_lines[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(old_lines) or old_lines[source_index] != value:
                    raise ValueError("delete_mismatch")
                source_index += 1
            elif marker == "+":
                result.append(value)
            elif marker == "\\":
                pass
            else:
                raise ValueError("unsupported_hunk_line")
            index += 1
    result.extend(old_lines[source_index:])
    return "\n".join(result) + ("\n" if old_text.endswith("\n") else "")


def _sanitize_item(item: str) -> str:
    text = item.replace("`", "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".") + "." if text and not text.endswith(".") else text
    if FORBIDDEN_COMMAND_PATTERN.search(text) or WINDOWS_C_PATH_PATTERN.search(text):
        return ""
    return text


def _policy_errors_for_execution_path(policy, path_text: str) -> list[str]:
    errors: list[str] = []
    for error in policy.validate_read_path(path_text):
        if error == "forbidden_c_path_present":
            errors.append(error)
        elif error.startswith("blocked_path:"):
            errors.append(error)
    return errors


def _section_counts(content: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTIONS}
    for line in content.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _is_under_project_root(path_text: str, project_root: Path) -> bool:
    candidate_key = _canonical_path_key(path_text)
    project_key = _canonical_path_key(project_root)
    return candidate_key == project_key or candidate_key.startswith(project_key.rstrip("/") + "/")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
