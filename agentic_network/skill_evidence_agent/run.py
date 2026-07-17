"""CLI for the ANN Skill Evidence Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_network.skill_evidence_agent.runtime import build_skill_evidence_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only ANN skill evidence bundle.")
    parser.add_argument("--skill-output-root", action="append", default=[], help="Skill artifact root to read.")
    parser.add_argument("--run-dir", default=None, help="Run directory where 70/71 artifacts should be written.")
    parser.add_argument("--max-items", type=int, default=20)
    args = parser.parse_args(argv)
    roots = [Path(item) for item in args.skill_output_root] or None
    result = build_skill_evidence_bundle(roots, args.run_dir, max_items=args.max_items)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status in {"VALID", "EMPTY"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
