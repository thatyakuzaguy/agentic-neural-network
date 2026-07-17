"""CLI for ANN Project Creation Agent."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_creation_agent.runtime import plan_new_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a safe ANN project creation plan.")
    parser.add_argument("--idea", required=True, help="Project idea to plan.")
    parser.add_argument("--target-root", required=True, help="Target root where the project may be created later.")
    parser.add_argument("--project-name", default=None, help="Optional explicit project name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = plan_new_project(
        idea=args.idea,
        target_root=args.target_root,
        project_name=args.project_name,
    )
    print(json.dumps(plan.to_dict(), indent=2))
    return 0 if plan.status == "VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
