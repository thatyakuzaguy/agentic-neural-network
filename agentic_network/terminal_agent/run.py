"""CLI entrypoint for the safe ANN Terminal Agent."""

from __future__ import annotations

import argparse
import json

from agentic_network.terminal_agent.runtime import run_terminal_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a safe allowlisted ANN terminal command.")
    parser.add_argument("--cwd", default=".", help="Working directory inside the ANN repository.")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = run_terminal_command(
        command=command,
        cwd=args.cwd,
        timeout_seconds=args.timeout_seconds,
        allow_write=args.allow_write,
        run_id=args.run_id,
    )
    print(json.dumps(result.to_dict(), indent=2))
    raise SystemExit(0 if result.status == "PASSED" else 1)


if __name__ == "__main__":
    main()
