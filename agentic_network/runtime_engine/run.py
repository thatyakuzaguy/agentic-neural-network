"""CLI smoke runner for ANN Sequential Runtime Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.runtime_engine.loader import reset_runtime_state
from agentic_network.runtime_engine.scheduler import run_pipeline_sequential


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ANN stages through the sequential runtime engine.")
    parser.add_argument("--mode", default="FAST", help="Execution mode: FAST or POWERFUL.")
    parser.add_argument("--stages", nargs="+", required=True, help="Stages to execute sequentially.")
    parser.add_argument("--task", default="Sequential runtime smoke.", help="Task preview to pass to each agent.")
    parser.add_argument("--run-dir", default=None, help="Optional artifact directory.")
    parser.add_argument("--backend", default=None, help="Optional backend override: mock, ollama, gguf, unsloth_qwen.")
    args = parser.parse_args(argv)

    reset_runtime_state()
    result = run_pipeline_sequential(
        args.stages,
        execution_mode=args.mode,
        task=args.task,
        run_dir=Path(args.run_dir) if args.run_dir else None,
        backend_name=args.backend,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
