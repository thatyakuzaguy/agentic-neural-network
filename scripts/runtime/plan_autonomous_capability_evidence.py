"""Plan the evidence required for ANN autonomous complex capability.

This script is read-only. It does not run projects, load models, infer, install
dependencies, or create success evidence. It only reports the missing proof ANN
must provide before final release can claim complex autonomous delivery.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_autonomous_capability_evidence_plan,
    write_autonomous_capability_evidence_plan_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan ANN autonomous capability evidence.")
    parser.add_argument("--evidence-root", default=None, help="Evidence root; defaults to outputs/autonomous_capability.")
    parser.add_argument("--output-dir", default=None, help="Optional artifact output directory.")
    parser.add_argument("--json", action="store_true", help="Print full JSON plan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = build_autonomous_capability_evidence_plan(args.evidence_root)
    if args.output_dir:
        write_autonomous_capability_evidence_plan_artifacts(Path(args.output_dir))
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        missing = [item["id"] for item in plan["scenarios"] if not item["passed"]]
        print(
            "\n".join(
                [
                    "ANN Autonomous Capability Evidence Plan",
                    f"Status: {plan['status']}",
                    f"Gate: {plan['gate_status']}",
                    f"Evidence Root: {plan['evidence_root']}",
                    f"Passed: {plan['passed_scenarios']}/{plan['required_scenarios']}",
                    f"Remaining: {', '.join(missing) if missing else 'none'}",
                ]
            )
        )
    return 0 if plan["status"] == "EVIDENCE_COMPLETE" else 2


if __name__ == "__main__":
    sys.exit(main())
