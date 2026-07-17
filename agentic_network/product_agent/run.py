"""CLI smoke runner for the stable Product Agent integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.product_agent.runtime import (
    PRODUCT_AGENT_CONFIG_PATH,
    run_product_agent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the stable Product Agent adapter.")
    parser.add_argument("instruction")
    parser.add_argument("--config", type=Path, default=PRODUCT_AGENT_CONFIG_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--output", type=Path, help="Optional path to write stage output.")
    parser.add_argument("--json", action="store_true", help="Print full structured result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_product_agent(
        args.instruction,
        config_path=args.config,
        max_new_tokens=args.max_new_tokens,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "raw_instruction": result.raw_instruction,
                    "cleaned_response": result.cleaned_response,
                    "parsed_sections": result.parsed_sections,
                    "quality_warnings": result.quality_warnings,
                    "adapter_path": result.adapter_path,
                    "config_path": result.config_path,
                },
                indent=2,
            )
        )
    else:
        stage_output = result.to_stage_output()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(stage_output.rstrip() + "\n", encoding="utf-8")
        print(stage_output)
    return 0 if not result.quality_warnings else 2


if __name__ == "__main__":
    raise SystemExit(main())
