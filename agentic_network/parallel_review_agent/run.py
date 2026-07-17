"""CLI entrypoint for ANN Parallel Review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.parallel_review_agent.runtime import run_parallel_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic ANN parallel review.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--runs-root", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_parallel_review(
        args.run_dir,
        max_workers=args.max_workers,
        runs_root=args.runs_root,
    )
    print(json.dumps(result.to_dict(), indent=2))
    raise SystemExit(0 if result.status == "VALID" else 1)


if __name__ == "__main__":
    main()
