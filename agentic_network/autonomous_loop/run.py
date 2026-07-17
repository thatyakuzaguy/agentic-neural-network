"""CLI entrypoint for ANN v4.0 autonomous loop."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.autonomous_loop.runtime import run_autonomous_engineering_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the guarded ANN autonomous engineering loop.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--approve-patches", action="store_true")
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    result = run_autonomous_engineering_loop(
        args.run_dir,
        max_attempts=args.max_attempts,
        approve_patches=args.approve_patches,
        approval_token=args.approval_token,
        run_tests=args.run_tests,
        timeout_seconds=args.timeout_seconds,
    )
    print(result.report)
    return 0 if result.validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
