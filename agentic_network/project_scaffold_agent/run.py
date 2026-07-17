"""CLI for ANN Project Scaffold Agent."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_scaffold_agent.runtime import (
    apply_project_scaffold,
    preview_project_scaffold,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or apply an approved ANN project scaffold.")
    parser.add_argument("plan_dir", help="Directory containing artifacts 40 and 41.")
    parser.add_argument("--preview", action="store_true", help="Generate scaffold preview artifacts.")
    parser.add_argument("--apply", action="store_true", help="Apply or dry-run the scaffold.")
    parser.add_argument("--dry-run", action="store_true", help="Do not create project files.")
    parser.add_argument("--approval-token", default=None, help="Approval token for real scaffold apply.")
    parser.add_argument("--confirm-create", action="store_true", help="Confirm real scaffold creation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply:
        result = apply_project_scaffold(
            args.plan_dir,
            approval_token=args.approval_token,
            confirm_create=args.confirm_create,
            dry_run=args.dry_run,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status in {"APPLIED", "DRY_RUN"} else 2
    preview = preview_project_scaffold(args.plan_dir)
    print(json.dumps(preview.to_dict(), indent=2))
    return 0 if preview.status == "VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
