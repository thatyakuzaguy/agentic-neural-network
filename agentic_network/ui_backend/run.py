"""CLI entrypoint for the local ANN dashboard."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from agentic_network.ui_backend.runtime import DEFAULT_RUNS_ROOT, create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local ANN dashboard UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Defaults to 8765.")
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=DEFAULT_RUNS_ROOT,
        help="ANN outputs/runs directory to inspect.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = create_app(runs_root=args.runs_root)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
