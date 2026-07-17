"""Generate raw Product Agent outputs with the local DeepSeek teacher."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_TASKS = Path("training/datasets/product_agent/tasks.jsonl")
DEFAULT_RAW_DIR = Path("training/datasets/product_agent/raw")


@dataclass(frozen=True)
class TaskRow:
    """Task row loaded from tasks.jsonl."""

    id: str
    instruction: str
    domains: list[str]


class ProductAgentLike(Protocol):
    def run(self, input_text: str) -> str:
        """Generate a Product Agent response."""


def load_tasks(path: Path) -> list[TaskRow]:
    tasks: list[TaskRow] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            instruction = str(row.get("instruction", "")).strip()
            if not instruction:
                raise ValueError(f"Missing instruction in {path}:{line_number}")
            task_id = str(row.get("id") or f"product-task-{line_number:06d}")
            domains = [str(domain) for domain in row.get("domains", [])]
            tasks.append(TaskRow(task_id, instruction, domains))
    return tasks


def build_deepseek_product_agent() -> ProductAgentLike:
    """Build the existing DeepSeek wrapper behind the existing ProductAgent."""

    from agentic_network.agents.product_agent import ProductAgent
    from agentic_network.config import PipelineConfig
    from agentic_network.models.deepseek_gguf import DeepSeekGGUFModel

    model = DeepSeekGGUFModel(PipelineConfig.from_env())
    setattr(model, "backend_name", "deepseek")
    return ProductAgent(model)


def generate_raw_examples(
    tasks: list[TaskRow],
    agent: ProductAgentLike,
    raw_dir: Path,
    *,
    limit: int | None = None,
    resume: bool = True,
) -> int:
    raw_dir.mkdir(parents=True, exist_ok=True)
    selected = tasks[:limit] if limit is not None else tasks
    written = 0
    for task in selected:
        output_path = raw_dir / f"{task.id}.json"
        if resume and output_path.exists():
            continue
        response = agent.run(task.instruction).strip()
        payload = {
            "id": task.id,
            "instruction": task.instruction,
            "domains": task.domains,
            "response": response,
            "teacher_model": "deepseek",
            "created_at": _utc_now(),
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate raw Product Agent dataset examples.")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS, help="Input tasks.jsonl path.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Raw output directory.")
    parser.add_argument("--limit", type=int, help="Optional maximum number of tasks to process.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Regenerate examples even when raw files already exist.",
    )
    return parser.parse_args()


def _reject_c_drive(path: Path) -> None:
    resolved = path.resolve()
    if resolved.drive.upper() == "C:":
        raise ValueError(f"Refusing to write dataset artifacts on C: {resolved}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    _reject_c_drive(args.raw_dir)
    tasks = load_tasks(args.tasks)
    agent = build_deepseek_product_agent()
    written = generate_raw_examples(tasks, agent, args.raw_dir, limit=args.limit, resume=not args.no_resume)
    print(f"Saved {written} raw Product Agent examples to {args.raw_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
