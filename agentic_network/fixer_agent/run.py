"""CLI runner for the Fixer Agent artifact-only remediation planning stage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.fixer_agent.runtime import (
    FixerAgentResult,
    FixerAgentRuntimeModel,
    run_fixer_agent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Fixer Agent.")
    parser.add_argument("instruction", help="Raw user request.")
    parser.add_argument("--product-requirements-file", type=Path)
    parser.add_argument("--architecture-plan-file", type=Path)
    parser.add_argument("--code-plan-file", type=Path)
    parser.add_argument("--test-plan-file", type=Path)
    parser.add_argument("--security-review-file", type=Path)
    parser.add_argument("--reviewer-report-file", type=Path)
    parser.add_argument("--failure-context-file", type=Path)
    parser.add_argument("--output", type=Path, help="Optional path to write the fix plan.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    parser.add_argument(
        "--mode",
        choices=("fast", "deep", "auto"),
        default=None,
        help="Fixer model mode. Deep mode may load DeepSeek and must be selected explicitly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    mode = args.mode or config.fixer_mode
    runtime_model = None if args.mock else FixerAgentRuntimeModel(config, mode=mode)
    result = run_fixer_agent(
        user_request=args.instruction,
        product_requirements=_load_product_requirements(args),
        architecture_plan=_load_architecture_plan(args),
        code_plan=_load_code_plan(args),
        test_plan=_load_test_plan(args),
        security_review=_load_security_review(args),
        reviewer_report=_load_reviewer_report(args),
        failure_context=_load_failure_context(args),
        mode=mode,
        output_artifact_path=args.output,
        response_generator=(
            _fake_fixer_response
            if args.mock
            else runtime_model._generate_with_model  # noqa: SLF001
        ),
    )
    _write_validation_summary(args.output, result)
    if args.json:
        print(
            json.dumps(
                {
                    "raw_user_request": result.raw_user_request,
                    "product_requirements_input": result.product_requirements_input,
                    "architecture_plan_input": result.architecture_plan_input,
                    "code_plan_input": result.code_plan_input,
                    "test_plan_input": result.test_plan_input,
                    "security_review_input": result.security_review_input,
                    "reviewer_report_input": result.reviewer_report_input,
                    "failure_context_input": result.failure_context_input,
                    "fix_plan_output": result.fix_plan_output,
                    "parsed_sections": result.parsed_sections,
                    "warnings": result.warnings,
                    "validation_errors": result.validation_errors,
                    "fallback_used": result.fallback_used,
                    "artifact_path": result.artifact_path,
                },
                indent=2,
            )
        )
    else:
        print(result.to_stage_output())
        if result.artifact_path:
            print(f"\nWrote: {result.artifact_path}")
        if result.warnings:
            print("\nWARNINGS", file=sys.stderr)
            for warning in result.warnings:
                print(f"* {warning}", file=sys.stderr)
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"* {error}", file=sys.stderr)
    return 0 if not result.validation_errors else 2


def _write_validation_summary(output_path: Path | None, result: FixerAgentResult) -> None:
    if output_path is None:
        return
    validation_path = output_path.with_suffix(".validation.json")
    validation_path.write_text(
        json.dumps(
            {
                "warnings": result.warnings,
                "validation_errors": result.validation_errors,
                "validation_passed": not result.validation_errors,
                "fallback_used": result.fallback_used,
                "ready_for_rereview": result.parsed_sections.get("ready_for_rereview", ""),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_product_requirements(args: argparse.Namespace) -> str:
    if args.product_requirements_file:
        return args.product_requirements_file.read_text(encoding="utf-8").strip()
    return "REQUIREMENTS\n- Review the requested change.\n\nCONFIDENCE\nHigh"


def _load_architecture_plan(args: argparse.Namespace) -> str:
    if args.architecture_plan_file:
        return args.architecture_plan_file.read_text(encoding="utf-8").strip()
    return "TECHNICAL SUMMARY\n- No architecture artifact was provided.\n\nCONFIDENCE\nHigh"


def _load_code_plan(args: argparse.Namespace) -> str:
    if args.code_plan_file:
        return args.code_plan_file.read_text(encoding="utf-8").strip()
    return "CODE CHANGES\n- No code artifact was provided.\n\nCONFIDENCE\nHigh"


def _load_test_plan(args: argparse.Namespace) -> str:
    if args.test_plan_file:
        return args.test_plan_file.read_text(encoding="utf-8").strip()
    return "TEST SCENARIOS\n- No test artifact was provided.\n\nCONFIDENCE\nHigh"


def _load_security_review(args: argparse.Namespace) -> str:
    if args.security_review_file:
        return args.security_review_file.read_text(encoding="utf-8").strip()
    return "SECURITY FINDINGS\n- No security artifact was provided.\n\nCONFIDENCE\nHigh"


def _load_reviewer_report(args: argparse.Namespace) -> str:
    if args.reviewer_report_file:
        return args.reviewer_report_file.read_text(encoding="utf-8").strip()
    return "APPROVAL STATUS\nApproved\n\nCONFIDENCE\nHigh"


def _load_failure_context(args: argparse.Namespace) -> str:
    if args.failure_context_file:
        return args.failure_context_file.read_text(encoding="utf-8").strip()
    return ""


def _fake_fixer_response(*, prompt: str) -> str:
    ready = "No" if "APPROVAL STATUS\nNeeds Fixes" in prompt else "Yes"
    if ready == "Yes":
        return (
            "FIX SUMMARY\n"
            "* No significant fixes are required based on the current review.\n\n"
            "REQUIREMENT FIXES\n"
            "* No requirement changes are required.\n\n"
            "ARCHITECTURE FIXES\n"
            "* No architecture changes are required.\n\n"
            "IMPLEMENTATION FIXES\n"
            "* Continue with planned implementation.\n\n"
            "TEST FIXES\n"
            "* Maintain planned test coverage.\n\n"
            "SECURITY FIXES\n"
            "* Maintain planned security controls.\n\n"
            "PRIORITY ORDER\n"
            "* Proceed with implementation review.\n\n"
            "READY FOR RE-REVIEW\n"
            "Yes\n\n"
            "CONFIDENCE\n"
            "High"
        )
    return (
        "FIX SUMMARY\n"
        "* Reviewer findings require corrective planning before re-review.\n\n"
        "REQUIREMENT FIXES\n"
        "* Reconcile any reviewer-noted requirement gaps with Product Agent intent.\n\n"
        "ARCHITECTURE FIXES\n"
        "* Align architecture notes with reviewer-noted gaps before implementation.\n\n"
        "IMPLEMENTATION FIXES\n"
        "* Scope implementation corrections to reviewer findings only.\n\n"
        "TEST FIXES\n"
        "* Add or adjust tests for reviewer-noted coverage gaps.\n\n"
        "SECURITY FIXES\n"
        "* Address reviewer-noted security gaps with minimal corrective actions.\n\n"
        "PRIORITY ORDER\n"
        "* Resolve requirement gaps, then architecture gaps, then implementation, test, and security gaps.\n\n"
        "READY FOR RE-REVIEW\n"
        "No\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
