import json
import random
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT = Path("training/datasets/external_50k_mixed.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

MAX_OPEN_CODE = 30000
MAX_SWE = 2294
MAX_VERIFIED = 500

random.seed(42)

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
    print("Downloading OpenCodeInstruct sample...")
    ds = load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True)

    count = 0
    for item in tqdm(ds, total=MAX_OPEN_CODE):
        if count >= MAX_OPEN_CODE:
            break

        question = item.get("instruction") or item.get("input") or item.get("question") or ""
        answer = item.get("output") or item.get("response") or item.get("solution") or ""

        if len(question) < 20 or len(answer) < 50:
            continue

        write_row(
            f,
            "You are a senior software engineer and coding agent.",
            question[:4000],
            answer[:6000],
        )
        count += 1

    print("Downloading SWE-bench...")
    swe = load_dataset("princeton-nlp/SWE-bench", split="test")

    for item in tqdm(swe.select(range(min(MAX_SWE, len(swe))))):
        repo = item.get("repo", "")
        problem = item.get("problem_statement", "")
        patch = item.get("patch", "")

        if not problem or not patch:
            continue

        write_row(
            f,
            "You are a senior debugging agent working on real GitHub issues.",
            f"Repository: {repo}\n\nIssue:\n{problem}",
            f"Proposed patch:\n{patch}",
        )

    print("Downloading SWE-bench Verified...")
    verified = load_dataset("SWE-bench/SWE-bench_Verified", split="test")

    for item in tqdm(verified.select(range(min(MAX_VERIFIED, len(verified))))):
        repo = item.get("repo", "")
        problem = item.get("problem_statement", "")
        patch = item.get("patch", "")

        if not problem or not patch:
            continue

        write_row(
            f,
            "You are a staff-level software repair agent.",
            f"Repository: {repo}\n\nVerified issue:\n{problem}",
            f"Verified solution patch:\n{patch}",
        )

print(f"Done. Dataset saved to {OUT}")
