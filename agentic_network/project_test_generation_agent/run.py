"""CLI for ANN project test generation."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_test_generation_agent.runtime import generate_project_tests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate approval-gated project test patches.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--max-tests", type=int, default=5)
    parser.add_argument("--test-target", action="append", dest="test_targets", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = generate_project_tests(
        project_root=args.project_root,
        run_dir=args.run_dir,
        test_targets=args.test_targets,
        max_tests=args.max_tests,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status in {"VALID", "NO_TARGETS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
