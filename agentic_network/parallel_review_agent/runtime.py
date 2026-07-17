"""Deterministic local multi-agent parallel review.

v7.0 reviews existing run artifacts and patches without executing commands,
applying patches, mutating approvals, loading models, or reading protected
project areas. The only writes are the two 37_parallel_review artifacts inside
the selected run directory.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
MARKDOWN_ARTIFACT = "37_parallel_review.md"
JSON_ARTIFACT = "37_parallel_review.json"

REVIEWERS = (
    "architecture_review",
    "security_review",
    "test_review",
    "patch_quality_review",
    "integration_review",
)
PROTECTED_PATH_PATTERN = re.compile(
    r"(?i)(?:^|/)(?:\.git|models|memory|knowledge|unsloth_compiled_cache)(?:/|$)|"
    r"(?:^|/)training/(?:datasets|adapters)(?:/|$)|"
    r"(?:^|/)outputs/(?!runs/[^/]+(?:/|$))|"
    r"(?:^|[\s:+-])(?:c:[\\/]|/mnt/c\b)"
)
DANGEROUS_PATTERN = re.compile(
    r"(?i)\b(?:rm\s+-rf|del\s+/s|format\b|mkfs\b|curl\b|wget\b|git\s+push|"
    r"git\s+pull|git\s+clone|pip\s+install|conda\s+install|npm\s+install|"
    r"powershell\b|cmd\.exe\b|bash\s+-c|sh\s+-c|subprocess\b|os\.system\b|"
    r"shell\s*=\s*True)\b"
)
DIFF_PATH_LINE = re.compile(r"^(?:---|\+\+\+)\s+(.+?)\s*$")


@dataclass(frozen=True)
class ReviewerResult:
    name: str
    status: str
    decision: str
    confidence: str
    findings: list[str]
    warnings: list[str]
    evidence: list[str]


@dataclass(frozen=True)
class ParallelReviewResult:
    status: str
    decision: str
    confidence: str
    agent_results: dict[str, dict[str, object]]
    blocking_findings: list[str]
    warnings: list[str]
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]
    consensus_summary: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_parallel_review(
    run_dir: str | Path,
    max_workers: int = 5,
    *,
    runs_root: str | Path | None = None,
) -> ParallelReviewResult:
    """Run independent local review tasks and write consolidated artifacts."""

    custom_runs_root = runs_root is not None
    validation_errors, validation_warnings, resolved_run_dir = _validate_run_dir(
        run_dir,
        runs_root=Path(runs_root).resolve() if runs_root is not None else DEFAULT_RUNS_ROOT,
        custom_runs_root=custom_runs_root,
    )
    if validation_errors or resolved_run_dir is None:
        return ParallelReviewResult(
            status="INVALID",
            decision="BLOCKED",
            confidence="Low",
            agent_results={},
            blocking_findings=validation_errors,
            warnings=[],
            artifacts=[],
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            consensus_summary="Parallel review did not run because the run directory failed validation.",
        )

    context = _load_context(resolved_run_dir)
    reviewer_functions: dict[str, Callable[[dict[str, str]], ReviewerResult]] = {
        "architecture_review": _architecture_review,
        "security_review": _security_review,
        "test_review": _test_review,
        "patch_quality_review": _patch_quality_review,
        "integration_review": _integration_review,
    }
    worker_count = max(1, min(max_workers, len(reviewer_functions)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            name: executor.submit(reviewer, context)
            for name, reviewer in reviewer_functions.items()
        }
    ordered_results = {name: futures[name].result() for name in REVIEWERS}
    result = _aggregate_results(
        run_dir=resolved_run_dir,
        reviewer_results=ordered_results,
        validation_warnings=validation_warnings,
    )
    _write_artifacts(resolved_run_dir, result)
    return result


def _validate_run_dir(
    run_dir: str | Path,
    *,
    runs_root: Path,
    custom_runs_root: bool,
) -> tuple[list[str], list[str], Path | None]:
    errors: list[str] = []
    warnings: list[str] = []
    text = str(run_dir).strip().strip('"').strip("'")
    if not text:
        return ["run_dir_missing"], warnings, None
    if ".." in text.replace("\\", "/").split("/"):
        return ["run_dir_path_traversal_blocked"], warnings, None
    if not custom_runs_root and re.match(r"(?i)^(?:c:[\\/]|/mnt/c\b)", text):
        errors.append("run_dir_c_drive_blocked")
    candidate = Path(text)
    if not candidate.is_absolute():
        normalized_text = text.replace("\\", "/")
        if normalized_text.startswith("outputs/runs/"):
            candidate = REPO_ROOT / candidate
        else:
            candidate = runs_root / candidate
    resolved = candidate.resolve()
    root = runs_root.resolve()
    if not _is_relative_to(resolved, root):
        errors.append("run_dir_must_be_inside_outputs_runs")
    if any(part.lower() in {".git", "models", "training", "memory", "knowledge", "unsloth_compiled_cache"} for part in resolved.parts):
        errors.append("run_dir_protected_path_blocked")
    if not resolved.exists() or not resolved.is_dir():
        errors.append("run_dir_missing")
    if not (resolved / "summary.json").exists():
        warnings.append("summary_json_missing")
    return _dedupe(errors), _dedupe(warnings), resolved if not errors else None


def _load_context(run_dir: Path) -> dict[str, str]:
    artifacts = {
        "summary": _read_text(run_dir / "summary.json"),
        "architecture": _read_text(run_dir / "02_architecture_plan.md"),
        "security": _read_text(run_dir / "05_security.md") or _read_text(run_dir / "05_security_revised.md"),
        "tests": _read_text(run_dir / "04_tests.md") or _read_text(run_dir / "04_tests_revised.md"),
        "test_run": _read_text(run_dir / "14_test_run.md"),
        "patch_quality": _read_text(run_dir / "25_patch_quality.md"),
        "patch_approval": _read_text(run_dir / "12_patch_approval.md"),
        "patch_apply": _read_text(run_dir / "13_patch_apply.md"),
        "autonomous_loop": _read_text(run_dir / "27_autonomous_loop.md"),
        "merge_readiness": _read_text(run_dir / "15_merge_readiness.md"),
        "patches": _read_patches(run_dir),
    }
    return artifacts


def _architecture_review(context: dict[str, str]) -> ReviewerResult:
    findings: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    text = context["architecture"]
    if not text:
        warnings.append("Architecture plan artifact is missing.")
    else:
        evidence.append("02_architecture_plan.md present.")
    if _contains_blocking_language(text):
        findings.append("Architecture artifact contains blocking or unsafe language.")
    if "TODO" in text or "placeholder" in text.lower():
        warnings.append("Architecture plan still contains placeholder language.")
    return _reviewer_result("architecture_review", findings, warnings, evidence)


def _security_review(context: dict[str, str]) -> ReviewerResult:
    findings: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    combined = "\n".join([context["security"], context["patches"]])
    if context["security"]:
        evidence.append("05_security.md present.")
    else:
        warnings.append("Security artifact is missing.")
    if PROTECTED_PATH_PATTERN.search(combined):
        findings.append("Protected path, C drive, or forbidden outputs path detected.")
    if DANGEROUS_PATTERN.search(combined):
        findings.append("Dangerous command or shell/network/install construct detected.")
    return _reviewer_result("security_review", findings, warnings, evidence)


def _test_review(context: dict[str, str]) -> ReviewerResult:
    findings: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    if context["tests"]:
        evidence.append("04_tests.md present.")
    else:
        warnings.append("Test plan artifact is missing.")
    test_text = "\n".join([context["tests"], context["test_run"]])
    if "FAILED_TESTS" in test_text or re.search(r"(?i)\bfailed\b", context["test_run"]):
        findings.append("Test runner artifact reports failed tests.")
    if not context["test_run"]:
        warnings.append("No executed test run artifact was found.")
    return _reviewer_result("test_review", findings, warnings, evidence)


def _patch_quality_review(context: dict[str, str]) -> ReviewerResult:
    findings: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    text = context["patch_quality"]
    if text:
        evidence.append("25_patch_quality.md present.")
    else:
        warnings.append("Patch Quality artifact is missing.")
    if any(decision in text for decision in ("REJECTED", "LOW_VALUE_COMMENT_ONLY", "UNCONNECTED_LOGIC")):
        findings.append("Patch Quality reports a blocking or unconnected patch decision.")
    elif any(decision in text for decision in ("NEEDS_REVISION", "NEEDS_RELOCATION")):
        warnings.append("Patch Quality reports a non-blocking revision concern.")
    return _reviewer_result("patch_quality_review", findings, warnings, evidence)


def _integration_review(context: dict[str, str]) -> ReviewerResult:
    findings: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    integration_text = "\n".join(
        [
            context["patch_approval"],
            context["patch_apply"],
            context["autonomous_loop"],
            context["merge_readiness"],
        ]
    )
    if integration_text:
        evidence.append("Integration artifacts present.")
    else:
        warnings.append("No approval/apply/loop/merge integration artifacts were found.")
    if "FAILED_PERMANENTLY" in integration_text or "BLOCKED" in integration_text:
        findings.append("Integration stage reports BLOCKED or FAILED_PERMANENTLY.")
    if "FAILED_TESTS" in integration_text:
        findings.append("Integration stage reports failed tests.")
    return _reviewer_result("integration_review", findings, warnings, evidence)


def _reviewer_result(
    name: str,
    findings: list[str],
    warnings: list[str],
    evidence: list[str],
) -> ReviewerResult:
    if findings:
        decision = "BLOCKED"
        confidence = "High"
    elif warnings:
        decision = "NEEDS_REVISION"
        confidence = "Medium"
    else:
        decision = "APPROVED"
        confidence = "High"
    return ReviewerResult(
        name=name,
        status="VALID",
        decision=decision,
        confidence=confidence,
        findings=_dedupe(findings),
        warnings=_dedupe(warnings),
        evidence=_dedupe(evidence),
    )


def _aggregate_results(
    *,
    run_dir: Path,
    reviewer_results: dict[str, ReviewerResult],
    validation_warnings: list[str],
) -> ParallelReviewResult:
    blocking_findings = _dedupe(
        finding
        for result in reviewer_results.values()
        for finding in result.findings
    )
    warnings = _dedupe(
        warning
        for result in reviewer_results.values()
        for warning in result.warnings
    )
    if blocking_findings:
        decision = "BLOCKED"
        confidence = "High"
    elif warnings:
        decision = "NEEDS_REVISION"
        confidence = "Medium"
    else:
        decision = "APPROVED"
        confidence = "High"
    agent_payload = {name: asdict(result) for name, result in reviewer_results.items()}
    consensus = _consensus_summary(decision, blocking_findings, warnings, agent_payload)
    return ParallelReviewResult(
        status="VALID",
        decision=decision,
        confidence=confidence,
        agent_results=agent_payload,
        blocking_findings=blocking_findings,
        warnings=warnings,
        artifacts=[
            str((run_dir / MARKDOWN_ARTIFACT).resolve()),
            str((run_dir / JSON_ARTIFACT).resolve()),
        ],
        validation_errors=[],
        validation_warnings=validation_warnings,
        consensus_summary=consensus,
    )


def _write_artifacts(run_dir: Path, result: ParallelReviewResult) -> None:
    json_path = run_dir / JSON_ARTIFACT
    markdown_path = run_dir / MARKDOWN_ARTIFACT
    json_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")


def _render_markdown(result: ParallelReviewResult) -> str:
    lines = [
        "# ANN Parallel Review",
        "",
        "## Decision",
        f"- Decision: {result.decision}",
        f"- Confidence: {result.confidence}",
        f"- Status: {result.status}",
        "",
        "## Consensus Summary",
        result.consensus_summary,
        "",
        "## Blocking Findings",
    ]
    lines.extend(f"- {item}" for item in result.blocking_findings or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in result.warnings or ["None"])
    lines.extend(["", "## Agent Results"])
    for name, payload in result.agent_results.items():
        lines.extend(
            [
                f"### {name}",
                f"- Decision: {payload['decision']}",
                f"- Confidence: {payload['confidence']}",
                f"- Findings: {', '.join(payload['findings']) if payload['findings'] else 'None'}",
                f"- Warnings: {', '.join(payload['warnings']) if payload['warnings'] else 'None'}",
                f"- Evidence: {', '.join(payload['evidence']) if payload['evidence'] else 'None'}",
                "",
            ]
        )
    lines.extend(["## Validation", f"- Errors: {result.validation_errors or ['None']}", f"- Warnings: {result.validation_warnings or ['None']}", ""])
    return "\n".join(lines)


def _consensus_summary(
    decision: str,
    blocking_findings: list[str],
    warnings: list[str],
    agent_results: dict[str, dict[str, object]],
) -> str:
    approved = [name for name, result in agent_results.items() if result["decision"] == "APPROVED"]
    revision = [name for name, result in agent_results.items() if result["decision"] == "NEEDS_REVISION"]
    blocked = [name for name, result in agent_results.items() if result["decision"] == "BLOCKED"]
    return (
        f"Parallel reviewers reached {decision}. "
        f"Approved reviewers: {', '.join(approved) or 'none'}. "
        f"Revision reviewers: {', '.join(revision) or 'none'}. "
        f"Blocked reviewers: {', '.join(blocked) or 'none'}. "
        f"Blocking findings: {len(blocking_findings)}. Warnings: {len(warnings)}."
    )


def _contains_blocking_language(text: str) -> bool:
    return bool(re.search(r"(?i)\b(blocked|unsafe|dangerous|do not apply|must not apply)\b", text))


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file() or not _safe_run_child(path):
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_patches(run_dir: Path) -> str:
    patches_dir = run_dir / "patches"
    if not patches_dir.exists() or not patches_dir.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(patches_dir.glob("*.diff")) + sorted(patches_dir.glob("*.patch")):
        if _safe_run_child(path):
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(chunks)


def _safe_run_child(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return not bool(parts & {".git", "models", "training", "memory", "knowledge", "unsloth_compiled_cache"})


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe(values) -> list[str]:
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
