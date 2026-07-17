"""CLI for building a non-LLM ANN handoff bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.handoff.runtime import build_handoff_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an ANN handoff bundle.")
    parser.add_argument("run_dir", type=Path, help="Pipeline run directory.")
    parser.add_argument("--task", help="Optional task text override.")
    parser.add_argument("--json", action="store_true", help="Print structured result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_handoff_bundle(args.run_dir, task=args.task)
    payload = {
        "run_dir": result.run_dir,
        "artifact_path": result.artifact_path,
        "included_artifacts": result.included_artifacts,
        "missing_artifacts": result.missing_artifacts,
        "final_decision": result.final_decision,
        "reviewer_approval_status": result.reviewer_approval_status,
        "fixer_ready_for_rereview": result.fixer_ready_for_rereview,
        "warnings": result.warnings,
        "validation_errors": result.validation_errors,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Wrote: {result.artifact_path}")
        print(f"Included artifacts: {len(result.included_artifacts)}")
        print(f"Missing artifacts: {len(result.missing_artifacts)}")
        print(f"Final decision: {result.final_decision}")
        if result.warnings:
            print("\nWARNINGS", file=sys.stderr)
            for warning in result.warnings:
                print(f"* {warning}", file=sys.stderr)
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"* {error}", file=sys.stderr)
    return 0 if not result.validation_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
