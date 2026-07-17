"""CLI entry point for the guarded Test Runner Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.test_runner_agent.runtime import run_tests_for_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run guarded ANN test execution for a pipeline run.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    parser.add_argument("--run-tests", action="store_true", help="Explicitly allow an allowlisted test command to execute.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Test execution timeout in seconds. Default: 300.")
    args = parser.parse_args()

    result = run_tests_for_run(
        args.run_dir,
        run_tests=args.run_tests,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"Test run artifact: {result.artifact_path}")
    print(f"Status: {result.status}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
