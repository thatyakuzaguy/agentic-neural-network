"""CLI entry point for the ANN Self Healing Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.self_healing_agent.runtime import run_self_healing


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ANN self-healing for a pipeline run.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    parser.add_argument("--max-attempts", type=int, default=5, help="Maximum self-healing attempts. Default: 5.")
    args = parser.parse_args()

    result = run_self_healing(args.run_dir, max_attempts=args.max_attempts)
    print(f"Self-healing artifact: {result.self_healing_path}")
    print(f"Status: {result.status}")
    if result.retry_patch_path:
        print(f"Retry patch: {result.retry_patch_path}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
