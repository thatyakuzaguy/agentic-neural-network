"""CLI entrypoint for ANN Consensus-Driven Action Planner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.action_planner_agent.runtime import run_action_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic ANN action planning.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--runs-root", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_action_plan(args.run_dir, runs_root=args.runs_root)
    print(json.dumps(result.to_dict(), indent=2))
    raise SystemExit(0 if result.status == "VALID" else 1)


if __name__ == "__main__":
    main()
