"""Lightweight static checks for obvious generated-code defects."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StaticSanityInput:
    """Generated pipeline text passed to the static sanity checker."""

    task: str
    architecture: str = ""
    code: str = ""
    tests: str = ""
    security: str = ""
    reviewer: str = ""
    fixer: str = ""


def run_static_sanity_checker(input_data: StaticSanityInput) -> str:
    """Return reviewer-ready static sanity findings."""

    findings: list[str] = []
    implementation = input_data.fixer or input_data.code
    combined = "\n\n".join(
        [
            input_data.architecture,
            implementation,
            input_data.tests,
            input_data.security,
            input_data.reviewer,
        ]
    )

    if _uses_datetime_fromisoformat(combined) and not _imports_datetime_class(combined):
        findings.append(
            "BLOCKING: datetime.fromisoformat(...) is used without importing the datetime class."
        )

    if "pytest.fail(" in input_data.tests and not _imports_name(input_data.tests, "pytest"):
        findings.append("BLOCKING: pytest.fail(...) is used in tests without importing pytest.")

    if "TestClient(" in input_data.tests and not _imports_test_client(input_data.tests):
        findings.append("BLOCKING: TestClient(...) is used in tests without importing TestClient.")

    if _task_requires_utc_timestamps(input_data.task):
        if _uses_naive_utcnow_isoformat(implementation):
            findings.append(
                "BLOCKING: Naive UTC timestamp detected. "
                "datetime.utcnow().isoformat() is not timezone-aware."
            )

        if _generates_timestamp(implementation) and not _uses_timezone_utc(implementation):
            findings.append(
                "BLOCKING: UTC timestamp generation does not use timezone.utc."
            )

        if _tests_expect_z_suffix(input_data.tests) and not _implementation_emits_z_suffix(
            implementation
        ):
            findings.append(
                "BLOCKING: Tests require a Z timestamp suffix but implementation does "
                "not generate one."
            )

        if _has_timestamp_format_mismatch(implementation, input_data.tests):
            findings.append(
                "BLOCKING: Implementation and tests contradict each other around "
                "timestamp format."
            )

        if _fixer_repeats_reviewer_utc_defect(input_data.reviewer, input_data.fixer):
            findings.append(
                "BLOCKING: Fixer repeats the original UTC timestamp defect reported "
                "by reviewer."
            )

    if _has_unverified_coverage_claim(combined):
        findings.append(
            "BLOCKING: Coverage or test-pass claims appear without execution evidence."
        )

    if re.search(r"</?think\b[^>]*>", input_data.security, flags=re.IGNORECASE):
        findings.append("BLOCKING: Security output contains DeepSeek reasoning tags.")

    lines = ["STATIC SANITY CHECK FINDINGS"]
    if not findings:
        lines.append("- No findings.")
    else:
        lines.extend(f"- {finding}" for finding in findings)
    return "\n".join(lines)


def count_static_sanity_findings(output: str) -> int:
    """Count concrete static sanity findings in checker output."""

    return sum(
        1
        for line in output.splitlines()
        if line.strip().startswith("- ") and "- No findings." not in line
    )


def has_blocking_static_sanity_findings(output: str) -> bool:
    """Return True when a checker output contains one or more blocking findings."""

    return count_static_sanity_findings(output) > 0


def _uses_datetime_fromisoformat(text: str) -> bool:
    return bool(re.search(r"\bdatetime\.fromisoformat\s*\(", text))


def _imports_datetime_class(text: str) -> bool:
    return bool(
        re.search(r"^\s*from\s+datetime\s+import\s+.*\bdatetime\b", text, flags=re.MULTILINE)
    )


def _imports_name(text: str, name: str) -> bool:
    return bool(re.search(rf"^\s*import\s+{re.escape(name)}\b", text, flags=re.MULTILINE))


def _imports_test_client(text: str) -> bool:
    return bool(
        re.search(
            r"^\s*from\s+(fastapi|starlette)\.testclient\s+import\s+.*\bTestClient\b",
            text,
            flags=re.MULTILINE,
        )
    )


def _task_requires_utc_timestamps(task: str) -> bool:
    lower_task = task.lower()
    return any(
        marker in lower_task
        for marker in ("utc", "timezone", "iso 8601", "iso8601", "z suffix")
    )


def _uses_naive_utcnow_isoformat(text: str) -> bool:
    return bool(re.search(r"\butcnow\s*\(\s*\)\s*\.isoformat\s*\(", text))


def _uses_timezone_utc(text: str) -> bool:
    return bool(re.search(r"\btimezone\.utc\b", text))


def _generates_timestamp(text: str) -> bool:
    return bool(
        re.search(r"\bdatetime\.(?:now|utcnow)\s*\(", text)
        or re.search(r"\.isoformat\s*\(", text)
    )


def _tests_expect_z_suffix(text: str) -> bool:
    return bool(re.search(r"\.endswith\s*\(\s*['\"]Z['\"]\s*\)", text))


def _implementation_emits_z_suffix(text: str) -> bool:
    return bool(
        re.search(r"\.replace\s*\(\s*['\"]\+00:00['\"]\s*,\s*['\"]Z['\"]\s*\)", text)
        or re.search(r"\+\s*['\"]Z['\"]", text)
        or re.search(r"['\"]Z['\"]\s*\+", text)
        or re.search(r"strftime\s*\([^)]*Z", text)
    )


def _has_timestamp_format_mismatch(implementation: str, tests: str) -> bool:
    return _tests_expect_z_suffix(tests) and not _implementation_emits_z_suffix(implementation)


def _fixer_repeats_reviewer_utc_defect(reviewer: str, fixer: str) -> bool:
    if not reviewer or not fixer:
        return False
    reviewer_reports_utc_defect = bool(
        re.search(r"\b(?:utcnow|naive utc|timezone\.utc|z suffix|timestamp)\b", reviewer, re.I)
    )
    fixer_claims_resolution = bool(
        re.search(r"\b(?:fix(?:ed|es)?|addressed|resolved|solved)\b", fixer, re.I)
    )
    return (
        reviewer_reports_utc_defect
        and fixer_claims_resolution
        and _uses_naive_utcnow_isoformat(fixer)
    )


def _has_unverified_coverage_claim(text: str) -> bool:
    return bool(
        re.search(r"\b100%\s+coverage\b", text, flags=re.IGNORECASE)
        or re.search(r"\ball\s+tests\s+passed\b", text, flags=re.IGNORECASE)
    )
