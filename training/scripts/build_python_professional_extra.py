import json
from pathlib import Path

OUT = Path("training/datasets/python_professional_extra.jsonl")

def write(f, system, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")

examples = [
    (
        "Design a FastAPI endpoint for creating contacts in a multi-tenant SaaS CRM with tenant isolation, RBAC, audit logs and pytest tests.",
        "Implement with FastAPI dependencies for current_user and tenant_id, validate input with Pydantic, enforce RBAC before database writes, scope every query by tenant_id, write an audit event after commit, return typed response models, and add pytest tests for success, forbidden role, cross-tenant access and validation errors."
    ),
    (
        "Review a Python service that catches all exceptions with except Exception and returns None.",
        "This is unsafe because it hides failures, breaks observability and makes callers handle ambiguous None values. Replace broad exception swallowing with typed exceptions, structured logging, domain-specific error classes and tests for expected failure paths. Only catch exceptions when adding context or recovering intentionally."
    ),
    (
        "Design a SQLAlchemy 2.0 repository for tenant-scoped queries.",
        "Use typed SQLAlchemy 2.0 models, AsyncSession, explicit tenant_id filters on every query, unique constraints including tenant_id, pagination, transaction boundaries and tests that prove tenant A cannot read tenant B data."
    ),
    (
        "Create a pytest strategy for a FastAPI billing module.",
        "Use unit tests for price calculations, integration tests for Stripe webhook signatures, idempotency tests for duplicate events, database tests for invoice creation, permission tests for billing access, and regression tests for failed payments."
    ),
    (
        "Refactor a large Python function that validates input, writes to database, sends email and logs audit events.",
        "Split into validation, domain service, repository, notification service and audit service. Keep transaction boundaries explicit. Make side effects observable. Add tests per component and one integration test for the full workflow."
    ),
]

SYSTEM = "You are a senior Python engineer. Write production-grade Python guidance: typed, tested, secure, maintainable and observable."

with OUT.open("w", encoding="utf-8") as f:
    for user, assistant in examples:
        write(f, SYSTEM, user, assistant)

print(f"Saved {OUT}")
