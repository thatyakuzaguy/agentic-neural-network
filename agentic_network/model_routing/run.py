"""CLI for ANN model routing smoke checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.model_routing.runtime import build_pipeline_routing_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ANN model routing plan artifacts.")
    parser.add_argument("--mode", default="FAST", help="Execution mode: FAST or POWERFUL.")
    parser.add_argument("--stages", nargs="+", required=True, help="Pipeline stages to route.")
    parser.add_argument("--run-dir", default=None, help="Optional run directory for artifacts.")
    parser.add_argument("--config-path", default=None, help="Optional routing config path.")
    args = parser.parse_args(argv)

    plan = build_pipeline_routing_plan(
        args.stages,
        mode=args.mode,
        run_dir=Path(args.run_dir) if args.run_dir else None,
        config_path=Path(args.config_path) if args.config_path else None,
    )
    print(json.dumps(plan.to_dict(), indent=2))
    return 0 if plan.status in {"VALID", "FALLBACK"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
