"""CLI entry point for the ANN Memory Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.memory_agent.runtime import record_engineering_experience


def main() -> None:
    parser = argparse.ArgumentParser(description="Record ANN engineering experience memory.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    args = parser.parse_args()

    result = record_engineering_experience(args.run_dir)
    print(f"Memory directory: {result.memory_dir}")
    print(f"Patterns recorded: {result.patterns_recorded}")
    print(f"Successful repairs recorded: {result.successful_repairs}")
    print(f"Failed repairs recorded: {result.failed_repairs}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
