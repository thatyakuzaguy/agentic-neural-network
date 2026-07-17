"""CLI for the non-LLM Knowledge Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime import capture_knowledge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture reusable knowledge from an ANN run.")
    parser.add_argument("run_dir", type=Path, help="Pipeline run directory to read.")
    parser.add_argument("--json", action="store_true", help="Print result metadata as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = capture_knowledge(args.run_dir)
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print(f"Wrote: {result.artifact_path}")
        print(f"Reusable patterns: {len(result.reusable_patterns)}")
        print(f"Lessons learned: {len(result.lessons)}")
        print(f"Future reuse score: {result.future_reuse_score}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.validation_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if not result.validation_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
