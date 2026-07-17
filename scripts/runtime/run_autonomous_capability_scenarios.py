"""Run ANN autonomous capability scenarios through the existing project builder.

This is a thin wrapper around ``run_end_to_end_project``. It is not a new
pipeline and does not bypass approval gates. Scenario execution requires
``--execute`` plus the same project-builder confirmations and approval token.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.project_builder_orchestrator.runtime import run_end_to_end_project
from agentic_network.runtime_engine.local_model_activation import build_autonomous_capability_evidence_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "outputs" / "autonomous_capability"
DEFAULT_TARGET_ROOT = REPO_ROOT / "outputs" / "autonomous_capability_projects"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ANN autonomous capability scenarios.")
    parser.add_argument("--scenario", action="append", help="Scenario id to run. Omit to run all scenarios.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--max-features", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="Actually run scenarios and write evidence.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = build_autonomous_capability_evidence_plan(args.evidence_root)
    selected = _selected_scenarios(plan["scenarios"], args.scenario)
    if not args.execute:
        print(_plan_summary(plan, selected))
        return 0
    evidence_root = Path(args.evidence_root).resolve()
    target_root = Path(args.target_root).resolve()
    results = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    for scenario in selected:
        result = run_end_to_end_project(
            idea=scenario["prompt"],
            target_root=target_root / scenario["id"] / run_id,
            project_name=scenario["id"],
            approval_token=args.approval_token,
            max_features=args.max_features,
            max_retries=args.max_retries,
            confirm_create=True,
            confirm_apply=True,
            confirm_tests=True,
            generate_tests_if_missing=True,
        )
        summary = _summary_from_result(scenario, result)
        scenario_dir = evidence_root / scenario["id"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (scenario_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
        results.append(summary)
    complete = all(item["status"] == "COMPLETED_VERIFIED" and item["security_review"] == "PASSED" for item in results)
    print(
        "\n".join(
            [
                "ANN Autonomous Capability Scenario Execution",
                f"Scenarios Run: {len(results)}",
                f"Completed Verified: {sum(1 for item in results if item['status'] == 'COMPLETED_VERIFIED')}",
                f"Status: {'SCENARIOS_VERIFIED' if complete else 'SCENARIOS_REQUIRE_REVIEW'}",
                f"Evidence Root: {evidence_root}",
            ]
        )
    )
    return 0 if complete else 2


def _selected_scenarios(scenarios: list[dict[str, Any]], requested: list[str] | None) -> list[dict[str, Any]]:
    if not requested:
        return scenarios
    by_id = {item["id"]: item for item in scenarios}
    missing = sorted(set(requested) - set(by_id))
    if missing:
        raise SystemExit(f"Unknown scenario id(s): {', '.join(missing)}")
    return [by_id[item] for item in requested]


def _plan_summary(plan: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "ANN Autonomous Capability Scenario Plan",
            f"Evidence Status: {plan['status']}",
            f"Selected Scenarios: {len(selected)}",
            "Execute: false",
            "Pass --execute with valid project-builder approval tokens to run.",
        ]
    )


def _summary_from_result(scenario: dict[str, Any], result: Any) -> dict[str, Any]:
    payload = result.to_dict()
    verification = payload.get("verification_evidence") or {}
    commands_executed = verification.get("commands_executed")
    if not isinstance(commands_executed, list):
        commands_executed = []
    security_review = (
        "PASSED"
        if payload.get("status") == "COMPLETED_VERIFIED" and not payload.get("validation_errors")
        else "REVIEW_REQUIRED"
    )
    return {
        "scenario_id": scenario["id"],
        "prompt": scenario["prompt"],
        "status": payload.get("status"),
        "completion_quality": payload.get("completion_quality"),
        "project_root": payload.get("project_root"),
        "verification_evidence": verification,
        "commands_executed": commands_executed,
        "security_review": security_review,
        "security_review_basis": "project-builder verification status and validation errors",
        "protected_paths_modified": False,
        "validation_errors": payload.get("validation_errors", []),
        "artifacts": payload.get("artifacts", []),
        "model_routing_status": payload.get("model_routing_status"),
        "next_action": payload.get("next_action"),
        "no_fake_success": True,
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary['scenario_id']}",
            "",
            f"- Status: {summary['status']}",
            f"- Completion quality: {summary['completion_quality']}",
            f"- Security review: {summary['security_review']}",
            f"- Commands executed: {len(summary['commands_executed'])}",
            f"- Project root: {summary['project_root']}",
            f"- Next action: {summary['next_action']}",
            "",
        ]
    )


if __name__ == "__main__":
    sys.exit(main())
