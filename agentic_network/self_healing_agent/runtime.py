"""Self Healing Agent runtime.

This stage reads failed test-run artifacts and writes a safe retry patch proposal
when the failure is a narrow deterministic case. It never applies patches,
executes commands, executes tests, runs models, or modifies repository sources.
"""

from __future__ import annotations

import ast
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import load_filesystem_policy

SUMMARY_FILE = "summary.json"
FAILURE_ANALYSIS_FILE = "17_failure_analysis.md"
ROOT_CAUSE_FILE = "18_root_cause.md"
SELF_HEALING_FILE = "21_self_healing.md"
RETRY_PATCH_TEMPLATE = "19_retry_patch_{attempt:03d}.diff"

STATUS_SKIPPED = "SKIPPED"
STATUS_NO_FAILURE_DETECTED = "NO_FAILURE_DETECTED"
STATUS_RETRY_PATCH_GENERATED = "RETRY_PATCH_GENERATED"
STATUS_FAILED_ANALYSIS = "FAILED_ANALYSIS"
STATUS_FAILED_PERMANENTLY = "FAILED_PERMANENTLY"

FAILED_TEST_STATUSES = {"FAILED", "TIMEOUT"}
NON_FAILURE_TEST_STATUSES = {"PASSED", "NO_TESTS_DETECTED"}
SKIPPED_TEST_STATUSES = {"SKIPPED"}

DANGEROUS_TEXT_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\()"
)
DIFF_PATH_LINE = re.compile(r"(?m)^\s*(?:---|\+\+\+)\s+(.+?)\s*$")
NAME_ERROR_PATTERN = re.compile(
    r"NameError:\s+name ['\"](?P<symbol>[A-Za-z_][A-Za-z0-9_]*)['\"] is not defined"
)
IMPORT_ERROR_PATTERN = re.compile(r"\b(?:ImportError|ModuleNotFoundError):\s*(?P<message>.+)")
ASSERTION_ERROR_PATTERN = re.compile(r"\bAssertionError(?::\s*(?P<message>.*))?")
SYNTAX_ERROR_PATTERN = re.compile(r"\bSyntaxError:\s*(?P<message>.+)")
PYTHON_TRACEBACK_FILE_PATTERN = re.compile(r'File "([^"]+\.py)"')
UPPERCASE_CONSTANT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
MEMORY_CONSTANT_PATTERN = re.compile(
    r"(?im)^\s*[-*]?\s*(?P<key>WINDOW_SECONDS|MAX_ATTEMPTS|THRESHOLD|LIMIT)\s*=\s*(?P<value>\d+)\s*$"
)


@dataclass(frozen=True)
class FailureSignal:
    """Parsed test failure signal used by self-healing synthesis."""

    error_type: str
    message: str
    missing_symbol: str = ""
    location: str = ""


