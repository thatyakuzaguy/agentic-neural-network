"""CLI runner for the Final Reviewer Agent artifact-only approval gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.final_reviewer.runtime import (
    FinalReviewerResult,
    FinalReviewerRuntimeModel,
    run_final_reviewer_agent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Final Reviewer Agent.")
    parser.add_argument("instruction", help="Raw user request.")
    parser.add_argument("--product-requirements-file", type=Path)
    parser.add_argument("--architecture-plan-file", type=Path)
    parser.add_argument("--code-plan-file", type=Path)
    parser.add_argument("--test-plan-file", type=Path)
    parser.add_argument("--security-review-file", type=Path)
    parser.add_argument("--reviewer-report-file", type=Path)
    parser.add_argument("--fix-plan-file", type=Path)
    parser.add_argument("--output", type=Path, help="Optional path to write the final review.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    parser.add_argument(
        "--mode",
        choices=("fast", "deep", "auto"),
        default=None,
        help="Final Reviewer model mode. Deep mode may load DeepSeek and must be selected explicitly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    mode = args.mode or config.final_reviewer_mode
    runtime_model = None if args.mock else FinalReviewerRuntimeModel(config, mode=mode)
    result = run_final_reviewer_agent(
        user_request=args.instruction,
        product_requirements=_load_product_requirements(args),
        architecture_plan=_load_architecture_plan(args),
        code_plan=_load_code_plan(args),
        test_plan=_load_test_plan(args),
        security_review=_load_security_review(args),
        reviewer_report=_load_reviewer_report(args),
        fix_plan=_load_fix_plan(args),
        mode=mode,
        output_artifact_path=args.output,
        response_generator=(
            _fake_final_reviewer_response
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
                    "fix_plan_input": result.fix_plan_input,
                    "final_review_output": result.final_review_output,
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


def _write_validation_summary(output_path: Path | None, result: FinalReviewerResult) -> None:
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
                "final_decision": result.parsed_sections.get("final_decision", ""),
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


def _load_fix_plan(args: argparse.Namespace) -> str:
    if args.fix_plan_file:
        return args.fix_plan_file.read_text(encoding="utf-8").strip()
    return "READY FOR RE-REVIEW\nYes\n\nCONFIDENCE\nHigh"


def _fake_final_reviewer_response(*, prompt: str) -> str:
    decision = "Rejected" if "READY FOR RE-REVIEW\nNo" in prompt else "Approved"
    if decision == "Rejected":
        return (
            "FINAL ASSESSMENT\n"
            "* The artifact chain still has unresolved items that require manual review.\n\n"
            "REQUIREMENTS STATUS\n"
            "* Requirements require confirmation against reviewer findings.\n\n"
            "ARCHITECTURE STATUS\n"
            "* Architecture requires confirmation against reviewer findings.\n\n"
            "IMPLEMENTATION STATUS\n"
            "* Implementation planning requires confirmation before approval.\n\n"
            "TEST STATUS\n"
            "* Test coverage requires confirmation before approval.\n\n"
            "SECURITY STATUS\n"
            "* Security review requires confirmation before approval.\n\n"
            "REVIEW STATUS\n"
            "* Reviewer findings are not fully resolved.\n\n"
            "FIX STATUS\n"
            "* Fix plan is not ready for re-review.\n\n"
            "FINAL DECISION\n"
            "Rejected\n\n"
            "REASONING\n"
            "* Blocking uncertainty remains across the artifact chain.\n\n"
            "CONFIDENCE\n"
            "High"
        )
    return (
        "FINAL ASSESSMENT\n"
        "* The generated artifacts are internally consistent.\n\n"
        "REQUIREMENTS STATUS\n"
        "* Requirements are sufficiently covered.\n\n"
        "ARCHITECTURE STATUS\n"
        "* Architecture aligns with requirements.\n\n"
        "IMPLEMENTATION STATUS\n"
        "* Implementation plan aligns with architecture.\n\n"
        "TEST STATUS\n"
        "* Test coverage addresses major acceptance criteria.\n\n"
        "SECURITY STATUS\n"
        "* Security concerns have been reviewed.\n\n"
        "REVIEW STATUS\n"
        "* Reviewer findings have been addressed.\n\n"
        "FIX STATUS\n"
        "* No significant unresolved fixes remain.\n\n"
        "FINAL DECISION\n"
        "Approved\n\n"
        "REASONING\n"
        "* No blocking inconsistencies remain across the artifact chain.\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
