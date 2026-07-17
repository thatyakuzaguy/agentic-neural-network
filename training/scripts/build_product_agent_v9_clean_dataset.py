from pathlib import Path
import json

INPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_combined_v8_manual_mix.jsonl")
OUTPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_combined_v9_clean.jsonl")

FORBIDDEN = [
    "tenant",
    "workspace",
    "organization",
    "support admin",
    "admin",
    "email domain",
    "database",
    "endpoint",
    "api",
    "429",
]

kept = 0
dropped = 0
bad_json = 0

with INPUT.open("r", encoding="utf-8") as f_in, OUTPUT.open("w", encoding="utf-8") as f_out:
    for line_no, line in enumerate(f_in, 1):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad_json += 1
            print(f"BAD JSON line {line_no}")
            continue

        combined = (obj.get("instruction", "") + "\n" + obj.get("response", "")).lower()

        if any(term in combined for term in FORBIDDEN):
            dropped += 1
            continue

        f_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        kept += 1

print(f"input: {INPUT}")
print(f"output: {OUTPUT}")
print(f"kept: {kept}")
print(f"dropped: {dropped}")
print(f"bad_json: {bad_json}")
