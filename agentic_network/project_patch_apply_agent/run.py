"""CLI for ANN Project Patch Apply Agent."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_patch_apply_agent.runtime import (
    apply_project_patch,
    rollback_project_patch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review, dry-run, apply, or rollback a project patch.")
    parser.add_argument("--project-root", help="Generated project root.")
    parser.add_argument("--patch", help="Patch file to apply.")
    parser.add_argument("--approval-token", default=None, help="Approval token for real apply.")
    parser.add_argument("--confirm-apply", action="store_true", help="Confirm real patch apply.")
    parser.add_argument("--dry-run", action="store_true", help="Preview patch application.")
    parser.add_argument("--no-backup", action="store_true", help="Disable backups for real apply.")
    parser.add_argument("--rollback", help="Backup directory to roll back.")
    parser.add_argument("--confirm-rollback", action="store_true", help="Confirm rollback.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rollback:
        result = rollback_project_patch(args.rollback, confirm_rollback=args.confirm_rollback)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status == "ROLLED_BACK" else 2
    if not args.project_root or not args.patch:
        raise SystemExit("--project-root and --patch are required unless --rollback is used.")
    result = apply_project_patch(
        args.project_root,
        args.patch,
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        backup=not args.no_backup,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status in {"DRY_RUN", "APPLIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
