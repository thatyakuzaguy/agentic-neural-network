"""CLI runner for the Test Engineer QA-plan stage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.test_engineer.runtime import (
    TestEngineerResult,
    TestEngineerRuntimeModel,
    run_test_engineer_agent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Test Engineer Agent.")
    parser.add_argument("instruction", help="Raw user request.")
    parser.add_argument(
        "--product-requirements-file",
        type=Path,
        help="Existing 01_product_requirements.md artifact to use as input.",
    )
    parser.add_argument(
        "--architecture-plan-file",
        type=Path,
        help="Existing 02_architecture_plan.md artifact to use as input.",
    )
    parser.add_argument(
        "--code-plan-file",
        type=Path,
        help="Existing 03_code.md artifact to use as input.",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write the QA artifact.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    runtime_model = None if args.mock else TestEngineerRuntimeModel(config)
    result = run_test_engineer_agent(
        user_request=args.instruction,
        product_requirements=_load_product_requirements(args),
        architecture_plan=_load_architecture_plan(args),
        code_plan=_load_code_plan(args),
        output_artifact_path=args.output,
        response_generator=(
            _fake_test_engineer_response
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
                    "generated_test_plan": result.generated_test_plan,
                    "parsed_sections": result.parsed_sections,
                    "warnings": result.warnings,
                    "validation_errors": result.validation_errors,
                    "output_artifact_path": result.output_artifact_path,
                },
                indent=2,
            )
        )
    else:
        print(result.to_stage_output())
        if result.output_artifact_path:
            print(f"\nWrote: {result.output_artifact_path}")
        if result.warnings:
            print("\nWARNINGS", file=sys.stderr)
            for warning in result.warnings:
                print(f"- {warning}", file=sys.stderr)
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"- {error}", file=sys.stderr)
    return 0 if not result.validation_errors else 2


def _write_validation_summary(output_path: Path | None, result: TestEngineerResult) -> None:
    if output_path is None:
        return
    validation_path = output_path.with_suffix(".validation.json")
    validation_path.write_text(
        json.dumps(
            {
                "warnings": result.warnings,
                "validation_errors": result.validation_errors,
                "validation_passed": not result.validation_errors,
                "fallback_used": any(
                    warning.startswith("model_output_replaced_after_validation_errors")
                    for warning in result.warnings
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_product_requirements(args: argparse.Namespace) -> str:
    if args.product_requirements_file:
        return args.product_requirements_file.read_text(encoding="utf-8").strip()
    return (
        "REQUIREMENTS\n"
        f"- {args.instruction.strip()}\n\n"
        "ACCEPTANCE CRITERIA\n"
        "- QA plan is available for review.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _load_architecture_plan(args: argparse.Namespace) -> str:
    if args.architecture_plan_file:
        return args.architecture_plan_file.read_text(encoding="utf-8").strip()
    return (
        "TECHNICAL SUMMARY\n"
        "- No architecture artifact was provided to the CLI.\n\n"
        "TEST STRATEGY\n"
        "- Validate the requested behavior at product and regression levels.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _load_code_plan(args: argparse.Namespace) -> str:
    if args.code_plan_file:
        return args.code_plan_file.read_text(encoding="utf-8").strip()
    return (
        "CODE CHANGES\n"
        "- Add the requested behavior with minimal changes.\n\n"
        "TESTS TO ADD\n"
        "- Cover allowed, blocked, and regression flows.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _fake_test_engineer_response(*, prompt: str) -> str:
    return (
        "TEST SCENARIOS\n"
        "- Verify password reset rate limits prevent repeated abuse.\n"
        "- Verify legitimate users can still complete password reset after allowed waiting conditions.\n"
        "- Verify user-facing feedback remains clear when limits are reached.\n\n"
        "TEST CASES\n"
        "- User reaches the configured reset limit and receives clear feedback.\n"
        "- User remains below the limit and receives reset instructions normally.\n"
        "- Repeated reset attempts are tracked consistently for the same account or identifier.\n"
        "- Reset attempts after the allowed waiting window are accepted.\n\n"
        "EDGE CASES\n"
        "- Multiple reset attempts occur close together.\n"
        "- A user retries after the limit window expires.\n"
        "- Reset flow is interrupted and resumed.\n"
        "- Reset attempts originate from repeated identifiers.\n\n"
        "REGRESSION TESTS\n"
        "- Existing successful password reset behavior remains unchanged.\n"
        "- Existing expired reset-link behavior remains unchanged.\n"
        "- Existing account recovery messaging remains consistent.\n\n"
        "AUTOMATION STRATEGY\n"
        "- Add behavior-level tests for allowed, blocked, and recovered reset flows.\n"
        "- Add regression coverage around existing password reset success and failure paths.\n"
        "- Keep tests deterministic by controlling rate-limit windows or test clocks.\n\n"
        "RISKS\n"
        "- Poorly designed tests may become flaky if time windows are not controlled.\n"
        "- Missing negative-path tests may allow abuse behavior to regress.\n"
        "- Overly strict assertions may block valid product changes.\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
