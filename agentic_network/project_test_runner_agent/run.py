"""CLI for ANN generated-project verification."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_test_runner_agent.runtime import run_project_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run allowlisted tests for a generated ANN project.")
    parser.add_argument("--project-root", required=True, help="Generated project root.")
    parser.add_argument("--run-dir", default=None, help="Run directory inside project_root.")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="Timeout per command.")
    parser.add_argument("--confirm-run", action="store_true", help="Confirm test execution.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_project_verification(
        project_root=args.project_root,
        run_dir=args.run_dir,
        timeout_seconds=args.timeout_seconds,
        confirm_run=args.confirm_run,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status in {"PASSED", "SKIPPED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
