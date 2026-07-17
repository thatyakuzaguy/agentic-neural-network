import json
from pathlib import Path

IN = Path("training/datasets/python_expert_v1.jsonl")
OUT = Path("training/datasets/python_expert_v3.jsonl")

def score(row):
    text = json.dumps(row).lower()
    s = 0

    professional_terms = [
        "repository:", "solution patch", "diff --git",
        "fastapi", "django", "sqlalchemy", "pytest",
        "pandas", "async", "asyncio", "pydantic",
        "logging", "database", "migration",
        "api", "endpoint", "security", "tenant",
        "http", "request", "response", "class ",
        "exception", "context manager", "decorator",
    ]

    basic_terms = [
        "you are given a list",
        "you are given an array",
        "you are given a string",
        "find duplicates",
        "balanced brackets",
        "mode of the list",
        "flatten_list",
        "two sum",
        "four sum",
    ]

    for t in professional_terms:
        if t in text:
            s += 2

    for t in basic_terms:
        if t in text:
            s -= 3

    if len(text) > 2000:
        s += 1

    return s

rows = []

with IN.open("r", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        if score(row) >= 2:
            rows.append(row)

with OUT.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("Input:", IN)
print("Output:", OUT)
print("Kept:", len(rows))
