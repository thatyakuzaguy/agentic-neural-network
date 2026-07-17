"""CLI for the artifact-only Revision Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.revision_agent.runtime import apply_revisions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply artifact-only ANN revisions.")
    parser.add_argument("run_dir", type=Path, help="Pipeline run directory containing artifacts.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = apply_revisions(args.run_dir)
    payload = {
        "run_dir": result.run_dir,
        "artifact_path": result.artifact_path,
        "code_artifact_path": result.code_artifact_path,
        "test_artifact_path": result.test_artifact_path,
        "security_artifact_path": result.security_artifact_path,
        "artifacts_generated": result.artifacts_generated,
        "warnings": result.warnings,
        "validation_errors": result.validation_errors,
        "validation_passed": result.validation_passed,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(result.revision_summary)
        print(f"\nWrote: {result.artifact_path}")
        for artifact in result.artifacts_generated:
            print(f"- {artifact}")
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
