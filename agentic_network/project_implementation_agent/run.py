"""CLI for ANN Project Implementation Kickoff."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_implementation_agent.runtime import start_project_implementation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start a deterministic ANN project implementation run.")
    parser.add_argument("--project-root", required=True, help="Scaffolded project root.")
    parser.add_argument("--objective", required=True, help="Implementation objective.")
    parser.add_argument("--max-features", type=int, default=5, help="Maximum features to include.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = start_project_implementation(
        project_root=args.project_root,
        objective=args.objective,
        max_features=args.max_features,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "PLANNED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
