import json
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT = Path("training/datasets/python_expert_v4_corrective.jsonl")
SWE = Path("training/datasets/swebench_v2.jsonl")

MAX_OPENCODE = 12000
MAX_CODESEARCH = 8000

BAD_PATTERNS = [
    "requests.post", "requests.get", "time.sleep", "sleep(",
    "unique=True", "db.query(", "Contact(**data)", "Invoice(**data)",
    "except Exception", "allow_origins=[\"*\"]",
]

GOOD_TERMS = [
    "fastapi", "sqlalchemy", "asyncsession", "asyncio", "httpx.asyncclient",
    "pytest", "tenant_id", "rbac", "audit", "idempotency",
    "pydantic", "structured logging", "opentelemetry", "alembic",
    "repository", "service layer", "background job", "redis", "celery",
]

def write(f, system, user, assistant):
    f.write(json.dumps({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }, ensure_ascii=False) + "\n")

def score_text(user, assistant):
    text = (user + "\n" + assistant).lower()
    score = 0
    for t in GOOD_TERMS:
        if t in text:
            score += 2
    for t in BAD_PATTERNS:
        if t.lower() in text:
            score -= 4
    if "```python" in text:
        score += 2
    if "test" in text or "pytest" in text:
        score += 2
    if "tenant_id" in text:
        score += 3
    if "async with" in text:
        score += 2
    return score

def add_corrective_examples(f):
    system = (
        "You are a staff-level Python backend engineer. "
        "Fix unsafe Python patterns and produce production-grade FastAPI, "
        "SQLAlchemy 2.0, asyncio and pytest guidance."
    )

    examples = [
        (
            "Review this async worker:\n\nasync def send(url, payload):\n    response = requests.post(url, json=payload)\n    time.sleep(5)\n    return response.json()",
            "Critical issues: blocking HTTP and blocking sleep inside async code. Use httpx.AsyncClient and await asyncio.sleep. Add timeouts, retries, idempotency, structured logs and dead-letter handling.\n\n```python\nimport asyncio\nimport httpx\nimport structlog\n\nlog = structlog.get_logger()\n\nasync def send_with_retry(url: str, payload: dict, event_id: str, max_attempts: int = 5) -> dict:\n    async with httpx.AsyncClient(timeout=10.0) as client:\n        for attempt in range(1, max_attempts + 1):\n            try:\n                response = await client.post(url, json=payload, headers={\"Idempotency-Key\": event_id})\n                response.raise_for_status()\n                log.info(\"webhook_sent\", event_id=event_id, attempt=attempt)\n                return response.json()\n            except httpx.HTTPError as exc:\n                delay = min(2 ** attempt, 60)\n                log.warning(\"webhook_retry\", event_id=event_id, attempt=attempt, delay=delay, error=str(exc))\n                await asyncio.sleep(delay)\n        log.error(\"webhook_dead_letter\", event_id=event_id)\n        raise RuntimeError(\"webhook delivery failed after retries\")\n```"
        ),
        (
            "Review this multi-tenant SQLAlchemy model:\n\nemail = Column(String, unique=True)\n\ndef get_contact(db, contact_id):\n    return db.query(Contact).filter(Contact.id == contact_id).first()",
            "Critical issues: global unique email breaks multi-tenancy, and query lacks tenant isolation. Use composite uniqueness and require tenant_id in every query.\n\n```python\nfrom sqlalchemy import UniqueConstraint, select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n\nclass Contact(Base):\n    __tablename__ = \"contacts\"\n    __table_args__ = (UniqueConstraint(\"tenant_id\", \"email\", name=\"uq_contact_tenant_email\"),)\n\n    id: Mapped[int] = mapped_column(primary_key=True)\n    tenant_id: Mapped[int] = mapped_column(index=True, nullable=False)\n    email: Mapped[str] = mapped_column(nullable=False)\n    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)\n\nasync def get_contact(session: AsyncSession, tenant_id: int, contact_id: int) -> Contact | None:\n    stmt = select(Contact).where(\n        Contact.id == contact_id,\n        Contact.tenant_id == tenant_id,\n        Contact.deleted_at.is_(None),\n    )\n    return await session.scalar(stmt)\n```\nRequired tests: tenant A cannot read tenant B, duplicate email allowed across tenants, duplicate email blocked within tenant."
        ),
        (
            "Design a FastAPI CSV import endpoint for contacts with tenant isolation, RBAC, idempotency, background job, audit log and pytest tests.",
            "Use a thin endpoint and move work to a service/job. Never parse a large CSV synchronously inside the request. Enforce tenant_id from auth context, not request body. Store idempotency key before enqueueing.\n\nImplementation decisions:\n- FastAPI endpoint validates file metadata and permissions.\n- Store upload in object storage/temp storage.\n- Create ImportJob row scoped by tenant_id.\n- Enforce unique (tenant_id, idempotency_key).\n- Enqueue background job.\n- Audit both job_created and job_completed.\n- Tests: success, forbidden role, duplicate idempotency key, invalid CSV, cross-tenant access.\n\nPseudo-structure:\n```python\n@router.post(\"/contacts/import\")\nasync def import_contacts(\n    file: UploadFile,\n    idempotency_key: Annotated[str, Header()],\n    ctx: AuthContext = Depends(require_permission(\"contacts:import\")),\n    session: AsyncSession = Depends(get_session),\n) -> ImportJobRead:\n    job = await import_service.create_job(\n        session=session,\n        tenant_id=ctx.tenant_id,\n        user_id=ctx.user_id,\n        file=file,\n        idempotency_key=idempotency_key,\n    )\n    await audit.log(session, ctx, \"contacts_import_requested\", {\"job_id\": job.id})\n    await queue.enqueue(\"contacts.import\", {\"job_id\": job.id, \"tenant_id\": ctx.tenant_id})\n    return ImportJobRead.model_validate(job)\n```"
        ),
    ]

    count = 0
    for user, assistant in examples:
        for _ in range(200):
            write(f, system, user, assistant)
            count += 1
    return count

