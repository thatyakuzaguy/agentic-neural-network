import json
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT = Path("training/datasets/python_expert_advanced_30k.jsonl")
SWE = Path("training/datasets/swebench_v2.jsonl")

MAX_OPEN_CODE = 30000

PRO_TERMS = [
    "fastapi", "django", "flask", "sqlalchemy", "pydantic",
    "pytest", "asyncio", "async def", "await ",
    "pandas", "numpy", "logging", "exception",
    "database", "migration", "api", "endpoint",
    "http", "request", "response", "middleware",
    "authentication", "authorization", "security",
    "docker", "kubernetes", "redis", "celery",
    "type hints", "typing", "dataclass",
    "context manager", "decorator", "repository",
    "service layer", "dependency injection",
]

BASIC_TERMS = [
    "two sum", "four sum", "balanced brackets",
    "find duplicates", "flatten list", "mode of the list",
    "palindrome", "fibonacci", "reverse a string",
    "binary search", "bubble sort",
]

def write(f, system, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")

def good_python_example(user, assistant):
    text = (user + "\n" + assistant).lower()

    if len(user) < 40 or len(assistant) < 120:
        return False

    if any(term in text for term in BASIC_TERMS):
        return False

    if "python" not in text and "def " not in text and "class " not in text:
        return False

    score = 0
    for term in PRO_TERMS:
        if term in text:
            score += 1

    if "```python" in text:
        score += 1

    if "test" in text or "pytest" in text:
        score += 1

    if "error" in text or "exception" in text:
        score += 1

    return score >= 2

def add_swebench(f):
    print("Adding SWE-Bench Python repair examples...")
    count = 0

    if not SWE.exists():
        print("Missing SWE-Bench local file, skipping.")
        return 0

    with SWE.open("r", encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            text = json.dumps(row).lower()

            if not any(x in text for x in [".py", "python", "django", "pytest", "sqlalchemy", "sphinx", "sympy"]):
                continue

            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    print("SWE-Bench kept:", count)
    return count

def add_opencode(f):
    print("Adding advanced OpenCodeInstruct Python examples...")
    ds = load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True)

    count = 0
    seen = set()

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

        key = (user[:200] + assistant[:200]).strip()
        if key in seen:
            continue
        seen.add(key)

        if not good_python_example(user, assistant):
            continue

        write(
            f,
            "You are an expert Python engineer. Produce production-quality Python: typed, tested, secure, maintainable, observable and idiomatic.",
            user[:5000],
            assistant[:10000],
        )

        count += 1

    print("OpenCodeInstruct advanced kept:", count)
    return count

def add_synthetic_professional(f, n=3000):
    print("Adding professional Python instruction examples...")
    topics = [
        "FastAPI endpoint with tenant isolation, RBAC, audit logs and pytest tests",
        "SQLAlchemy 2.0 async repository with explicit tenant_id filtering",
        "pytest strategy for Stripe webhook idempotency and signature verification",
        "asyncio worker with retries, exponential backoff and structured logging",
        "Pydantic settings management for production environments",
        "refactor a large Python service into service, repository and domain layers",
        "review Python code that swallows exceptions and returns None",
        "design a pandas data validation pipeline with schema checks",
        "write a CLI tool with argparse, logging, dry-run mode and safe errors",
        "secure file upload processing with validation and malware scanning hooks",
        "FastAPI dependency injection for current user, tenant and permissions",
        "database migration safety checklist with rollback and data validation",
        "background job queue with Redis/Celery and idempotent task design",
        "typed Python package layout with pyproject.toml, ruff, mypy and pytest",
        "production error handling strategy for a Python API",
    ]

    count = 0
    for i in range(n):
        topic = topics[i % len(topics)]

        user = f"Design and implement guidance for: {topic}."

        assistant = (
            f"Approach for {topic}:\n"
            f"1. Use clear module boundaries: api, schemas, services, repositories, domain, tests.\n"
            f"2. Use type hints, Pydantic models, explicit exceptions and structured logging.\n"
            f"3. Add tests for success, validation failure, authorization failure, edge cases and regression cases.\n"
            f"4. Avoid hidden global state and broad except Exception blocks.\n"
            f"5. Make side effects idempotent where possible.\n"
            f"6. Add observability: logs, metrics, trace ids and error context.\n"
            f"7. Security requirements: validate inputs, enforce authorization, avoid leaking secrets and audit sensitive actions.\n"
            f"8. Production readiness: config via environment, safe migrations, rollback plan and CI checks.\n"
        )

        write(
            f,
            "You are an expert Python engineer and production code reviewer.",
            user,
            assistant,
        )
        count += 1

    print("Synthetic professional examples:", count)
    return count

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    total = 0

    with OUT.open("w", encoding="utf-8") as f:
        total += add_swebench(f)
        total += add_opencode(f)
        total += add_synthetic_professional(f, n=3000)

    print("Saved:", OUT)
    print("Total:", total)

if __name__ == "__main__":
    main()
