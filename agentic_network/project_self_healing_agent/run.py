"""CLI for ANN Project Self-Healing Loop."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_self_healing_agent.runtime import run_project_self_healing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run project self-healing loop.")
    parser.add_argument("--project-root", required=True, help="Generated project root.")
    parser.add_argument("--run-dir", required=True, help="Run directory inside project_root.")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum retry attempts.")
    parser.add_argument("--approval-token", default=None, help="Project patch approval token.")
    parser.add_argument("--confirm-retry", action="store_true", help="Confirm retry patch application.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_project_self_healing(
        project_root=args.project_root,
        run_dir=args.run_dir,
        max_attempts=args.max_attempts,
        approval_token=args.approval_token,
        confirm_retry=args.confirm_retry,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "REPAIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
