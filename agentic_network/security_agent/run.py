"""CLI runner for the Security Agent artifact-only review stage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.security_agent.runtime import (
    SecurityAgentResult,
    SecurityAgentRuntimeModel,
    run_security_agent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Security Agent.")
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
    parser.add_argument(
        "--test-plan-file",
        type=Path,
        help="Existing 04_tests.md artifact to use as input.",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write the security artifact.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    parser.add_argument(
        "--mode",
        choices=("fast", "deep", "auto"),
        default=None,
        help="Security model mode. Deep mode may load DeepSeek and must be selected explicitly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    mode = args.mode or config.security_mode
    runtime_model = None if args.mock else SecurityAgentRuntimeModel(config, mode=mode)
    result = run_security_agent(
        user_request=args.instruction,
        product_requirements=_load_product_requirements(args),
        architecture_plan=_load_architecture_plan(args),
        code_plan=_load_code_plan(args),
        test_plan=_load_test_plan(args),
        mode=mode,
        output_artifact_path=args.output,
        response_generator=(
            _fake_security_response
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
                    "generated_security_review": result.generated_security_review,
                    "parsed_sections": result.parsed_sections,
                    "warnings": result.warnings,
                    "validation_errors": result.validation_errors,
                    "fallback_used": result.fallback_used,
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


def _write_validation_summary(output_path: Path | None, result: SecurityAgentResult) -> None:
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
        "- Security review artifact is available for review.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _load_architecture_plan(args: argparse.Namespace) -> str:
    if args.architecture_plan_file:
        return args.architecture_plan_file.read_text(encoding="utf-8").strip()
    return (
        "TECHNICAL SUMMARY\n"
        "- No architecture artifact was provided to the CLI.\n\n"
        "RISKS\n"
        "- Security implications require review.\n\n"
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


def _load_test_plan(args: argparse.Namespace) -> str:
    if args.test_plan_file:
        return args.test_plan_file.read_text(encoding="utf-8").strip()
    return (
        "TEST SCENARIOS\n"
        "- Validate the requested behavior and regression coverage.\n\n"
        "RISKS\n"
        "- Security coverage may need additional review.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _fake_security_response(*, prompt: str) -> str:
    return (
        "SECURITY FINDINGS\n"
        "- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.\n"
        "- Reset-attempt tracking should not expose sensitive account existence information.\n"
        "- User-facing feedback should avoid confirming whether an account exists.\n\n"
        "THREATS\n"
        "- Automated reset abuse may overwhelm users or email systems.\n"
        "- Attackers may use reset behavior to enumerate valid accounts.\n"
        "- Weak tracking may allow repeated attempts from rotating identifiers.\n\n"
        "ABUSE SCENARIOS\n"
        "- An attacker repeatedly triggers reset messages for a target user.\n"
        "- An attacker probes reset feedback to infer account validity.\n"
        "- A malicious actor attempts to bypass limits by changing identifiers.\n\n"
        "SECURITY TESTS\n"
        "- Verify excessive reset attempts are limited without revealing account existence.\n"
        "- Verify feedback remains generic when limits are reached.\n"
        "- Verify reset attempts are tracked consistently across repeated requests.\n"
        "- Verify legitimate users can recover after the allowed waiting conditions.\n\n"
        "MITIGATIONS\n"
        "- Use generic feedback for reset requests and limit events.\n"
        "- Track repeated reset attempts using privacy-preserving identifiers.\n"
        "- Apply consistent limits across supported reset channels.\n"
        "- Log abuse indicators for monitoring without exposing sensitive data.\n\n"
        "RESIDUAL RISKS\n"
        "- Highly distributed abuse may still bypass simple limits.\n"
        "- Strict controls may impact legitimate users during account recovery.\n"
        "- Poor telemetry handling may introduce privacy concerns.\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
