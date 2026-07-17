from pathlib import Path
import json

INPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_combined_v8_manual_mix.jsonl")

CLEAN_OUTPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_v9_repair_clean_part.jsonl")
CONTAMINATED_OUTPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_v9_repair_contaminated_part.jsonl")
REPORT_OUTPUT = Path("/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_v9_repair_contamination_report.txt")

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

clean = 0
contaminated = 0
bad_json = 0
term_counts = {term: 0 for term in FORBIDDEN}

with INPUT.open("r", encoding="utf-8") as f_in, \
     CLEAN_OUTPUT.open("w", encoding="utf-8") as f_clean, \
     CONTAMINATED_OUTPUT.open("w", encoding="utf-8") as f_bad, \
     REPORT_OUTPUT.open("w", encoding="utf-8") as f_report:

    for line_no, line in enumerate(f_in, 1):
        raw = line.strip()
        if not raw:
            continue

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            bad_json += 1
            f_report.write(f"BAD JSON line {line_no}\n")
            continue

        combined = (obj.get("instruction", "") + "\n" + obj.get("response", "")).lower()
        hits = [term for term in FORBIDDEN if term in combined]

        if hits:
            contaminated += 1
            for term in hits:
                term_counts[term] += 1

            obj["_repair_meta"] = {
                "source_line": line_no,
                "forbidden_hits": hits,
            }
            f_bad.write(json.dumps(obj, ensure_ascii=False) + "\n")
        else:
            clean += 1
            f_clean.write(json.dumps(obj, ensure_ascii=False) + "\n")

    f_report.write(f"input: {INPUT}\n")
    f_report.write(f"clean_output: {CLEAN_OUTPUT}\n")
    f_report.write(f"contaminated_output: {CONTAMINATED_OUTPUT}\n")
    f_report.write(f"clean: {clean}\n")
    f_report.write(f"contaminated: {contaminated}\n")
    f_report.write(f"bad_json: {bad_json}\n\n")
    f_report.write("term_counts:\n")
    for term, count in sorted(term_counts.items(), key=lambda x: x[1], reverse=True):
        f_report.write(f"{term}: {count}\n")

print(f"clean: {clean}")
print(f"contaminated: {contaminated}")
print(f"bad_json: {bad_json}")
print(f"report: {REPORT_OUTPUT}")
print(f"contaminated_file: {CONTAMINATED_OUTPUT}")
