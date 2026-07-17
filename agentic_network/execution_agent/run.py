"""CLI for the patch-only Execution Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.execution_agent.runtime import generate_execution_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ANN execution plan and patch proposals.")
    parser.add_argument("run_dir", type=Path, help="Pipeline run directory containing approved artifacts.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = generate_execution_plan(args.run_dir)
    payload = {
        "run_dir": result.run_dir,
        "final_decision": result.final_decision,
        "artifact_path": result.artifact_path,
        "patch_paths": result.patch_paths,
        "patch_count": result.patch_count,
        "refused": result.refused,
        "warnings": result.warnings,
        "validation_errors": result.validation_errors,
        "validation_passed": result.validation_passed,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(result.execution_plan)
        print(f"\nWrote: {result.artifact_path}")
        for patch_path in result.patch_paths:
            print(f"- {patch_path}")
        if result.warnings:
            print("\nWARNINGS", file=sys.stderr)
            for warning in result.warnings:
                print(f"- {warning}", file=sys.stderr)
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"- {error}", file=sys.stderr)
    return 0 if result.validation_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