def add_swe(f):
    if not SWE.exists():
        return 0
    count = 0
    with SWE.open("r", encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            text = json.dumps(row).lower()
            if any(t in text for t in ["django", "sqlalchemy", "pytest", "sphinx", ".py", "python"]):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    return count

def add_opencode(f):
    ds = load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True)
    count = 0
    for item in tqdm(ds, total=MAX_OPENCODE):
        if count >= MAX_OPENCODE:
            break
        user = item.get("instruction") or item.get("input") or item.get("question") or item.get("prompt") or ""
        assistant = item.get("output") or item.get("response") or item.get("solution") or item.get("answer") or ""
        if score_text(user, assistant) < 6:
            continue
        write(
            f,
            "You are a senior Python engineer. Produce correct production-grade Python, not tutorial text.",
            user[:5000],
            assistant[:10000],
        )
        count += 1
    return count

def add_codesearch(f):
    ds = load_dataset("Nan-Do/code-search-net-python", split="train", streaming=True)
    count = 0
    for item in tqdm(ds, total=MAX_CODESEARCH):
        if count >= MAX_CODESEARCH:
            break
        code = item.get("code") or item.get("func_code_string") or ""
        summary = item.get("summary") or item.get("docstring") or item.get("func_documentation_string") or ""
        text = (summary + "\n" + code).lower()
        if not any(t in text for t in ["async", "sqlalchemy", "request", "response", "exception", "database", "pytest", "class "]):
            continue
        write(
            f,
            "You are a senior Python engineer. Implement maintainable, typed, production-grade Python.",
            f"Implement this Python behavior:\n\n{summary[:2000]}",
            code[:8000],
        )
        count += 1
    return count

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with OUT.open("w", encoding="utf-8") as f:
        print("Adding corrective examples...")
        c = add_corrective_examples(f); print("corrective:", c); total += c

        print("Adding SWE-Bench...")
        c = add_swe(f); print("swe:", c); total += c

        print("Adding OpenCodeInstruct filtered...")
        c = add_opencode(f); print("opencode:", c); total += c

        print("Adding CodeSearchNet filtered...")
        c = add_codesearch(f); print("codesearch:", c); total += c

    print("Saved:", OUT)
    print("Total:", total)

if __name__ == "__main__":
    main()
