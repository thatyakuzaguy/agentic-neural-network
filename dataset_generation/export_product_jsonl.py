"""Export approved Product Agent examples into training JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_APPROVED_DIR = Path("training/datasets/product_agent/approved")
DEFAULT_OUTPUT = Path("training/datasets/product_agent/product_agent_gold_v1.jsonl")


def export_approved_examples(approved_dir: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as file:
        for example_path in sorted(approved_dir.glob("*.json")):
            payload = json.loads(example_path.read_text(encoding="utf-8"))
            instruction = str(payload.get("instruction", "")).strip()
            response = str(payload.get("response", "")).strip()
            if not instruction or not response:
                raise ValueError(f"Approved example is missing instruction or response: {example_path}")
            file.write(
                json.dumps(
                    {
                        "instruction": instruction,
                        "response": response,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export approved Product Agent examples.")
    parser.add_argument(
        "--approved-dir",
        type=Path,
        default=DEFAULT_APPROVED_DIR,
        help="Approved examples directory.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Gold JSONL output path.")
    return parser.parse_args()


def _reject_c_drive(path: Path) -> None:
    resolved = path.resolve()
    if resolved.drive.upper() == "C:":
        raise ValueError(f"Refusing to write dataset artifacts on C: {resolved}")


def main() -> int:
    args = parse_args()
    _reject_c_drive(args.output)
    count = export_approved_examples(args.approved_dir, args.output)
    print(f"Exported {count} examples to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
