"""CLI runner for the Code Agent implementation-plan stage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.code_agent.runtime import CodeAgentRuntimeModel, run_code_agent
from agentic_network.config import PipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Code Agent.")
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
        "--output",
        type=Path,
        help="Optional path to write the implementation artifact.",
    )
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    runtime_model = None if args.mock else CodeAgentRuntimeModel(config)
    result = run_code_agent(
        user_request=args.instruction,
        product_requirements=_load_product_requirements(args),
        architecture_plan=_load_architecture_plan(args),
        output_artifact_path=args.output,
        response_generator=(
            _fake_code_response
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
                    "generated_code_plan": result.generated_code_plan,
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


def _write_validation_summary(output_path: Path | None, result) -> None:
    if output_path is None:
        return
    validation_path = output_path.with_suffix(".validation.json")
    validation_path.write_text(
        json.dumps(
            {
                "warnings": result.warnings,
                "validation_errors": result.validation_errors,
                "validation_passed": not result.validation_errors,
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
        "- Code implementation plan is available for review.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _load_architecture_plan(args: argparse.Namespace) -> str:
    if args.architecture_plan_file:
        return args.architecture_plan_file.read_text(encoding="utf-8").strip()
    return (
        "TECHNICAL SUMMARY\n"
        "- No architecture artifact was provided to the CLI.\n\n"
        "FILES TO INSPECT\n"
        "- No specific files identified yet.\n\n"
        "HANDOFF TO CODE AGENT\n"
        "- Inspect existing project structure before recommending changes.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _fake_code_response(*, prompt: str) -> str:
    return (
        "FILES TO MODIFY\n"
        "- Candidate: password reset request handling module.\n"
        "- Candidate: rate-limit policy or configuration module.\n\n"
        "NEW FILES\n"
        "- Candidate: tests for password reset rate-limit behavior.\n\n"
        "CODE CHANGES\n"
        "- Add configurable rate limit policy for password reset requests.\n"
        "- Track reset attempts by user or request identity.\n"
        "- Block excessive requests with user-facing feedback.\n\n"
        "TESTS TO ADD\n"
        "- Verify limits are enforced for repeated requests.\n"
        "- Verify legitimate reset requests still work.\n"
        "- Verify limits reset after the configured window expires.\n\n"
        "RATIONALE\n"
        "- Prevent password reset abuse while preserving usability.\n"
        "- Align implementation with Product and Architect artifacts.\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
