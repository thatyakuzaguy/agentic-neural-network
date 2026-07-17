"""Non-LLM Patch Quality Agent.

This stage reads generated patch proposal artifacts and classifies whether the
diffs are meaningful enough for approval review. It never applies patches,
executes code, runs shell commands, loads models, or modifies repository files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import load_filesystem_policy

PATCH_QUALITY_OUTPUT_FILE = "25_patch_quality.md"
PATCHES_DIR = "patches"
SUMMARY_FILE = "summary.json"

IMPLEMENTATION_READY = "IMPLEMENTATION_READY"
NEEDS_REVISION = "NEEDS_REVISION"
NEEDS_RELOCATION = "NEEDS_RELOCATION"
LOW_VALUE_COMMENT_ONLY = "LOW_VALUE_COMMENT_ONLY"
UNCONNECTED_LOGIC = "UNCONNECTED_LOGIC"
REJECTED = "REJECTED"

QUALITY_ORDER = {
    REJECTED: 0,
    LOW_VALUE_COMMENT_ONLY: 1,
    UNCONNECTED_LOGIC: 2,
    NEEDS_RELOCATION: 3,
    NEEDS_REVISION: 4,
    IMPLEMENTATION_READY: 5,
}
REPORT_SECTIONS = ("PATCH", "QUALITY", "SCORE", "REASONS", "CONFIDENCE")
DIFF_PATH_LINE = re.compile(r"(?m)^\s*(?:---|\+\+\+)\s+(.+?)\s*$")
HUNK_LINE = re.compile(r"(?m)^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")
DANGEROUS_TEXT_PATTERN = re.compile(
    r"(?im)(?:^|\s|\+)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\(|shell\s*=\s*True)"
)
WINDOWS_C_PATH_PATTERN = re.compile(r"(?i)(?:^|[\s:+-])(?:/mnt/c\b|[A-Z]:\\)")
COMMENT_ONLY_PATTERN = re.compile(
    r"^\s*(?:#|//|/\*|\*|<!--|-->|pass\b|TODO\b|todo\b|Future implementation\b|ANN patch proposal\b)"
)
PLACEHOLDER_PATTERN = re.compile(
    r"(?im)(ANN patch proposal|TODO|Future implementation|placeholder|NotImplementedError)"
)
DEF_LINE = re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
IMPORT_LINE = re.compile(r"^\s*(?:import\s+[A-Za-z_][\w.]*|from\s+[A-Za-z_][\w.]*\s+import\s+)")
ROUTE_DECORATOR_LINE = re.compile(r"^\s*@(?:app|router)\.(?:get|post|put|patch|delete|api_route)\b")
SERVICE_PATH_PATTERN = re.compile(r"(?:^|/)(?:services?|domain|use_cases?)/|_service\.py$|service", re.IGNORECASE)
TEST_PATH_PATTERN = re.compile(r"(?:^|/)tests?/|(?:^|/)test_[^/]+\.py$|_test\.py$")
TRIVIAL_ASSERT_PATTERN = re.compile(
    r"^\s*assert\s+(?:True|False|\d+\s*(?:==|!=|<=|>=|<|>)\s*\d+|"
    r"[A-Z_][A-Z0-9_]*\s*(?:==|!=)\s*(?:True|False|\d+|['\"][^'\"]*['\"]))\s*$"
)


@dataclass(frozen=True)
class _DiffFile:
    path: str
    added_lines: list[str]
    context_lines: list[str]
    is_created: bool


@dataclass(frozen=True)
class _SemanticPenalty:
    code: str
    reason: str
    points: int
    blocks_ready: bool = True


@dataclass(frozen=True)
class PatchQualityEvaluation:
    patch_name: str
    quality: str
    score: int
    reasons: list[str]
    validation_errors: list[str]
    target_paths: list[str]


@dataclass(frozen=True)
class PatchQualityResult:
    run_dir: str
    artifact_path: str
    report: str
    evaluations: list[PatchQualityEvaluation]
    decision: str
    score: int
    reasons: list[str]
    warnings: list[str]
    validation_errors: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def evaluate_patch_quality(
    run_dir: Path,
    *,
    patch_dir: str = PATCHES_DIR,
    artifact_name: str = PATCH_QUALITY_OUTPUT_FILE,
) -> PatchQualityResult:
    """Evaluate generated patches and write a patch quality artifact."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    context = _load_context(resolved_run_dir, warnings)
    patch_paths = sorted((resolved_run_dir / patch_dir).glob("*.diff"))
    evaluations: list[PatchQualityEvaluation] = []
    if not patch_paths:
        warnings.append("no_patch_files_found")
        evaluations.append(
            PatchQualityEvaluation(
                patch_name="None",
                quality=REJECTED,
                score=0,
                reasons=["No patch files were available for quality review."],
                validation_errors=["patch_files_missing"],
                target_paths=[],
            )
        )
    for patch_path in patch_paths:
        try:
            patch_text = patch_path.read_text(encoding="utf-8")
        except OSError:
            evaluations.append(
                PatchQualityEvaluation(
                    patch_name=patch_path.name,
                    quality=REJECTED,
                    score=0,
                    reasons=["Patch file could not be read."],
                    validation_errors=[f"patch_unreadable:{patch_path.name}"],
                    target_paths=[],
                )
            )
            continue
        evaluations.append(
            _evaluate_patch(
                patch_name=patch_path.name,
                patch_text=patch_text,
                context=context,
                project_root=_project_root(),
            )
        )

    decision = _aggregate_decision(evaluations)
    score = min((evaluation.score for evaluation in evaluations), default=0)
    reasons = _dedupe(
        reason
        for evaluation in evaluations
        for reason in evaluation.reasons
        if reason
    )[:8]
    validation_errors = _dedupe(
        error
        for evaluation in evaluations
        for error in evaluation.validation_errors
        if error
    )
    report = _render_report(evaluations)
    parsed = parse_patch_quality_report(report)
    validation_errors.extend(validate_patch_quality_report(report, parsed))
    validation_errors = _dedupe(validation_errors)

    artifact_path = resolved_run_dir / artifact_name
    artifact_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    return PatchQualityResult(
        run_dir=str(resolved_run_dir),
        artifact_path=str(artifact_path),
        report=report,
        evaluations=evaluations,
        decision=decision,
        score=score,
        reasons=reasons,
        warnings=_dedupe(warnings),
        validation_errors=validation_errors,
    )


