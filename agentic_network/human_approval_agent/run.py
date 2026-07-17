"""CLI entry point for the Human Approval Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.human_approval_agent.runtime import authorize_apply


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize later ANN patch application.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    parser.add_argument("--approve-apply", action="store_true", help="Explicitly approve later patch application.")
    parser.add_argument("--approval-token", help="Exact human approval token.")
    args = parser.parse_args()

    result = authorize_apply(
        args.run_dir,
        approval_token=args.approval_token,
        approve_apply=args.approve_apply,
    )
    print(f"Human approval artifact: {result.artifact_path}")
    print(f"Decision: {result.decision}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
