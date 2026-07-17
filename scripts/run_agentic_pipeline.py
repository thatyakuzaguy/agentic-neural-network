"""CLI for the local DeepSeek/Qwen multi-agent pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local multi-agent pipeline.")
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="User task to run through the pipeline.")
    task_group.add_argument("--task-file", type=Path, help="Markdown/text file containing the task.")
    parser.add_argument(
        "--stages",
        help=(
            "Comma-separated stage list: "
            "context,repository_intelligence,repository_context,product,architect,code,test,security,reviewer,fixer,revision,final,execution,patch_quality,patch_approval,patch_apply,test_runner,self_healing,merge_readiness,memory,human_approval,knowledge,handoff"
        ),
    )
    parser.add_argument("--skip-fixer", action="store_true", help="Do not run fixer automatically.")
    parser.add_argument("--run-tests", action="store_true", help="Allow the explicit test_runner stage to execute an allowlisted test command.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Timeout for test_runner execution when --run-tests is set.")
    parser.add_argument("--apply", action="store_true", help="Request guarded real patch application when patch_apply is selected.")
    parser.add_argument("--approve-patches", action="store_true", help="Required with --apply to allow Patch Apply to apply approved patches.")
    parser.add_argument("--approve-apply", action="store_true", help="Allow the explicit human_approval stage to approve later patch application.")
    parser.add_argument("--approval-token", help="Exact approval token for the human_approval stage.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock models.")
    parser.add_argument(
        "--mock-approved",
        action="store_true",
        help="In mock mode, make the reviewer approve instead of requiring fixes.",
    )
    return parser.parse_args()


def format_exception(exc: Exception) -> str:
    message = str(exc) or "<no message>"
    return f"{type(exc).__name__}: {message}"


def load_task(args: argparse.Namespace) -> str:
    if args.task:
        return args.task
    task_file = args.task_file
    if not task_file.exists():
        raise FileNotFoundError(f"Task file does not exist: {task_file}")
    return task_file.read_text(encoding="utf-8").strip()


def main() -> int:
    from agentic_network.config import PipelineConfig
    from agentic_network.pipeline.runner import PipelineRunner

    args = parse_args()
    try:
        task = load_task(args)
        stages = args.stages.split(",") if args.stages else None
        runner = PipelineRunner(
            PipelineConfig.from_env(),
            mock=args.mock,
            mock_changes_required=not args.mock_approved,
        )
        result = runner.run(
            task,
            stages=stages,
            skip_fixer=args.skip_fixer,
            run_tests=args.run_tests,
            test_timeout_seconds=args.timeout_seconds,
            approve_apply=args.approve_apply,
            approval_token=args.approval_token,
            apply_requested=args.apply,
            approve_patches=args.approve_patches,
        )
        print(f"Output folder: {result.output_dir}")
        print(f"Reviewer status: {result.reviewer_status}")
        print(f"Final status: {result.final_status}")
        return 0
    except Exception as exc:
        print(f"Pipeline failed: {format_exception(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
