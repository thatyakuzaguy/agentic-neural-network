"""CLI for the Repository Intelligence Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.repository_intelligence_agent.runtime import build_repository_intelligence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build repository intelligence JSON indexes.")
    parser.add_argument("--project-root", type=Path, help="Repository root to scan.")
    parser.add_argument("--output-dir", type=Path, help="Directory for repository_intelligence JSON files.")
    parser.add_argument(
        "--allowed-root",
        action="append",
        type=Path,
        dest="allowed_roots",
        help="Allowed root to scan. May be repeated.",
    )
    parser.add_argument("--max-files", type=int, default=5000, help="Maximum supported files to index.")
    parser.add_argument("--json", action="store_true", help="Print structured result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_repository_intelligence(
        project_root=args.project_root,
        output_dir=args.output_dir,
        allowed_roots=args.allowed_roots,
        max_files=args.max_files,
    )
    payload = {
        "project_root": result.project_root,
        "output_dir": result.output_dir,
        "files_scanned": result.files_scanned,
        "functions": result.functions,
        "classes": result.classes,
        "routes": result.routes,
        "tests": result.tests,
        "languages_detected": result.languages_detected,
        "output_files": result.output_files,
        "warnings": result.warnings,
        "validation_errors": result.validation_errors,
        "validation_passed": result.validation_passed,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))
        print(f"\nWrote: {result.output_dir}")
        if result.validation_errors:
            print("\nVALIDATION ERRORS", file=sys.stderr)
            for error in result.validation_errors:
                print(f"- {error}", file=sys.stderr)
    return 0 if result.validation_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

