"""CLI entry point for the Merge Readiness Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.merge_readiness_agent.runtime import evaluate_merge_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ANN run merge readiness.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    args = parser.parse_args()

    result = evaluate_merge_readiness(args.run_dir)
    print(f"Merge readiness artifact: {result.artifact_path}")
    print(f"Decision: {result.decision}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