def patch_quality_summary_fields(result: PatchQualityResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "patch_quality_status": "VALID" if result.validation_passed else "INVALID",
        "patch_quality_decision": result.decision,
        "patch_quality_score": result.score,
        "patch_quality_reasons": result.reasons,
        "patch_quality_validation_passed": result.validation_passed,
        "patch_quality_validation_errors": result.validation_errors,
        "patch_quality_validation_warnings": result.warnings,
    }


def parse_patch_quality_report(content: str) -> list[dict[str, Any]]:
    """Parse repeated fixed-format patch quality blocks."""

    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in REPORT_SECTIONS:
            section = line
            if section == "PATCH":
                if current:
                    parsed.append(current)
                current = {"reasons": []}
            continue
        if current is None or section is None:
            continue
        if section == "PATCH":
            current["patch"] = line
        elif section == "QUALITY":
            current["quality"] = line
        elif section == "SCORE":
            try:
                current["score"] = int(line)
            except ValueError:
                current["score"] = line
        elif section == "REASONS" and line.startswith("- "):
            current.setdefault("reasons", []).append(line[2:].strip())
        elif section == "CONFIDENCE":
            current["confidence"] = line
    if current:
        parsed.append(current)
    return parsed


def validate_patch_quality_report(content: str, parsed: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not parsed:
        errors.append("patch_quality_blocks_missing")
        return errors
    valid_qualities = set(QUALITY_ORDER)
    for index, block in enumerate(parsed, start=1):
        for key in ("patch", "quality", "score", "reasons", "confidence"):
            if key not in block or block[key] in ("", None) or block[key] == []:
                errors.append(f"patch_quality_block_{index}_missing:{key}")
        if block.get("quality") not in valid_qualities:
            errors.append(f"patch_quality_block_{index}_quality_invalid")
        score = block.get("score")
        if not isinstance(score, int) or score < 0 or score > 100:
            errors.append(f"patch_quality_block_{index}_score_invalid")
        if block.get("confidence") != "High":
            errors.append(f"patch_quality_block_{index}_confidence_not_high")
    return _dedupe(errors)


def _evaluate_patch(
    *,
    patch_name: str,
    patch_text: str,
    context: dict[str, Any],
    project_root: Path,
) -> PatchQualityEvaluation:
    reasons: list[str] = []
    validation_errors: list[str] = []
    target_paths = _target_paths(patch_text)
    source_aware = _is_source_aware(patch_text)
    creation_patch = _is_creation_patch(patch_text)
    layer_creation_planned = _layer_creation_planned(target_paths, context)
    additions = _added_lines(patch_text)
    functional_lines = [line for line in additions if _is_functional_line(line)]
    placeholder = any(PLACEHOLDER_PATTERN.search(line) for line in additions)
    comment_only = bool(additions) and not functional_lines
    dangerous = DANGEROUS_TEXT_PATTERN.search(patch_text) or WINDOWS_C_PATH_PATTERN.search(patch_text)
    protected_errors = _protected_path_errors(target_paths, project_root)

    if dangerous:
        validation_errors.append("dangerous_content_present")
        reasons.append("Dangerous command or executable construct detected.")
    validation_errors.extend(protected_errors)
    if protected_errors:
        reasons.append("Patch targets a protected or forbidden path.")
    if dangerous or protected_errors:
        return PatchQualityEvaluation(patch_name, REJECTED, 0, _dedupe(reasons), _dedupe(validation_errors), target_paths)
    if creation_patch and not layer_creation_planned:
        reasons.append("New file creation patch was not listed in the layer creation plan.")
        validation_errors.append("unplanned_creation_file")
        return PatchQualityEvaluation(
            patch_name,
            REJECTED,
            0,
            _dedupe(reasons),
            _dedupe(validation_errors),
            target_paths,
        )

    if comment_only:
        reasons.extend(["Comment-only patch.", "No functional behavior added."])
        return PatchQualityEvaluation(
            patch_name,
            LOW_VALUE_COMMENT_ONLY,
            _score(
                real_implementation=False,
                architecture_connected=False,
                memory_reused=False,
                tests_generated=False,
                source_aware=source_aware,
                no_placeholders=not placeholder,
                comment_only=True,
                disconnected=False,
            ),
            _dedupe(reasons),
            [],
            target_paths,
        )

    real_implementation = bool(functional_lines)
    multifile_planned = _multifile_planned(target_paths, context)
    multifile_unplanned = _multifile_unplanned(target_paths, context)
    target_selection_connected = _target_selection_selected(target_paths, context)
    target_selection_rejected = _target_selection_rejected(target_paths, context)
    architecture_connected = (
        _architecture_connected(target_paths, patch_text, context)
        or target_selection_connected
        or multifile_planned
        or layer_creation_planned
    )
    tests_generated = _tests_generated(target_paths, patch_text)
    semantic_penalties = _semantic_penalties(
        patch_text=patch_text,
        target_paths=target_paths,
        tests_generated=tests_generated,
    )
    strong_tests_generated = tests_generated and not any(
        penalty.code == "trivial_tests_detected" for penalty in semantic_penalties
    )
    memory_reused = _memory_reused(patch_text, context)
    disconnected = _disconnected_logic(
        patch_text,
        context,
        target_paths,
        architecture_connected,
        strong_tests_generated,
    )
    relocation = (
        target_selection_rejected
        or multifile_unplanned
        or _needs_relocation(target_paths, patch_text, context)
    )

    if real_implementation:
        reasons.append("Real implementation detected.")
    if architecture_connected:
        reasons.append("Architecture connection detected.")
    if memory_reused:
        reasons.append("Memory constants or patterns reused.")
    if tests_generated:
        reasons.append("Tests generated.")
    if strong_tests_generated:
        reasons.append("Non-trivial test coverage detected.")
    if source_aware:
        reasons.append("Source-aware unified diff with real context.")
    if not placeholder:
        reasons.append("No placeholders detected.")
    reasons.extend(penalty.reason for penalty in semantic_penalties)
    if multifile_planned:
        reasons.append("Patch targets a file selected by the multi-file implementation plan.")
    if layer_creation_planned:
        reasons.append("Patch creates a file selected by the layer creation plan.")
    if _multifile_missing_layers_documented(context):
        reasons.append("Missing implementation layers were documented by the multi-file plan.")
    if multifile_unplanned:
        reasons.append("Patch target was not selected by the multi-file implementation plan.")
    if relocation:
        reasons.append("Patch target was rejected or logic appears placed in the wrong file.")
    if disconnected:
        reasons.append("Functional additions appear disconnected from existing architecture.")

    score = _score(
        real_implementation=real_implementation,
        architecture_connected=architecture_connected,
        memory_reused=memory_reused,
        tests_generated=strong_tests_generated,
        source_aware=source_aware,
        no_placeholders=not placeholder,
        comment_only=False,
        disconnected=disconnected,
    )
    if multifile_planned:
        score = min(100, score + 10)
    if layer_creation_planned:
        score = min(100, score + 10)
    for penalty in semantic_penalties:
        score = max(0, score - penalty.points)
    if not strong_tests_generated:
        score = min(score, 90)
    if any(penalty.blocks_ready for penalty in semantic_penalties):
        score = min(score, 79)
    if relocation:
        score = max(0, score - 25)
        quality = NEEDS_RELOCATION
    elif disconnected:
        quality = UNCONNECTED_LOGIC
    elif any(penalty.blocks_ready for penalty in semantic_penalties):
        quality = NEEDS_REVISION
    elif real_implementation and architecture_connected and source_aware and not placeholder:
        quality = IMPLEMENTATION_READY
    elif real_implementation:
        quality = UNCONNECTED_LOGIC
    else:
        quality = LOW_VALUE_COMMENT_ONLY
    return PatchQualityEvaluation(
        patch_name=patch_name,
        quality=quality,
        score=score,
        reasons=_dedupe(reasons),
        validation_errors=[],
        target_paths=target_paths,
    )


def _load_context(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    filenames = (
        "11_execution_plan.md",
        "03_code_revised.md",
        "04_tests_revised.md",
        "05_security_revised.md",
        "08_final_review.md",
        "24_experience_context.md",
    )
    artifacts: dict[str, str] = {}
    for filename in filenames:
        path = run_dir / filename
        if path.exists():
            artifacts[filename] = path.read_text(encoding="utf-8")
        else:
            warnings.append(f"missing_artifact:{filename}")
            artifacts[filename] = ""
    summary_path = run_dir / SUMMARY_FILE
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary = payload
        except json.JSONDecodeError:
            warnings.append("invalid_summary_json")
    else:
        warnings.append("missing_summary_json")
    all_text = "\n\n".join(artifacts.values())
    return {"artifacts": artifacts, "summary": summary, "all_text": all_text}


def _render_report(evaluations: list[PatchQualityEvaluation]) -> str:
    blocks: list[str] = []
    for evaluation in evaluations:
        blocks.extend(
            [
                "PATCH",
                evaluation.patch_name,
                "",
                "QUALITY",
                evaluation.quality,
                "",
                "SCORE",
                str(evaluation.score),
                "",
                "REASONS",
            ]
        )
        blocks.extend(f"- {reason}" for reason in (evaluation.reasons or ["No quality reasons recorded."]))
        blocks.extend(["", "CONFIDENCE", "High", ""])
    return "\n".join(blocks).strip()


def _score(
    *,
    real_implementation: bool,
    architecture_connected: bool,
    memory_reused: bool,
    tests_generated: bool,
    source_aware: bool,
    no_placeholders: bool,
    comment_only: bool,
    disconnected: bool,
) -> int:
    score = 0
    if real_implementation:
        score += 40
    if architecture_connected:
        score += 25
    if memory_reused:
        score += 10
    if tests_generated:
        score += 10
    if source_aware:
        score += 10
    if no_placeholders:
        score += 5
    if comment_only:
        score -= 60
    if disconnected:
        score -= 40
    return max(0, min(100, score))


def _semantic_penalties(
    *,
    patch_text: str,
    target_paths: list[str],
    tests_generated: bool,
) -> list[_SemanticPenalty]:
    penalties: list[_SemanticPenalty] = []
    bottom_imports = _bottom_import_paths(patch_text)
    if bottom_imports:
        penalties.append(
            _SemanticPenalty(
                code="bottom_imports_detected",
                reason=f"Imports were added below executable code in: {', '.join(bottom_imports)}.",
                points=20,
            )
        )
    disconnected_services = _disconnected_created_services(patch_text)
    if disconnected_services:
        penalties.append(
            _SemanticPenalty(
                code="created_service_not_connected",
                reason="Created service code is not called by an API route, handler, or existing layer.",
                points=25,
            )
        )
    route_without_service = _routes_without_service_calls(patch_text)
    if route_without_service:
        penalties.append(
            _SemanticPenalty(
                code="route_without_service_call",
                reason=f"Route handler was added without calling the proposed service layer: {', '.join(route_without_service)}.",
                points=25,
            )
        )
    trivial_tests = _trivial_test_paths(patch_text, target_paths) if tests_generated else []
    if trivial_tests:
        penalties.append(
            _SemanticPenalty(
                code="trivial_tests_detected",
                reason=f"Generated tests look trivial or disconnected from behavior: {', '.join(trivial_tests)}.",
                points=15,
            )
        )
    return penalties


def _diff_files(patch_text: str) -> list[_DiffFile]:
    files: list[_DiffFile] = []
    old_path = ""
    new_path = ""
    added_lines: list[str] = []
    context_lines: list[str] = []
    is_created = False

    def flush() -> None:
        nonlocal old_path, new_path, added_lines, context_lines, is_created
        path = new_path or old_path
        if path:
            files.append(
                _DiffFile(
                    path=path,
                    added_lines=added_lines,
                    context_lines=context_lines,
                    is_created=is_created,
                )
            )
        old_path = ""
        new_path = ""
        added_lines = []
        context_lines = []
        is_created = False

    for line in patch_text.splitlines():
        if line.startswith("--- "):
            flush()
            raw_old = line[4:].strip()
            old_path = _normalize_diff_path(raw_old)
            is_created = raw_old.split("\t", 1)[0].strip() == "/dev/null"
        elif line.startswith("+++ "):
            new_path = _normalize_diff_path(line[4:].strip())
        elif new_path:
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
            elif line.startswith(" ") and line.strip():
                context_lines.append(line[1:])
    flush()
    return files


def _bottom_import_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for diff_file in _diff_files(patch_text):
        executable_seen = False
        for line in [*diff_file.context_lines, *diff_file.added_lines]:
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", '"""', "'''")):
                continue
            if IMPORT_LINE.search(stripped):
                if executable_seen:
                    paths.append(diff_file.path)
                continue
            if _is_functional_line(line) and not stripped.startswith("@"):
                executable_seen = True
    return _dedupe(paths)


def _disconnected_created_services(patch_text: str) -> list[str]:
    files = _diff_files(patch_text)
    created_service_files = [
        diff_file for diff_file in files if diff_file.is_created and SERVICE_PATH_PATTERN.search(diff_file.path)
    ]
    if not created_service_files:
        return []
    non_service_added = "\n".join(
        line
        for diff_file in files
        if diff_file not in created_service_files and not _is_test_path(diff_file.path)
        for line in diff_file.added_lines
    )
    disconnected: list[str] = []
    for diff_file in created_service_files:
        names = _defined_names(diff_file.added_lines)
        if not names or not any(_references_name(non_service_added, name) for name in names):
            disconnected.append(diff_file.path)
    return _dedupe(disconnected)


def _routes_without_service_calls(patch_text: str) -> list[str]:
    files = _diff_files(patch_text)
    service_names = {
        name
        for diff_file in files
        if SERVICE_PATH_PATTERN.search(diff_file.path)
        for name in _defined_names(diff_file.added_lines)
    }
    if not service_names:
        return []
    weak_routes: list[str] = []
    for diff_file in files:
        added_text = "\n".join(diff_file.added_lines)
        is_route = any(ROUTE_DECORATOR_LINE.search(line.strip()) for line in diff_file.added_lines) or any(
            token in diff_file.path.lower() for token in ("routes/", "api/")
        )
        if is_route and not any(_references_name(added_text, name) for name in service_names):
            weak_routes.append(diff_file.path)
    return _dedupe(weak_routes)


def _trivial_test_paths(patch_text: str, target_paths: list[str]) -> list[str]:
    trivial: list[str] = []
    files = _diff_files(patch_text)
    for diff_file in files:
        if not _is_test_path(diff_file.path):
            continue
        functional_lines = [line for line in diff_file.added_lines if _is_functional_line(line)]
        assert_lines = [line for line in functional_lines if line.strip().startswith("assert ")]
        has_behavior_call = any(_looks_like_behavior_test_line(line) for line in functional_lines)
        if functional_lines and (not assert_lines or not has_behavior_call):
            trivial.append(diff_file.path)
    return _dedupe(trivial)


def _is_test_path(path: str) -> bool:
    return bool(TEST_PATH_PATTERN.search(path.replace("\\", "/")))


def _defined_names(lines: list[str]) -> list[str]:
    return _dedupe(match.group(1) for line in lines if (match := DEF_LINE.search(line)))


def _references_name(text: str, name: str) -> bool:
    return bool(re.search(rf"\b{re.escape(name)}\s*\(", text))


def _looks_like_behavior_test_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("def test_", "async def test_", "@")):
        return False
    if TRIVIAL_ASSERT_PATTERN.search(stripped):
        return False
    behavior_markers = (
        "client.",
        "TestClient",
        "pytest.raises",
        "response.",
        "status_code",
        ".get(",
        ".post(",
        ".put(",
        ".patch(",
        ".delete(",
    )
    if any(marker in stripped for marker in behavior_markers):
        return True
    return bool(re.search(r"\b[a-z_][A-Za-z0-9_]*\s*\(", stripped))


def _target_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for match in DIFF_PATH_LINE.finditer(patch_text):
        normalized = _normalize_diff_path(match.group(1))
        if normalized:
            paths.append(normalized)
    return _dedupe(paths)


def _normalize_diff_path(path_text: str) -> str:
    text = path_text.strip().strip('"').strip("'")
    if "\t" in text:
        text = text.split("\t", 1)[0]
    if text.startswith(("a/", "b/")):
        text = text[2:]
    return "" if text in {"old", "new", "/dev/null"} else text


def _added_lines(patch_text: str) -> list[str]:
    return [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _is_functional_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if COMMENT_ONLY_PATTERN.search(stripped):
        return False
    return True


def _is_source_aware(patch_text: str) -> bool:
    lines = patch_text.splitlines()
    if len(lines) < 5:
        return False
    if lines[0].strip() == "--- /dev/null" and lines[1].startswith("+++ b/"):
        return bool(re.search(r"(?m)^@@\s+-0,0\s+\+1,\d+\s+@@", patch_text)) and any(
            line.startswith("+") and not line.startswith("+++") and line.strip() for line in lines[3:]
        )
    if not lines[0].startswith("--- a/") or not lines[1].startswith("+++ b/"):
        return False
    return bool(HUNK_LINE.search(patch_text)) and any(
        line.startswith(" ") and line.strip() for line in lines
    )


def _architecture_connected(target_paths: list[str], patch_text: str, context: dict[str, Any]) -> bool:
    combined = context.get("all_text", "").lower()
    if any(path.lower() in combined for path in target_paths):
        return True
    if _tests_generated(target_paths, patch_text):
        return True
    lowered = patch_text.lower()
    if "@app." in patch_text or "@router." in patch_text:
        return True
    domain_tokens = {"auth", "password", "reset", "rate", "limit", "pagination", "page", "route", "fastapi"}
    patch_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", lowered))
    context_tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", combined))
    return bool((patch_tokens & domain_tokens) and (patch_tokens & context_tokens & domain_tokens))


def _tests_generated(target_paths: list[str], patch_text: str) -> bool:
    return any(path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_") for path in target_paths) or "+def test_" in patch_text


def _memory_reused(patch_text: str, context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if isinstance(summary, dict) and summary.get("execution_memory_used") is True:
        return True
    experience = context.get("artifacts", {}).get("24_experience_context.md", "")
    constants = re.findall(r"(?m)^\s*-\s*([A-Z_]+=\d+)\s*$", experience)
    return any(constant in patch_text for constant in constants)


def _disconnected_logic(
    patch_text: str,
    context: dict[str, Any],
    target_paths: list[str],
    architecture_connected: bool,
    tests_generated: bool,
) -> bool:
    if tests_generated or "@app." in patch_text or "@router." in patch_text:
        return False
    added_names = [match.group(1) for line in _added_lines(patch_text) if (match := DEF_LINE.search(line))]
    if not added_names:
        return False
    context_text = context.get("all_text", "")
    non_def_added = "\n".join(
        line for line in _added_lines(patch_text) if not DEF_LINE.search(line)
    )
    referenced = any(
        re.search(rf"\b{re.escape(name)}\b", context_text)
        or re.search(rf"\b{re.escape(name)}\s*\(", non_def_added)
        for name in added_names
    )
    target_text = " ".join(target_paths).lower()
    reusable_domain_file = any(token in target_text for token in ("auth", "guard", "service", "middleware", "pagination", "route"))
    return not referenced and not (architecture_connected and reusable_domain_file)


def _target_selection_selected(target_paths: list[str], context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_target_selection_used") is not True:
        return False
    selected = {str(path) for path in summary.get("execution_selected_targets", []) if path}
    return bool(selected & set(target_paths))


def _target_selection_rejected(target_paths: list[str], context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_target_selection_used") is not True:
        return False
    rejected = {str(path) for path in summary.get("execution_rejected_targets", []) if path}
    return bool(rejected & set(target_paths))


def _multifile_planned(target_paths: list[str], context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_multifile_plan_used") is not True:
        return False
    planned = {str(path) for path in summary.get("execution_multifile_selected_files", []) if path}
    return bool(planned & set(target_paths))


def _multifile_unplanned(target_paths: list[str], context: dict[str, Any]) -> bool:
    if _layer_creation_planned(target_paths, context):
        return False
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_multifile_plan_used") is not True:
        return False
    planned = {str(path) for path in summary.get("execution_multifile_selected_files", []) if path}
    if not planned or not target_paths:
        return False
    return not bool(planned & set(target_paths))


def _is_creation_patch(patch_text: str) -> bool:
    return patch_text.splitlines()[:1] == ["--- /dev/null"]


def _layer_creation_planned(target_paths: list[str], context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_layer_creation_used") is not True:
        return False
    planned = {str(path) for path in summary.get("execution_layer_proposed_files", []) if path}
    return bool(planned & set(target_paths))


def _multifile_missing_layers_documented(context: dict[str, Any]) -> bool:
    summary = context.get("summary", {})
    if not isinstance(summary, dict) or summary.get("execution_multifile_plan_used") is not True:
        return False
    missing = summary.get("execution_multifile_missing_layers", [])
    return isinstance(missing, list) and bool(missing)


def _needs_relocation(target_paths: list[str], patch_text: str, context: dict[str, Any] | None = None) -> bool:
    if context and _target_selection_selected(target_paths, context):
        return False
    target_text = " ".join(target_paths).lower()
    lowered = patch_text.lower()
    if ("password_reset_rate_limit" in lowered or "rate_limit" in lowered) and not any(
        token in target_text for token in ("auth", "password", "reset", "rate", "limit", "middleware", "service", "guard")
    ):
        return True
    if ("require_permission" in lowered or "record_failed_login" in lowered) and not any(
        token in target_text for token in ("auth", "guard", "permission", "session", "login")
    ):
        return True
    if ("paginate_items" in lowered or "next_cursor" in lowered) and not any(
        token in target_text for token in ("pagination", "catalog", "search", "product", "route", "api")
    ):
        return True
    return False


def _protected_path_errors(target_paths: list[str], project_root: Path) -> list[str]:
    errors: list[str] = []
    policy = load_filesystem_policy(project_root=project_root)
    protected_parts = {"outputs", "knowledge", "memory", "models", ".git"}
    protected_prefixes = (Path("training/datasets"), Path("training/adapters"))
    for path_text in target_paths:
        if WINDOWS_C_PATH_PATTERN.search(path_text) or path_text.lower().startswith("/mnt/c"):
            errors.append("forbidden_c_path_present")
            continue
        relative = Path(path_text)
        if set(relative.parts) & protected_parts:
            errors.append(f"protected_path_modified:{path_text}")
        for prefix in protected_prefixes:
            try:
                relative.relative_to(prefix)
                errors.append(f"protected_path_modified:{path_text}")
            except ValueError:
                pass
        for error in policy.validate_patch_target(path_text):
            if error == "forbidden_c_path_present":
                errors.append(error)
            elif error.startswith(("protected_path_modified:", "blocked_path:", "path_traversal_present:")):
                errors.append(error)
    return _dedupe(errors)


def _aggregate_decision(evaluations: list[PatchQualityEvaluation]) -> str:
    if not evaluations:
        return REJECTED
    return min(evaluations, key=lambda item: QUALITY_ORDER.get(item.quality, 0)).quality


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
