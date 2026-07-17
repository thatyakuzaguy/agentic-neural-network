from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path("training/datasets/product_agent/generated_instructions/instructions_v3_family_clean.jsonl")
OUT = Path("training/datasets/product_agent/generated_instructions/instructions_v3_family_clean_filtered_v2.jsonl")
REJECT = Path("training/datasets/product_agent/generated_instructions/instructions_v3_family_clean_rejected_v2.jsonl")

BAD_PATTERNS = [
    r"while preserving financial history",
    r"when totals change after recalculation",
    r"before applying account changes",
    r"during concurrent booking attempts",
    r"during high-volume sending",
    r"after users change notification preferences",
    r"before applying changes before applying",
    r"while preserving adjustment history",
    r"when the recovery flow is interrupted\.?$",
    r"during concurrent reserved stock",
    r"reserved stock",
    r"when the related record is cancelled",

    r"for large result sets",
    r"for long-running jobs",
    r"after several failed attempts",
    r"for mobile users",
    r"without duplicating records",
    r"without creating negative stock",
    r"before creating records",
    r"when filters change",
    r"after cancellations",
    r"when file generation fails",
    r"\bwhen\b.*\bwhen\b",
    r"\bfor\b.*\bfor\b.*\bfor\b",
    r"\bduring\b.*\bduring\b",
    r"\bafter\b.*\bafter\b",
    r"\bwithout\b.*\bwithout\b",
    r"for repeated .* for long-running",
    r"fail when",
    r"after cancellation after",
    r"during concurrent .* during concurrent",
    r"after cancellation when the related record is cancelled",
    r"after cancellation when delivery fails",
    r"for repeated .*",
    r"long-running .* when file generation fails",
    r"\.\s+[a-z]",
]

GENERIC_WEIRD = [
    "allow bulk updates for user sessions",
    "support cancellation for login attempts",
    "archive old records for password resets",
    "support rollback for password resets",
]

def is_bad(text: str) -> bool:
    lower = text.lower()
    if len(text) < 25 or len(text) > 140:
        return True
    for phrase in GENERIC_WEIRD:
        if phrase in lower:
            return True
    for pattern in BAD_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False

def main() -> None:
    kept = rejected = 0
    with SRC.open(encoding="utf-8") as src, OUT.open("w", encoding="utf-8") as out, REJECT.open("w", encoding="utf-8") as rej:
        for line in src:
            obj = json.loads(line)
            instruction = obj["instruction"]
            if is_bad(instruction):
                rej.write(json.dumps(obj, ensure_ascii=False) + "\n")
                rejected += 1
            else:
                out.write(json.dumps(obj, ensure_ascii=False) + "\n")
                kept += 1

    print("kept", kept)
    print("rejected", rejected)
    print("out", OUT)
    print("reject", REJECT)

if __name__ == "__main__":
    main()
