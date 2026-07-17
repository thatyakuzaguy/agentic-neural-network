import json
from pathlib import Path
from datasets import load_dataset

OUT = Path("training/datasets/swebench_v2.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

DATASETS = [
    ("SWE-bench/SWE-bench", "test", "senior debugging agent"),
    ("SWE-bench/SWE-bench_Verified", "test", "staff-level verified software repair agent"),
]

def write_row(f, system, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")

with OUT.open("w", encoding="utf-8") as f:
    for dataset_name, split, role in DATASETS:
        print(f"Loading {dataset_name}...")
        ds = load_dataset(dataset_name, split=split)

        for item in ds:
            repo = item.get("repo", "")
            problem = item.get("problem_statement", "")
            patch = item.get("patch", "")

            if not problem or not patch:
                continue

            write_row(
                f,
                f"You are a {role} working on real GitHub issues.",
                f"Repository: {repo}\n\nIssue:\n{problem}\n\nCreate a safe production-quality fix.",
                f"Solution patch:\n{patch}\n\nReview requirements: add tests when needed, preserve backwards compatibility, consider edge cases, and explain risks.",
            )

print(f"Saved to {OUT}")
