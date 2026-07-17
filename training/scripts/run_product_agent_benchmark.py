from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


FORBIDDEN_TERMS = [
    "tenant",
    "workspace",
    "organization",
    "support admin",
    "admin",
    "email domain",
    "database",
    "endpoint",
    "api",
    "429",
]

REQUIRED_SECTIONS = [
    "REQUIREMENTS",
    "AMBIGUITIES",
    "ASSUMPTIONS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "CONFIDENCE",
]


def has_forbidden(response: str, instruction: str) -> list[str]:
    lower_response = response.lower()
    lower_instruction = instruction.lower()
    return [
        term
        for term in FORBIDDEN_TERMS
        if term in lower_response and term not in lower_instruction
    ]


def section_counts(response: str) -> dict[str, int]:
    lines = [line.strip() for line in response.splitlines()]
    return {section: lines.count(section) for section in REQUIRED_SECTIONS}


def format_issues(response: str) -> list[str]:
    issues = []
    counts = section_counts(response)

    for section, count in counts.items():
        if count != 1:
            issues.append(f"{section}_count_{count}")

    lines = response.splitlines()
    current = None
    bullets = {section: 0 for section in REQUIRED_SECTIONS}

    for line in lines:
        stripped = line.strip()
        if stripped in REQUIRED_SECTIONS:
            current = stripped
            continue
        if current and stripped.startswith("- "):
            bullets[current] += 1

    for section in REQUIRED_SECTIONS:
        if section == "CONFIDENCE":
            continue
        if bullets[section] < 1:
            issues.append(f"{section}_no_bullets")

    if "CONFIDENCE\nHigh" not in response and "CONFIDENCE\n- High" not in response:
        issues.append("confidence_not_high")

    if "```" in response:
        issues.append("code_fence")

    if "<think>" in response.lower() or "</think>" in response.lower():
        issues.append("think_tags")

    return issues


def run_one(script: Path, config: Path, instruction: str) -> tuple[str, str, int]:
    cmd = [
        sys.executable,
        str(script),
        instruction,
        "--config",
        str(config),
    ]

    result = subprocess.run(
        cmd,
        cwd=Path("/mnt/d/AgenticEngineeringNetwork"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    return result.stdout.strip(), result.stderr.strip(), result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    script = Path("/mnt/d/AgenticEngineeringNetwork/training/scripts/test_qwen3_product_adapter.py")

    prompts = [
        line.strip()
        for line in args.prompts.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    results = []
    failures = 0
    forbidden_total = 0
    format_total = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as f:
        for i, instruction in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}] {instruction}", flush=True)

            response, stderr, returncode = run_one(script, args.config, instruction)

            forbidden = has_forbidden(response, instruction)
            issues = format_issues(response)

            if returncode != 0:
                failures += 1
            if forbidden:
                forbidden_total += 1
            if issues:
                format_total += 1

            row = {
                "index": i,
                "instruction": instruction,
                "response": response,
                "stderr": stderr,
                "returncode": returncode,
                "forbidden_terms": forbidden,
                "format_issues": issues,
            }

            results.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    report_lines = []
    report_lines.append(f"prompts: {len(prompts)}")
    report_lines.append(f"runtime_failures: {failures}")
    report_lines.append(f"responses_with_forbidden_terms: {forbidden_total}")
    report_lines.append(f"responses_with_format_issues: {format_total}")
    report_lines.append("")
    report_lines.append("problem_cases:")

    for row in results:
        if row["returncode"] != 0 or row["forbidden_terms"] or row["format_issues"]:
            report_lines.append("=" * 80)
            report_lines.append(f"index: {row['index']}")
            report_lines.append(f"instruction: {row['instruction']}")
            report_lines.append(f"forbidden_terms: {row['forbidden_terms']}")
            report_lines.append(f"format_issues: {row['format_issues']}")
            if row["stderr"]:
                report_lines.append("stderr:")
                report_lines.append(row["stderr"][:2000])
            report_lines.append("response:")
            report_lines.append(row["response"][:2000])

    args.report.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"output: {args.output}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
