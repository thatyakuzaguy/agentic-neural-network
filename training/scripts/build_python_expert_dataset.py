import json
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT = Path("training/datasets/python_expert_v1.jsonl")
SWE = Path("training/datasets/swebench_v2.jsonl")

MAX_OPEN_CODE = 20000
MAX_CODESEARCH = 20000

def write(f, system, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")

def add_opencode(f):
    print("Adding OpenCodeInstruct...")
    ds = load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True)

    count = 0
    for item in tqdm(ds, total=MAX_OPEN_CODE):
        if count >= MAX_OPEN_CODE:
            break

        user = (
            item.get("instruction")
            or item.get("input")
            or item.get("question")
            or item.get("prompt")
            or ""
        )

        assistant = (
            item.get("output")
            or item.get("response")
            or item.get("solution")
            or item.get("answer")
            or ""
        )

        text = (user + "\n" + assistant).lower()

        if "python" not in text and "def " not in text and "pytest" not in text:
            continue

        if len(user) < 20 or len(assistant) < 50:
            continue

        write(
            f,
            "You are an expert Python engineer. Write clean, typed, tested, production-quality Python.",
            user[:4000],
            assistant[:8000],
        )
        count += 1

    print("OpenCodeInstruct examples:", count)

def add_codesearchnet(f):
    print("Adding CodeSearchNet Python...")
    ds = load_dataset("Nan-Do/code-search-net-python", split="train", streaming=True)

    count = 0
    for item in tqdm(ds, total=MAX_CODESEARCH):
        if count >= MAX_CODESEARCH:
            break

        code = item.get("code") or item.get("func_code_string") or ""
        summary = item.get("summary") or item.get("docstring") or item.get("func_documentation_string") or ""

        if len(code) < 80 or len(summary) < 15:
            continue

        write(
            f,
            "You are an expert Python engineer. Implement clean Python from requirements.",
            f"Write a Python function that does this:\n\n{summary[:2000]}",
            code[:8000],
        )
        count += 1

    print("CodeSearchNet examples:", count)

def add_mbpp(f):
    print("Adding MBPP...")
    try:
        ds = load_dataset("google-research-datasets/mbpp", split="train")
    except Exception:
        ds = load_dataset("Muennighoff/mbpp", split="train")

    count = 0
    for item in ds:
        prompt = item.get("text") or item.get("prompt") or ""
        code = item.get("code") or ""

        tests = item.get("test_list") or item.get("test_setup_code") or ""

        if not prompt or not code:
            continue

        write(
            f,
            "You are an expert Python engineer. Solve the problem and satisfy the tests.",
            f"Problem:\n{prompt}\n\nTests:\n{tests}",
            code,
        )
        count += 1

    print("MBPP examples:", count)

def add_humaneval(f):
    print("Adding HumanEval...")
    ds = load_dataset("openai/openai_humaneval", split="test")

    count = 0
    for item in ds:
        prompt = item.get("prompt", "")
        canonical = item.get("canonical_solution", "")
        tests = item.get("test", "")

        if not prompt or not canonical:
            continue

        write(
            f,
            "You are an expert Python engineer. Complete the function correctly and pass all tests.",
            f"Complete this Python task:\n\n{prompt}\n\nTests:\n{tests}",
            canonical,
        )
        count += 1

    print("HumanEval examples:", count)

def add_swebench(f):
    print("Adding local SWE-Bench...")
    if not SWE.exists():
        print("Missing swebench_v2.jsonl, skipping.")
        return

    count = 0
    with SWE.open("r", encoding="utf-8") as src:
        for line in src:
            item = json.loads(line)
            messages = item.get("messages", [])
            if len(messages) < 3:
                continue

            text = json.dumps(item).lower()
            if "python" not in text and ".py" not in text and "django" not in text and "pytest" not in text:
                continue

            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1

    print("SWE-Bench Python-like examples:", count)

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8") as f:
        add_opencode(f)
        add_codesearchnet(f)
        add_mbpp(f)
        add_humaneval(f)
        add_swebench(f)

    print("Saved:", OUT)

if __name__ == "__main__":
    main()
