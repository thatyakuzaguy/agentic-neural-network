"""CLI for the non-LLM Context Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime import CONTEXT_OUTPUT_FILE, build_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable context for an ANN task.")
    parser.add_argument("task", help="Current user task.")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=Path("knowledge"),
        help="Knowledge base root directory.",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write context artifact.")
    parser.add_argument("--json", action="store_true", help="Print result metadata as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_context(args.task, args.knowledge_root)
    output_path = args.output or Path(CONTEXT_OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.context_artifact.rstrip() + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({**result.__dict__, "output_path": str(output_path)}, indent=2))
    else:
        print(f"Wrote: {output_path.resolve()}")
        print(f"Matched patterns: {len(result.matched_patterns)}")
        print(f"Matched lessons: {len(result.matched_lessons)}")
        print(f"Matched runs: {len(result.matched_runs)}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.validation_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if not result.validation_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
