"""Prepare a minimal ANN release-candidate handoff bundle.

The bundle is intended for transfer to a signing/clean-machine validation flow.
It copies only release scripts, installer binaries, runtime config, and
verification commands. It does not include models, datasets, adapters, memory,
knowledge, or historical outputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_release_candidate_handoff_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare ANN release candidate handoff bundle.")
    parser.add_argument(
        "--bundle-root",
        default="outputs/release_candidates/ANN_RC_HANDOFF",
        help="Target bundle directory inside the repository.",
    )
    parser.add_argument("--json", action="store_true", help="Print full manifest JSON.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report what would be included; do not copy files.",
    )
    return parser


def _summary(manifest: dict[str, object]) -> str:
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    return "\n".join(
        [
            "ANN Release Candidate Handoff",
            f"Status: {manifest.get('status')}",
            f"Bundle Root: {manifest.get('bundle_root')}",
            f"Materialized: {manifest.get('materialized')}",
            f"Files: {len(files)}",
            f"Missing: {', '.join(manifest.get('missing', [])) if manifest.get('missing') else 'none'}",
            f"Models Included: {manifest.get('model_files_included')}",
            f"Training Included: {manifest.get('training_files_included')}",
            f"Historical Outputs Included: {manifest.get('historical_outputs_included')}",
            f"Next: {manifest.get('sign_command')}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bundle_root = Path(args.bundle_root)
    manifest = build_release_candidate_handoff_manifest(
        bundle_root,
        materialize=not args.check_only,
    )
    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        print(_summary(manifest))
    return 0 if manifest["status"] == "HANDOFF_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