@dataclass(frozen=True)
class SelfHealingResult:
    """Structured result for a single self-healing attempt."""

    run_dir: str
    status: str
    attempts: int
    max_attempts: int
    failure_analysis_path: str
    root_cause_path: str
    self_healing_path: str
    retry_patch_path: str
    last_error: str
    validation_errors: list[str]
    validation_warnings: list[str]
    artifacts: list[str]
    failure_signal: FailureSignal | None
    report: str
    memory_used: bool = False
    memory_pattern_used: str = ""

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def run_self_healing(run_dir: Path, max_attempts: int = 5) -> SelfHealingResult:
    """Analyze a failed Test Runner result and write one retry patch proposal if safe."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    artifacts: list[str] = []
    summary = _load_summary(resolved_run_dir, warnings)
    experience_context = _load_experience_context(resolved_run_dir)
    memory_constants = _memory_constant_values(experience_context)
    memory_pattern = _memory_pattern_used(experience_context)
    memory_used = False
    previous_attempts = _int_value(summary.get("self_healing_attempts"), 0)
    test_status = _normalize_status(summary.get("test_runner_status"))

    if max_attempts <= 0:
        errors.append("max_attempts_invalid")
        status = STATUS_FAILED_PERMANENTLY
        attempts = previous_attempts
        signal = None
        retry_patch_path = ""
        analysis = _render_failure_analysis(None, "Max attempts value is invalid.", "Unknown")
        root_cause = _render_root_cause(None, "Self-healing cannot run with invalid max attempts.", "None")
    elif test_status in SKIPPED_TEST_STATUSES:
        status = STATUS_SKIPPED
        attempts = previous_attempts
        signal = None
        retry_patch_path = ""
        analysis = _render_failure_analysis(None, "Test Runner was skipped.", "High")
        root_cause = _render_root_cause(None, "No failed test output is available.", "No retry patch.")
    elif test_status in NON_FAILURE_TEST_STATUSES:
        status = STATUS_NO_FAILURE_DETECTED
        attempts = previous_attempts
        signal = None
        retry_patch_path = ""
        analysis = _render_failure_analysis(None, f"Test Runner status is {test_status}.", "High")
        root_cause = _render_root_cause(None, "No failing test signal was detected.", "No retry patch.")
    elif previous_attempts >= max_attempts:
        status = STATUS_FAILED_PERMANENTLY
        attempts = previous_attempts
        signal = None
        retry_patch_path = ""
        errors.append("self_healing_max_attempts_reached")
        analysis = _render_failure_analysis(None, "Maximum self-healing attempts reached.", "High")
        root_cause = _render_root_cause(None, "Retry budget is exhausted.", "No retry patch.")
    elif test_status in FAILED_TEST_STATUSES:
        attempts = previous_attempts + 1
        failure_text = _load_failure_text(resolved_run_dir, summary, warnings)
        signal = analyze_failure(failure_text, forced_timeout=test_status == "TIMEOUT")
        patch_text = ""
        retry_patch_path = ""
        if signal is None:
            errors.append("failure_signal_unrecognized")
            status = STATUS_FAILED_ANALYSIS
            analysis = _render_failure_analysis(None, failure_text, "Low")
            root_cause = _render_root_cause(None, "Failure pattern is not supported in v1.", "No retry patch.")
        else:
            analysis = _render_failure_analysis(signal, failure_text, "High")
            root_cause = _render_root_cause(
                signal,
                _root_cause_summary(signal),
                _safe_fix_strategy(signal),
            )
            patch_text, synthesis_warnings = synthesize_retry_patch(
                run_dir=resolved_run_dir,
                signal=signal,
                attempt=attempts,
                memory_constants=memory_constants,
            )
            memory_used = bool(patch_text and _memory_value_for_symbol(signal.missing_symbol, memory_constants) is not None)
            warnings.extend(synthesis_warnings)
            if patch_text:
                validation_errors = validate_retry_patch(patch_text, project_root=_project_root())
                errors.extend(validation_errors)
                if not validation_errors:
                    retry_patch = resolved_run_dir / RETRY_PATCH_TEMPLATE.format(attempt=attempts)
                    retry_patch.write_text(patch_text.rstrip() + "\n", encoding="utf-8")
                    retry_patch_path = str(retry_patch)
                    artifacts.append(retry_patch_path)
                    status = STATUS_RETRY_PATCH_GENERATED
                else:
                    status = STATUS_FAILED_ANALYSIS
            else:
                status = STATUS_FAILED_ANALYSIS
    else:
        status = STATUS_NO_FAILURE_DETECTED
        attempts = previous_attempts
        signal = None
        retry_patch_path = ""
        analysis = _render_failure_analysis(None, f"Test Runner status is {test_status or 'UNKNOWN'}.", "High")
        root_cause = _render_root_cause(None, "No failed test signal was detected.", "No retry patch.")

    failure_analysis_path = resolved_run_dir / FAILURE_ANALYSIS_FILE
    root_cause_path = resolved_run_dir / ROOT_CAUSE_FILE
    self_healing_path = resolved_run_dir / SELF_HEALING_FILE
    failure_analysis_path.write_text(analysis.rstrip() + "\n", encoding="utf-8")
    root_cause_path.write_text(root_cause.rstrip() + "\n", encoding="utf-8")
    artifacts.extend([str(failure_analysis_path), str(root_cause_path), str(self_healing_path)])
    report = _render_self_healing_report(
        status=status,
        retry_patch_path=retry_patch_path,
        errors=_dedupe(errors),
        warnings=_dedupe(warnings),
        signal=signal,
    )
    self_healing_path.write_text(report.rstrip() + "\n", encoding="utf-8")

    result = SelfHealingResult(
        run_dir=str(resolved_run_dir),
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        failure_analysis_path=str(failure_analysis_path),
        root_cause_path=str(root_cause_path),
        self_healing_path=str(self_healing_path),
        retry_patch_path=retry_patch_path,
        last_error=_last_error(signal, errors),
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
        artifacts=_dedupe(artifacts),
        failure_signal=signal,
        report=report,
        memory_used=memory_used,
        memory_pattern_used=memory_pattern if memory_used else "",
    )
    _update_summary(resolved_run_dir, result)
    return result


def analyze_failure(content: str, *, forced_timeout: bool = False) -> FailureSignal | None:
    """Parse known failure patterns from captured test output."""

    if forced_timeout or "TIMEOUT" in content.upper() or "TimeoutExpired" in content:
        return FailureSignal("Timeout", "Test execution timed out.", location=_extract_location(content))
    match = NAME_ERROR_PATTERN.search(content)
    if match:
        symbol = match.group("symbol")
        return FailureSignal(
            "NameError",
            f"name '{symbol}' is not defined",
            missing_symbol=symbol,
            location=_extract_location(content),
        )
    match = IMPORT_ERROR_PATTERN.search(content)
    if match:
        return FailureSignal("ImportError", match.group("message").strip(), location=_extract_location(content))
    match = SYNTAX_ERROR_PATTERN.search(content)
    if match:
        return FailureSignal("SyntaxError", match.group("message").strip(), location=_extract_location(content))
    match = ASSERTION_ERROR_PATTERN.search(content)
    if match:
        return FailureSignal("AssertionError", (match.group("message") or "").strip(), location=_extract_location(content))
    return None


def synthesize_retry_patch(
    *,
    run_dir: Path,
    signal: FailureSignal,
    attempt: int,
    memory_constants: dict[str, int] | None = None,
) -> tuple[str, list[str]]:
    """Generate a retry patch only for deterministic v1-safe cases."""

    warnings: list[str] = []
    if signal.error_type != "NameError":
        warnings.append(f"unsupported_retry_synthesis:{signal.error_type}")
        return "", warnings
    symbol = signal.missing_symbol
    if not UPPERCASE_CONSTANT_PATTERN.match(symbol):
        warnings.append("missing_symbol_not_uppercase_constant")
        return "", warnings
    value = _constant_value(symbol, memory_constants=memory_constants)
    if value is None:
        warnings.append("missing_constant_value_not_deterministic")
        return "", warnings
    target = _select_constant_target(run_dir, signal)
    if target is None:
        warnings.append("safe_config_target_not_found")
        return "", warnings
    patch = _build_constant_patch(target, symbol, value)
    if not patch:
        warnings.append("retry_patch_not_synthesized")
    return patch, warnings


def validate_retry_patch(patch_text: str, *, project_root: Path) -> list[str]:
    """Validate that a retry patch is reviewable and safe to store."""

    errors: list[str] = []
    if not patch_text.strip():
        return ["retry_patch_empty"]
    if DANGEROUS_TEXT_PATTERN.search(patch_text):
        errors.append("dangerous_command_present")
    policy = load_filesystem_policy(project_root=project_root)
    targets: list[Path] = []
    for path_text in _diff_paths(patch_text):
        normalized = _normalize_diff_path(path_text)
        if not normalized:
            errors.append(f"patch_target_invalid:{path_text}")
            continue
        target = (project_root / normalized).resolve()
        targets.append(target)
        if not _is_relative_to(target, project_root):
            errors.append(f"patch_target_outside_project_root:{normalized}")
        if not target.exists():
            errors.append(f"patch_target_missing:{normalized}")
        for policy_error in policy.validate_patch_target(target):
            if policy_error == "forbidden_c_path_present":
                errors.append("forbidden_c_path_present")
            elif policy_error.startswith("protected_path_modified:"):
                errors.append(policy_error)
            elif policy_error.startswith(("blocked_path:", "path_traversal_present:", "path_outside_allowed_roots:")):
                errors.append(policy_error)
    if not targets:
        errors.append("patch_targets_missing")
    if len({str(target) for target in targets}) > 1:
        errors.append("multiple_patch_targets_not_supported")
    target = targets[0] if targets else None
    if target is not None:
        try:
            old_text = target.read_text(encoding="utf-8")
            new_text = _apply_simple_unified_diff(old_text, patch_text)
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"patch_target_unreadable:{type(exc).__name__}")
        except ValueError as exc:
            errors.append(f"patch_context_invalid:{exc}")
        else:
            if target.suffix == ".py":
                try:
                    ast.parse(new_text)
                except SyntaxError:
                    errors.append("python_ast_invalid_after_retry_patch")
    return _dedupe(errors)


def self_healing_summary_fields(result: SelfHealingResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "self_healing_enabled": True,
        "self_healing_status": result.status,
        "self_healing_attempts": result.attempts,
        "self_healing_max_attempts": result.max_attempts,
        "self_healing_last_error": result.last_error,
        "self_healing_last_patch": result.retry_patch_path,
        "self_healing_validation_passed": result.validation_passed,
        "self_healing_validation_errors": result.validation_errors,
        "self_healing_validation_warnings": result.validation_warnings,
        "self_healing_artifacts": result.artifacts,
        "self_healing_memory_used": result.memory_used,
        "self_healing_memory_pattern_used": result.memory_pattern_used,
    }


def _build_constant_patch(target: Path, symbol: str, value: int) -> str:
    try:
        old_text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if re.search(rf"(?m)^\s*{re.escape(symbol)}\s*=", old_text):
        return ""
    old_lines = old_text.splitlines()
    insert_index = _constant_insert_index(old_lines)
    new_line = f"{symbol} = {value}"
    new_lines = old_lines[:insert_index] + [new_line] + old_lines[insert_index:]
    try:
        ast.parse("\n".join(new_lines) + "\n")
    except SyntaxError:
        return ""
    relative = target.relative_to(_project_root()).as_posix()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


def _constant_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "@dataclass")):
            while index > 0 and not lines[index - 1].strip():
                index -= 1
            return index
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(("\"\"\"", "'''", "from ", "import ")):
            return index
    return len(lines)


def _select_constant_target(run_dir: Path, signal: FailureSignal) -> Path | None:
    project_root = _project_root()
    candidates: list[Path] = [project_root / "agentic_network" / "config.py"]
    if signal.location:
        candidates.append(_location_to_path(signal.location, project_root))
    candidates.extend(_patch_targets_from_run(run_dir, project_root))
    policy = load_filesystem_policy(project_root=project_root)
    for candidate in candidates:
        if candidate.suffix != ".py" or not candidate.exists():
            continue
        if not _is_relative_to(candidate.resolve(), project_root):
            continue
        if policy.validate_read_path(candidate) or policy.validate_patch_target(candidate):
            continue
        return candidate.resolve()
    return None


def _patch_targets_from_run(run_dir: Path, project_root: Path) -> list[Path]:
    targets: list[Path] = []
    for directory in (run_dir / "patches", run_dir):
        if not directory.exists():
            continue
        for patch_path in sorted(directory.glob("*.diff")):
            if patch_path.name.startswith("19_retry_patch_"):
                continue
            try:
                text = patch_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for path_text in _diff_paths(text):
                normalized = _normalize_diff_path(path_text)
                if normalized:
                    targets.append((project_root / normalized).resolve())
    return targets


def _constant_value(symbol: str, *, memory_constants: dict[str, int] | None = None) -> int | None:
    memory_value = _memory_value_for_symbol(symbol, memory_constants or {})
    if memory_value is not None:
        return memory_value
    if "WINDOW_SECONDS" in symbol:
        return 3600
    if "MAX_ATTEMPTS" in symbol:
        return 5
    if "THRESHOLD" in symbol:
        return 10
    if "LIMIT" in symbol:
        return 5
    return None


def _load_experience_context(run_dir: Path) -> str:
    path = run_dir / "24_experience_context.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _memory_constant_values(experience_context: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for match in MEMORY_CONSTANT_PATTERN.finditer(experience_context):
        key = match.group("key")
        if key == "LIMIT":
            key = "MAX_ATTEMPTS"
        value = int(match.group("value"))
        if value > 0:
            values[key] = value
    return values


def _memory_value_for_symbol(symbol: str, memory_constants: dict[str, int]) -> int | None:
    if "WINDOW_SECONDS" in symbol:
        return memory_constants.get("WINDOW_SECONDS")
    if "MAX_ATTEMPTS" in symbol:
        return memory_constants.get("MAX_ATTEMPTS")
    if "THRESHOLD" in symbol:
        return memory_constants.get("THRESHOLD")
    if "LIMIT" in symbol:
        return memory_constants.get("LIMIT") or memory_constants.get("MAX_ATTEMPTS")
    return None


def _memory_pattern_used(experience_context: str) -> str:
    section = _section_body(experience_context, "REUSABLE PATTERNS")
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip().rstrip(".")
            if item and item != "No reusable patterns matched":
                return item
    return ""


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


def _load_failure_text(run_dir: Path, summary: dict[str, Any], warnings: list[str]) -> str:
    parts: list[str] = []
    for key in (
        "test_runner_stdout",
        "test_runner_stderr",
        "test_runner_stdout_summary",
        "test_runner_stderr_summary",
        "stdout_summary",
        "stderr_summary",
    ):
        value = summary.get(key)
        if value:
            parts.append(str(value))
    for filename in (
        "14_test_run.md",
        "summary.json",
        "13_patch_apply.md",
        "12_patch_approval.md",
        "11_execution_plan.md",
    ):
        path = run_dir / filename
        if path.exists():
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                warnings.append(f"artifact_unreadable:{filename}")
    patches_dir = run_dir / "patches"
    if patches_dir.exists():
        for patch_path in sorted(patches_dir.glob("*.diff")):
            try:
                parts.append(patch_path.read_text(encoding="utf-8"))
            except OSError:
                warnings.append(f"patch_unreadable:{patch_path.name}")
    return "\n\n".join(parts)


def _render_failure_analysis(signal: FailureSignal | None, failure_text: str, confidence: str) -> str:
    summary = (
        f"Detected {signal.error_type} from Test Runner output."
        if signal
        else _one_line(failure_text)
    )
    error_type = signal.error_type if signal else "None"
    location = signal.location if signal and signal.location else "Unknown"
    extracted = []
    if signal and signal.missing_symbol:
        extracted.append(f"missing_symbol = {signal.missing_symbol}")
    if signal:
        extracted.append(f"message = {signal.message or 'None'}")
    return "\n".join(
        [
            "FAILURE SUMMARY",
            f"- {summary}",
            "",
            "ERROR TYPE",
            f"- {error_type}",
            "",
            "ERROR LOCATION",
            f"- {location}",
            "",
            "EXTRACTED SIGNALS",
            *_bullets(extracted or ["None"]),
            "",
            "CONFIDENCE",
            confidence,
        ]
    )


def _render_root_cause(signal: FailureSignal | None, cause: str, strategy: str) -> str:
    unsafe = [
        "Did not apply retry patches.",
        "Did not execute commands, run tests, run LLMs, retrain, or modify repository source files.",
        "Did not bypass Patch Approval, Human Approval, Patch Apply, or Test Runner.",
    ]
    return "\n".join(
        [
            "ROOT CAUSE SUMMARY",
            f"- {_root_cause_summary(signal) if signal else cause}",
            "",
            "LIKELY CAUSE",
            f"- {cause}",
            "",
            "SAFE FIX STRATEGY",
            f"- {strategy}",
            "",
            "UNSAFE ACTIONS AVOIDED",
            *_bullets(unsafe),
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _render_self_healing_report(
    *,
    status: str,
    retry_patch_path: str,
    errors: list[str],
    warnings: list[str],
    signal: FailureSignal | None,
) -> str:
    next_action = (
        "Route the retry patch through Patch Approval and Human Approval before Patch Apply."
        if status == STATUS_RETRY_PATCH_GENERATED
        else "Review failure analysis and continue through the normal guarded pipeline."
    )
    validation = "Passed" if not errors else "Failed: " + ", ".join(errors)
    summary = (
        f"Self Healing analyzed {signal.error_type} and produced a retry patch proposal."
        if status == STATUS_RETRY_PATCH_GENERATED and signal
        else f"Self Healing completed with status {status}."
    )
    return "\n".join(
        [
            "SELF HEALING SUMMARY",
            f"- {summary}",
            "",
            "ATTEMPT STATUS",
            f"- {status}",
            "",
            "RETRY PATCH",
            f"- {retry_patch_path or 'None'}",
            "",
            "VALIDATION",
            f"- {validation}",
            *[f"- Warning: {warning}" for warning in warnings],
            "",
            "NEXT ACTION",
            f"- {next_action}",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _root_cause_summary(signal: FailureSignal | None) -> str:
    if signal is None:
        return "Unknown failure pattern."
    if signal.error_type == "NameError" and signal.missing_symbol:
        return f"Referenced symbol {signal.missing_symbol} is missing from code or configuration."
    if signal.error_type == "SyntaxError":
        return "Generated patch likely broke Python syntax."
    if signal.error_type == "AssertionError":
        return "Observed behavior does not match test expectations."
    if signal.error_type == "Timeout":
        return "Test execution exceeded the configured timeout."
    if signal.error_type == "ImportError":
        return "Import or module dependency was unavailable."
    return signal.message or "Unknown failure pattern."


def _safe_fix_strategy(signal: FailureSignal) -> str:
    if signal.error_type == "NameError" and signal.missing_symbol:
        return "Generate a review-only unified diff adding a conservative missing constant when deterministic."
    if signal.error_type == "ImportError":
        return "Do not add dependency installs automatically; record a recommendation only."
    if signal.error_type == "SyntaxError":
        return "Do not auto-patch unless a prior patch line can be safely and exactly corrected."
    if signal.error_type == "AssertionError":
        return "Do not synthesize behavior changes in v1 unless a missing constant is obvious."
    if signal.error_type == "Timeout":
        return "Do not synthesize timeout fixes by default."
    return "No retry patch in v1."


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


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _update_summary(run_dir: Path, result: SelfHealingResult) -> None:
    summary = _load_summary(run_dir, [])
    summary.update(self_healing_summary_fields(result))
    output_files = summary.setdefault("output_files", {})
    if isinstance(output_files, dict):
        output_files["self_healing"] = result.self_healing_path
        output_files["failure_analysis"] = result.failure_analysis_path
        output_files["root_cause"] = result.root_cause_path
        if result.retry_patch_path:
            output_files["self_healing_retry_patch"] = result.retry_patch_path
    (run_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _extract_location(content: str) -> str:
    matches = PYTHON_TRACEBACK_FILE_PATTERN.findall(content)
    return matches[-1] if matches else "Unknown"


def _location_to_path(location: str, project_root: Path) -> Path:
    path = Path(location)
    if path.is_absolute():
        return path.resolve()
    return (project_root / location).resolve()


def _diff_paths(patch_text: str) -> list[str]:
    return [match.group(1).strip() for match in DIFF_PATH_LINE.finditer(patch_text)]


def _normalize_diff_path(path_text: str) -> str:
    text = path_text.strip().strip('"').strip("'")
    if "\t" in text:
        text = text.split("\t", 1)[0]
    if text.startswith(("a/", "b/")):
        text = text[2:]
    return "" if text == "/dev/null" else text


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _last_error(signal: FailureSignal | None, errors: list[str]) -> str:
    if signal:
        return signal.message or signal.error_type
    return errors[0] if errors else ""


def _one_line(value: str, *, max_chars: int = 160) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return "No failure output was available."
    return text[: max_chars - 3].rstrip() + "..." if len(text) > max_chars else text


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items or ["None"]]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


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
