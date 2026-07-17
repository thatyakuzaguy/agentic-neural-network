import json
from pathlib import Path

OUT = Path("training/datasets/python_v5_gold_corrective.jsonl")

SYSTEM = (
    "You are a staff-level Python backend engineer. "
    "Always produce production-grade Python guidance. "
    "Prefer FastAPI, SQLAlchemy 2.0, AsyncSession, tenant isolation, RBAC, "
    "audit logs, idempotency, pytest, structured logging, observability, "
    "secure coding and maintainable architecture. "
    "Avoid toy examples and avoid tutorial filler."
)

TOPICS = {
    "fastapi": 400,
    "sqlalchemy": 350,
    "asyncio": 300,
    "security": 250,
    "code_review": 300,
    "pytest": 200,
    "refactoring": 200,
}

def write_example(f, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")

def fastapi_example(i):
    user = (
        f"Design FastAPI endpoint scenario {i} for importing contacts in a "
        "multi-tenant SaaS CRM. Requirements: AsyncSession, tenant isolation, "
        "RBAC, idempotency key, background job, audit logs, structured logging, "
        "error handling and pytest tests."
    )
    assistant = """
Correct production design:

- Use AsyncSession, never sync Session.
- Derive tenant_id from AuthContext, never from request body.
- Enforce RBAC with a dependency like require_permission("contacts:import").
- Store idempotency key with UniqueConstraint("tenant_id", "idempotency_key").
- Create an ImportJob row and enqueue background processing.
- Write audit events for requested, completed and failed imports.
- Use structured logging with tenant_id, user_id, job_id and correlation_id.
- Return a job response, not imported contacts directly.

Correct shape:

@router.post("/contacts/import")
async def import_contacts(
    file: UploadFile,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ctx: AuthContext = Depends(require_permission("contacts:import")),
    session: AsyncSession = Depends(get_session),
) -> ImportJobRead:
    job = await import_service.create_import_job(
        session=session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        file=file,
        idempotency_key=idempotency_key,
    )
    await audit_service.log(
        session=session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="contacts_import_requested",
        entity_id=job.id,
    )
    await queue.enqueue("contacts.import", {"job_id": job.id, "tenant_id": ctx.tenant_id})
    return ImportJobRead.model_validate(job)

Required pytest cases:
- success creates job
- missing permission returns 403
- duplicate idempotency key returns existing job
- invalid CSV returns structured 422/400
- tenant A cannot access tenant B job
"""
    return user, assistant

def sqlalchemy_example(i):
    user = (
        f"Design SQLAlchemy 2.0 repository scenario {i} for tenant-safe contacts "
        "with soft delete, restore, pagination and unique email per tenant."
    )
    assistant = """
Correct production pattern:

- Use SQLAlchemy 2.0 typed models.
- Use AsyncSession.
- Every read/write must include tenant_id.
- Never use global unique=True for tenant-owned fields.
- Use composite constraints.

Model pattern:

class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_contacts_tenant_email"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

Repository pattern:

async def get_by_id(
    session: AsyncSession,
    tenant_id: UUID,
    contact_id: UUID,
) -> Contact | None:
    stmt = select(Contact).where(
        Contact.id == contact_id,
        Contact.tenant_id == tenant_id,
        Contact.deleted_at.is_(None),
    )
    return await session.scalar(stmt)

async def soft_delete(session: AsyncSession, tenant_id: UUID, contact_id: UUID) -> bool:
    contact = await get_by_id(session, tenant_id, contact_id)
    if contact is None:
        return False
    contact.deleted_at = datetime.now(UTC)
    await session.flush()
    return True

Required tests:
- tenant A cannot read tenant B contact
- duplicate email allowed across tenants
- duplicate email blocked within same tenant
- soft deleted contacts are hidden
- restore only works inside same tenant
"""
    return user, assistant

def asyncio_example(i):
    user = (
        f"Review asyncio worker scenario {i}. It processes webhook events and must "
        "support retries, exponential backoff, idempotency, structured logging and dead-letter handling."
    )
    assistant = """
Correct async rules:

Bad:
- requests.post(...) inside async code
- time.sleep(...) inside async code
- unbounded retries
- no idempotency
- no dead-letter queue

Good:
- httpx.AsyncClient
- await asyncio.sleep(...)
- explicit timeout
- bounded retries
- idempotency store
- structured logs
- dead-letter after final failure

Correct pattern:

async def deliver_event(event: WebhookEvent) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if await idempotency.already_processed(event.event_id):
                log.info("webhook_skip_duplicate", event_id=event.event_id)
                return

            try:
                response = await client.post(
                    event.url,
                    json=event.payload,
                    headers={"Idempotency-Key": event.event_id},
                )
                response.raise_for_status()
                await idempotency.mark_processed(event.event_id)
                log.info("webhook_delivered", event_id=event.event_id, attempt=attempt)
                return

            except httpx.HTTPError as exc:
                delay = min(2 ** attempt, 60)
                log.warning(
                    "webhook_retry",
                    event_id=event.event_id,
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

    await dead_letter.publish(event)
    log.error("webhook_dead_lettered", event_id=event.event_id)

Required tests:
- duplicate event is skipped
- transient HTTP failure retries
- final failure goes to dead letter
- no blocking requests/time.sleep usage
"""
    return user, assistant

def security_example(i):
    user = (
        f"Perform security review scenario {i} for a FastAPI multi-tenant SaaS endpoint."
    )
    assistant = """
Security review findings checklist:

Release blockers:
1. Missing tenant_id filter on queries.
2. tenant_id accepted from request body.
3. Missing RBAC dependency.
4. Missing audit logs for sensitive actions.
5. Wildcard CORS in production.
6. Secrets in code or logs.
7. No rate limiting for expensive endpoints.
8. No idempotency for billing/import/webhook operations.

Required controls:
- AuthContext from verified token/session.
- require_permission(...) dependency.
- tenant_id enforced in repository layer.
- audit_service.log(...) for sensitive writes.
- structured errors without leaking internals.
- rate limits for imports and webhooks.
- dependency scanning and SAST in CI.

Security tests:
- user without permission gets 403
- tenant A cannot access tenant B data
- malformed input returns 422
- audit log created on success and failure
- secrets are never returned or logged
"""
    return user, assistant

def code_review_example(i):
    user = f"""
Review this Python/FastAPI code scenario {i}:

async def create_contact(data, db):
    contact = Contact(**data)
    db.add(contact)
    await db.commit()
    return contact

Assume it runs in a multi-tenant SaaS CRM.
"""
    assistant = """
This code is not production-safe.

Issues:
1. No Pydantic validation boundary.
2. No AuthContext.
3. No tenant isolation.
4. No RBAC check.
5. Unsafe Contact(**data) mass assignment.
6. No audit log.
7. No transaction/error handling strategy.
8. No idempotency for retryable client operations.
9. No structured logging.
10. No tests.

Correct design:
- Router receives ContactCreate.
- Auth dependency returns AuthContext.
- RBAC dependency verifies contacts:create.
- Service owns business rules.
- Repository enforces tenant_id.
- Audit service records write.

Safer shape:

async def create_contact(
    payload: ContactCreate,
    ctx: AuthContext,
    session: AsyncSession,
) -> ContactRead:
    await permissions.require(ctx, "contacts:create")
    contact = await contact_service.create(
        session=session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        payload=payload,
    )
    await audit_service.log(
        session=session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="contact_created",
        entity_id=contact.id,
    )
    return ContactRead.model_validate(contact)

Required tests:
- success path
- validation error
- missing permission
- cross-tenant read/write blocked
- audit log exists
"""
    return user, assistant

def pytest_example(i):
    user = (
        f"Create pytest strategy scenario {i} for FastAPI, PostgreSQL, Redis, "
        "tenant isolation, RBAC and background jobs."
    )
    assistant = """
Production pytest strategy:

Fixtures:
- event_loop / anyio backend
- async_engine
- async_session with rollback per test
- app with dependency overrides
- client using httpx.AsyncClient
- tenant_factory
- user_factory
- auth_context_factory
- redis_fake or test Redis
- background_queue_fake

Test categories:
1. API validation tests.
2. RBAC tests.
3. Tenant isolation tests.
4. Repository tests.
5. Service tests.
6. Background job tests.
7. Idempotency tests.
8. Audit log tests.
9. Error handling tests.

Required tenant isolation tests:
- tenant A cannot read tenant B entity
- tenant A cannot update tenant B entity
- tenant A cannot access tenant B import job
- repositories always require tenant_id

Example assertion:
response = await client.post(
    "/contacts/import",
    headers=auth_headers(user_without_permission),
)
assert response.status_code == 403
"""
    return user, assistant

def refactor_example(i):
    user = (
        f"Refactor scenario {i}: a 900-line Python service validates input, writes "
        "to PostgreSQL, sends email, emits events and writes audit logs."
    )
    assistant = """
Refactoring target:

router/
- HTTP concerns only

schemas/
- Pydantic request/response models

services/
- business workflow and transaction boundaries

repositories/
- database access with tenant_id enforcement

notifications/
- email/SMS side effects

events/
- Kafka/Celery publishing

audit/
- audit logging

Migration plan:
1. Add tests around current behavior.
2. Introduce Pydantic schema boundary.
3. Extract repository methods with AsyncSession.
4. Extract business service.
5. Extract side effects behind interfaces.
6. Add audit service.
7. Add structured logging and trace IDs.
8. Move long-running work to background jobs.
9. Remove old code after parity tests pass.

Rules:
- Do not send email inside DB transaction.
- Do not publish Kafka event before commit unless using outbox pattern.
- All tenant-owned operations require tenant_id.
- All sensitive writes require audit logs.
"""
    return user, assistant

GENERATORS = {
    "fastapi": fastapi_example,
    "sqlalchemy": sqlalchemy_example,
    "asyncio": asyncio_example,
    "security": security_example,
    "code_review": code_review_example,
    "pytest": pytest_example,
    "refactoring": refactor_example,
}

OUT.parent.mkdir(parents=True, exist_ok=True)

count = 0

with OUT.open("w", encoding="utf-8") as f:
    for topic, total in TOPICS.items():
        generator = GENERATORS[topic]
        for i in range(total):
            user, assistant = generator(i)
            write_example(f, user, assistant)
            count += 1

print("Saved:", OUT)
print("Examples:", count)
