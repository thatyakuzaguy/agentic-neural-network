from __future__ import annotations

import hashlib
import itertools
import json
import random
from pathlib import Path

OUT = Path("training/datasets/product_agent/generated_instructions/instructions_v1.jsonl")
TARGET = 100_000
SEED = 42

DOMAINS = [
    "authentication", "authorization", "billing", "payments", "subscriptions",
    "crm", "inventory", "warehouse", "shipping", "search", "analytics",
    "reporting", "notifications", "email", "sms", "scheduling", "appointments",
    "bookings", "support", "knowledge base", "imports", "exports",
    "background jobs", "data pipelines", "monitoring", "alerting",
    "fraud detection", "document management", "media processing", "ecommerce",
]

ARTIFACTS = [
    "user accounts", "password resets", "login attempts", "refund requests",
    "invoice exports", "shipment updates", "inventory transfers",
    "customer records", "support tickets", "report generation",
    "scheduled jobs", "notification delivery", "email campaigns",
    "search indexes", "product catalogs", "booking reservations",
]

ACTIONS = [
    "prevent duplicates", "support retries", "detect conflicts", "enforce limits",
    "improve reliability", "archive old records", "allow bulk updates",
    "track history", "validate inputs", "handle failures",
    "recover from interruptions", "support cancellation", "support rollback",
    "reduce latency", "improve accuracy",
]

CONSTRAINTS = [
    "during concurrent updates", "when network failures occur", "for large datasets",
    "during peak traffic", "across regions", "while preserving history",
    "without data loss", "without downtime", "for mobile users",
    "for anonymous users", "for scheduled processing",
]

TEMPLATES = [
    "{action} for {artifact} {constraint}.",
    "{action} in {domain} workflows involving {artifact} {constraint}.",
    "Add support to {action} for {artifact} {constraint}.",
    "Improve {artifact} so the system can {action} {constraint}.",
    "Handle cases where {artifact} must {action} {constraint}.",
]

def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def clean_instruction(text: str) -> str:
    text = " ".join(text.split())
    return text[0].upper() + text[1:]

def main() -> None:
    random.seed(SEED)
    candidates = []

    for domain, artifact, action, constraint, template in itertools.product(
        DOMAINS, ARTIFACTS, ACTIONS, CONSTRAINTS, TEMPLATES
    ):
        instruction = clean_instruction(
            template.format(
                domain=domain,
                artifact=artifact,
                action=action,
                constraint=constraint,
            )
        )
        candidates.append(instruction)

    random.shuffle(candidates)

    seen = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with OUT.open("w", encoding="utf-8") as f:
        for instruction in candidates:
            key = instruction.lower()
            if key in seen:
                continue
            seen.add(key)

            obj = {
                "instruction_id": stable_id(instruction),
                "instruction": instruction,
                "source": "programmatic_v1",
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1
            if written >= TARGET:
                break

    print("written", written)
    print("out", OUT)

if __name__ == "__main__":
    main()
