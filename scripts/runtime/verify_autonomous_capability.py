"""Verify ANN autonomous complex project capability evidence.

This script is read-only. It checks existing benchmark evidence and exits 0
only when every required complex scenario has strong verified evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_autonomous_complex_capability_gate,
    write_autonomous_complex_capability_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ANN autonomous complex capability evidence.")
    parser.add_argument("--evidence-root", default=None, help="Evidence root; defaults to outputs/autonomous_capability.")
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_autonomous_complex_capability_gate(args.evidence_root)
    if args.output_dir:
        write_autonomous_complex_capability_artifacts(Path(args.output_dir))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        blockers = ", ".join(item["id"] for item in report["blockers"]) or "none"
        print(
            "\n".join(
                [
                    "ANN Autonomous Complex Capability",
                    f"Status: {report['status']}",
                    f"Evidence Root: {report['evidence_root']}",
                    f"Passed: {report['passed_scenarios']}/{report['required_scenarios']}",
                    f"Blockers: {blockers}",
                ]
            )
        )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
