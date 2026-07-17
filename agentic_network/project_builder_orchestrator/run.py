"""CLI for ANN end-to-end project builder."""

from __future__ import annotations

import argparse
import json

from agentic_network.project_builder_orchestrator.runtime import run_end_to_end_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ANN end-to-end project builder.")
    parser.add_argument("--idea", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--max-features", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--confirm-create", action="store_true")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--confirm-tests", action="store_true")
    parser.add_argument("--generate-tests-if-missing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_end_to_end_project(
        idea=args.idea,
        target_root=args.target_root,
        project_name=args.project_name,
        approval_token=args.approval_token,
        max_features=args.max_features,
        max_retries=args.max_retries,
        confirm_create=args.confirm_create,
        confirm_apply=args.confirm_apply,
        confirm_tests=args.confirm_tests,
        generate_tests_if_missing=args.generate_tests_if_missing,
    )
    print(json.dumps(result.to_dict(), indent=2))
    non_fatal_statuses = {
        "COMPLETED_VERIFIED",
        "COMPLETED_UNVERIFIED",
        "NEEDS_TESTS",
        "NEEDS_REVIEW",
    }
    return 0 if result.status in non_fatal_statuses else 2


if __name__ == "__main__":
    raise SystemExit(main())
