"""CLI smoke runner for the Architect Agent integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.architect_agent.runtime import (
    ArchitectAgentRuntimeModel,
    run_architect_agent,
)
from agentic_network.config import PipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Architect Agent.")
    parser.add_argument("instruction", help="Raw user request to turn into architecture.")
    parser.add_argument("--mode", choices=["fast", "deep", "auto"], default=None)
    parser.add_argument(
        "--product-requirements-file",
        type=Path,
        help="Existing 01_product_requirements.md artifact to use as input.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the architecture plan. Defaults to no file write.",
    )
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    parser.add_argument("--mock", action="store_true", help="Use a deterministic fake generator.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig.from_env()
    product_requirements = _load_product_requirements(args)
    output_path = args.output
    runtime_model = None if args.mock else ArchitectAgentRuntimeModel(config, config.project_root)
    result = run_architect_agent(
        user_request=args.instruction,
        product_requirements=product_requirements,
        mode=args.mode or config.architect_mode,
        repo_root=config.project_root,
        fast_model_path=config.architect_fast_model,
        deep_model_path=config.architect_deep_model,
        output_artifact_path=output_path,
        response_generator=(
            _fake_architect_response
            if args.mock
            else runtime_model._generate_with_selected_model  # noqa: SLF001
        ),
    )
    if args.json:
        print(
            json.dumps(
                {
                    "raw_user_request": result.raw_user_request,
                    "product_requirements_input": result.product_requirements_input,
                    "cleaned_architecture_response": result.cleaned_architecture_response,
                    "parsed_sections": result.parsed_sections,
                    "mode_used": result.mode_used,
                    "model_path_used": result.model_path_used,
                    "validation_warnings": result.validation_warnings,
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
    return 0 if not result.validation_errors else 2


def _load_product_requirements(args: argparse.Namespace) -> str:
    if args.product_requirements_file:
        return args.product_requirements_file.read_text(encoding="utf-8").strip()
    return (
        "REQUIREMENTS\n"
        f"- {args.instruction.strip()}\n\n"
        "AMBIGUITIES\n"
        "- No Product Agent artifact was provided to the CLI.\n\n"
        "ASSUMPTIONS\n"
        "- Use existing project patterns.\n\n"
        "ACCEPTANCE CRITERIA\n"
        "- Architecture plan is available for Code Agent handoff.\n\n"
        "RISKS\n"
        "- CLI fallback requirements are less precise than a real Product Agent artifact.\n\n"
        "CONFIDENCE\n"
        "High"
    )


def _fake_architect_response(*, prompt: str, mode: str, model_path: Path) -> str:
    return (
        "TECHNICAL SUMMARY\n"
        "- Add a minimal implementation plan derived from the Product Agent output.\n\n"
        "AFFECTED AREAS\n"
        "- Existing local pipeline and tests.\n\n"
        "FILES TO INSPECT\n"
        "- agentic_network/pipeline/runner.py\n"
        "- tests/python/test_local_agentic_pipeline.py\n\n"
        "IMPLEMENTATION PLAN\n"
        "- Inspect the existing pipeline entry point before editing.\n"
        "- Keep changes scoped to the requested capability.\n"
        "- Preserve existing acceptance criteria in the Code Agent handoff.\n\n"
        "DATA OR STATE CHANGES\n"
        "- No persistent data changes identified.\n\n"
        "TEST STRATEGY\n"
        "- Run parser validation and pipeline smoke tests with fake generators.\n\n"
        "RISKS\n"
        "- Real model behavior is not exercised when --mock is used.\n\n"
        "HANDOFF TO CODE AGENT\n"
        "- Implement only the scoped files after inspecting the current project structure.\n"
        "- Keep the final code aligned with Product Agent acceptance criteria.\n\n"
        "CONFIDENCE\n"
        "High"
    )


if __name__ == "__main__":
    raise SystemExit(main())
