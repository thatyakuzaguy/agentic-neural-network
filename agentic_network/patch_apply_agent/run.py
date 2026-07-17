"""CLI entry point for the Patch Apply Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentic_network.patch_apply_agent.runtime import apply_approved_patches


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and optionally apply approved ANN patch proposals.")
    parser.add_argument("run_dir", type=Path, help="Path to an ANN output run directory.")
    parser.add_argument("--approve-patches", action="store_true", help="Required before patches can be applied or dry-run validated.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Validate patches without modifying repository files. This is the default.")
    parser.add_argument("--apply", action="store_true", help="Apply approved patches after validation. Requires --approve-patches.")
    args = parser.parse_args()

    if args.apply and not args.approve_patches:
        parser.error("--apply requires --approve-patches")

    result = apply_approved_patches(
        args.run_dir,
        approve_patches=args.approve_patches,
        dry_run=not args.apply,
    )
    print(f"Patch apply artifact: {result.artifact_path}")
    print(f"Status: {result.status}")
    if result.validation_errors:
        print("Validation errors:")
        for error in result.validation_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
