from __future__ import annotations

import re


def build_full_stack_project_artifacts(idea: str, run_id: str) -> dict[str, str]:
    slug = _slugify(idea)
    base = f"{slug}-{run_id[:8]}"
    product_name = _product_name(idea)
    return {
        f"{base}/README.md": _readme(product_name, idea),
        f"{base}/.github/workflows/ci.yml": _github_ci(),
        f"{base}/.env.example": _env_example(),
        f"{base}/docker-compose.yml": _compose(),
        f"{base}/apps/api/Dockerfile": _api_dockerfile(),
        f"{base}/apps/api/alembic.ini": _alembic_ini(),
        f"{base}/apps/api/requirements.txt": _api_requirements(),
        f"{base}/apps/api/app/__init__.py": "",
        f"{base}/apps/api/app/database.py": _api_database(),
        f"{base}/apps/api/app/models.py": _api_models(),
        f"{base}/apps/api/app/schemas.py": _api_schemas(),
        f"{base}/apps/api/app/security.py": _api_security(),
        f"{base}/apps/api/app/security_headers.py": _api_security_headers(),
        f"{base}/apps/api/app/tenancy.py": _api_tenancy(),
        f"{base}/apps/api/app/rbac.py": _api_rbac(),
        f"{base}/apps/api/app/billing.py": _api_billing(),
        f"{base}/apps/api/app/workflows.py": _api_workflows(),
        f"{base}/apps/api/app/integrations.py": _api_integrations(),
        f"{base}/apps/api/app/domain.py": _api_domain_blueprint(product_name),
        f"{base}/apps/api/app/main.py": _api_main(product_name),
        f"{base}/apps/api/migrations/env.py": _alembic_env(),
        f"{base}/apps/api/migrations/script.py.mako": _alembic_script(),
        f"{base}/apps/api/migrations/versions/0001_initial.py": _alembic_initial_revision(),
        f"{base}/apps/api/tests/test_health.py": _api_test_health(),
        f"{base}/apps/desktop/package.json": _desktop_package(product_name),
        f"{base}/apps/desktop/src/main.js": _desktop_main(product_name),
        f"{base}/apps/web/Dockerfile": _web_dockerfile(),
        f"{base}/apps/web/package.json": _web_package(),
        f"{base}/apps/web/next.config.ts": _web_next_config(),
        f"{base}/apps/web/tsconfig.json": _web_tsconfig(),
        f"{base}/apps/web/src/app/globals.css": _web_globals(),
        f"{base}/apps/web/src/app/layout.tsx": _web_layout(product_name),
        f"{base}/apps/web/src/app/page.tsx": _web_page(product_name),
        f"{base}/apps/web/src/lib/api.ts": _web_api(),
        f"{base}/apps/web/tests/workbench.spec.ts": _web_e2e(product_name),
        f"{base}/database/schema.sql": _schema_sql(),
        f"{base}/docs/SPEC.md": _spec(product_name, idea),
        f"{base}/docs/ARCHITECTURE.md": _architecture(product_name),
        f"{base}/docs/DOMAIN_MODEL.md": _domain_model_doc(product_name),
        f"{base}/docs/PRODUCTION_HARDENING.md": _production_hardening_doc(),
        f"{base}/docs/COMPLIANCE.md": _compliance_doc(),
        f"{base}/docs/SECURITY.md": _security_doc(),
        f"{base}/docs/ROADMAP.md": _roadmap(),
        f"{base}/scripts/package-windows.ps1": _package_windows_script(),
        f"{base}/scripts/start.ps1": _start_script(),
        f"{base}/scripts/test.ps1": _test_script(),
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "generated-project"


def _product_name(idea: str) -> str:
    if "crm" in idea.lower():
        return "SaaS CRM"
    if "ecommerce" in idea.lower() or "commerce" in idea.lower():
        return "Ecommerce Platform"
    if "social" in idea.lower():
        return "Social App"
    return "Generated SaaS App"


def _readme(product_name: str, idea: str) -> str:
    return f"""# {product_name}

Generated from:

```text
{idea}
```

## Stack

- Next.js, React, TypeScript
- FastAPI, Python, SQLAlchemy
- PostgreSQL
- Docker Compose
- pytest and Playwright

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Web: http://localhost:3000
- API: http://localhost:8000/docs

## Features

- Email/password login scaffold with JWT-compatible token shape
- Accounts, contacts, deals, activities, and pipeline overview
- PostgreSQL schema and SQLAlchemy models
- Alembic migrations
- API health endpoint and CRUD-style CRM endpoints
- Responsive CRM dashboard
- Desktop wrapper scaffold for Windows `.exe` packaging
- Advanced domain blueprint for multi-tenancy, RBAC, billing, integrations, workflows, audit, and dashboard customization
- Docker deployment
- Unit and E2E test scaffolding

## Security

- Secrets are loaded from environment variables.
- Passwords are hashed with PBKDF2.
- CORS is restricted through environment configuration.
- Database credentials are not committed.
"""


def _env_example() -> str:
    return """POSTGRES_USER=crm
POSTGRES_PASSWORD=change-me
POSTGRES_DB=crm
DATABASE_URL=postgresql+psycopg://crm:change-me@postgres:5432/crm
JWT_SECRET=change-me
REFRESH_TOKEN_SECRET=change-me-too
CORS_ORIGINS=http://localhost:3000
SECURITY_CSP=default-src 'self'; connect-src 'self' http://localhost:*; img-src 'self' data:; style-src 'self' 'unsafe-inline'
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
PUBLIC_APP_URL=http://localhost:3000
WEBHOOK_SIGNING_SECRET=
NEXT_PUBLIC_API_URL=http://localhost:8000
POSTGRES_PORT=15432
API_PORT=18000
WEB_PORT=13000
"""


def _compose() -> str:
    return """services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-crm}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change-me}
      POSTGRES_DB: ${POSTGRES_DB:-crm}
    ports:
      - "${POSTGRES_PORT:-15432}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-crm} -d ${POSTGRES_DB:-crm}"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    build:
      context: ./apps/api
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql+psycopg://crm:change-me@postgres:5432/crm}
      JWT_SECRET: ${JWT_SECRET:-change-me}
      REFRESH_TOKEN_SECRET: ${REFRESH_TOKEN_SECRET:-change-me-too}
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:13000}
      SECURITY_CSP: ${SECURITY_CSP:-default-src 'self'; connect-src 'self' http://localhost:*; img-src 'self' data:; style-src 'self' 'unsafe-inline'}
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY:-}
      STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET:-}
      STRIPE_PRICE_ID: ${STRIPE_PRICE_ID:-}
      PUBLIC_APP_URL: ${PUBLIC_APP_URL:-http://localhost:13000}
      WEBHOOK_SIGNING_SECRET: ${WEBHOOK_SIGNING_SECRET:-dev}
    ports:
      - "${API_PORT:-18000}:8000"
    depends_on:
      postgres:
        condition: service_healthy

  web:
    build:
      context: ./apps/web
    environment:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:18000}
    ports:
      - "${WEB_PORT:-13000}:3000"
    depends_on:
      - api

volumes:
  postgres-data:
"""


def _api_dockerfile() -> str:
    return """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
"""


def _api_requirements() -> str:
    return """fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy>=2.0.0
alembic>=1.13.0
psycopg[binary]>=3.2.0
pydantic>=2.8.0
email-validator>=2.2.0
python-dotenv>=1.0.1
PyJWT>=2.8.0
stripe>=12.0.0
pytest>=8.0.0
httpx>=0.27.0
"""


def _alembic_ini() -> str:
    return """[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
"""


def _api_database() -> str:
    return '''from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./crm.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''


def _api_models() -> str:
    return '''from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(80), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    industry: Mapped[str] = mapped_column(String(120), default="General")
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contacts: Mapped[list["Contact"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    deals: Mapped[list["Deal"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(120), default="Decision maker")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="contacts")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(180))
    stage: Mapped[str] = mapped_column(String(80), default="qualified")
    value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="deals")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    kind: Mapped[str] = mapped_column(String(80), default="note")
    summary: Mapped[str] = mapped_column(String(240))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
'''


def _api_schemas() -> str:
    return '''from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    industry: str = "General"
    website: str | None = None


class AccountRead(AccountCreate):
    id: str

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    account_id: str
    name: str
    email: EmailStr
    role: str = "Decision maker"


class ContactRead(ContactCreate):
    id: str

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    account_id: str
    name: str
    stage: str = "qualified"
    value: float = 0
    notes: str | None = None


class DealRead(DealCreate):
    id: str

    model_config = {"from_attributes": True}


class ActivityCreate(BaseModel):
    account_id: str
    kind: str = "note"
    summary: str = Field(min_length=2, max_length=240)


class ActivityRead(ActivityCreate):
    id: str

    model_config = {"from_attributes": True}


class DashboardMetrics(BaseModel):
    accounts: int
    contacts: int
    open_deals: int
    activities: int
    pipeline_value: float
'''


def _api_security() -> str:
    return '''from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from secrets import token_bytes
from typing import Any

try:
    import jwt
except ModuleNotFoundError:
    jwt = None


TOKEN_ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = 60


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    algorithm, raw_salt, raw_digest = stored.split("$", 2)
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(raw_salt.encode())
    expected = base64.b64decode(raw_digest.encode())
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return hmac.compare_digest(actual, expected)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _fallback_jwt_encode(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": TOKEN_ALGORITHM, "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def _fallback_jwt_decode(token: str, secret: str) -> dict[str, Any]:
    encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(actual, expected):
        raise ValueError("Token signature is invalid")
    payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
    expires_at = payload.get("exp")
    if isinstance(expires_at, int) and expires_at < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token has expired")
    return payload


def issue_token(subject: str) -> str:
    secret = os.environ.get("JWT_SECRET", "change-me")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_TTL_MINUTES)).timestamp()),
    }
    if jwt is None:
        return _fallback_jwt_encode(payload, secret)
    return jwt.encode(payload, secret, algorithm=TOKEN_ALGORITHM)


def decode_token(token: str) -> str:
    secret = os.environ.get("JWT_SECRET", "change-me")
    if jwt is None:
        payload = _fallback_jwt_decode(token, secret)
    else:
        payload = jwt.decode(token, secret, algorithms=[TOKEN_ALGORITHM])
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise ValueError("Token subject is invalid")
    return subject
'''


def _api_security_headers() -> str:
    return '''from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import Request, Response


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


async def security_headers_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    response.headers.setdefault(
        "Content-Security-Policy",
        os.environ.get("SECURITY_CSP", "default-src 'self'; connect-src 'self' http://localhost:*"),
    )
    return response
'''


def _api_tenancy() -> str:
    return '''from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status


TenantHeader = Annotated[str | None, Header(alias="X-Tenant-ID")]


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str


def require_tenant(tenant_id: TenantHeader = None) -> TenantContext:
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required for tenant-scoped operations.",
        )
    return TenantContext(tenant_id=tenant_id)


def tenant_scope(model: object, tenant_id: str) -> object:
    return getattr(model, "tenant_id") == tenant_id
'''


def _api_rbac() -> str:
    return '''from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, status


RoleHeader = Annotated[str | None, Header(alias="X-Role")]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": {"billing:*", "tenant:*", "crm:*", "workflow:*", "integration:*", "dashboard:*"},
    "manager": {"crm:*", "workflow:read", "dashboard:*"},
    "contributor": {"crm:write", "crm:read", "dashboard:read"},
    "viewer": {"crm:read", "dashboard:read"},
}


def has_permission(role: str, permission: str) -> bool:
    grants = ROLE_PERMISSIONS.get(role, set())
    namespace = permission.split(":", 1)[0]
    return "*" in grants or permission in grants or f"{namespace}:*" in grants


def require_permission(permission: str) -> Callable[[RoleHeader], str]:
    def dependency(role: RoleHeader = "viewer") -> str:
        selected_role = role or "viewer"
        if not has_permission(selected_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{selected_role}' does not have permission '{permission}'.",
            )
        return selected_role

    return dependency
'''


def _api_billing() -> str:
    return '''from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

try:
    import stripe
except ModuleNotFoundError:
    stripe = None


router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    tenant_id: str
    customer_email: str
    price_id: str | None = None


class BillingPortalRequest(BaseModel):
    customer_id: str


def _stripe_ready() -> bool:
    return stripe is not None and bool(os.environ.get("STRIPE_SECRET_KEY"))


@router.get("/status")
def billing_status() -> dict[str, object]:
    return {
        "provider": "stripe",
        "configured": _stripe_ready(),
        "package_available": stripe is not None,
        "required_env": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID", "PUBLIC_APP_URL"],
    }


@router.post("/checkout-session")
def create_checkout_session(payload: CheckoutRequest) -> dict[str, Any]:
    if not _stripe_ready():
        return {
            "mode": "configuration_required",
            "message": "Install stripe and set STRIPE_SECRET_KEY and STRIPE_PRICE_ID to create real checkout sessions.",
        }
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
    price_id = payload.price_id or os.environ.get("STRIPE_PRICE_ID")
    if not price_id:
        raise HTTPException(status_code=400, detail="No Stripe price id configured.")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=payload.customer_email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{app_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{app_url}/billing/cancelled",
        metadata={"tenant_id": payload.tenant_id},
    )
    return {"id": session.id, "url": session.url}


@router.post("/portal-session")
def create_portal_session(payload: BillingPortalRequest) -> dict[str, Any]:
    if not _stripe_ready():
        return {"mode": "configuration_required", "message": "Install stripe and set STRIPE_SECRET_KEY to create billing portal sessions."}
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
    session = stripe.billing_portal.Session.create(customer=payload.customer_id, return_url=f"{app_url}/settings/billing")
    return {"url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None)) -> dict[str, str]:
    payload = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not _stripe_ready() or not secret:
        return {"status": "ignored", "reason": "Stripe webhook secret is not configured."}
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature or "", secret=secret)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Stripe webhook: {exc}") from exc
    return {"status": "received", "event_type": str(event["type"])}
'''


def _api_workflows() -> str:
    return '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowRule(BaseModel):
    field: str
    operator: Literal["eq", "neq", "gt", "lt", "contains"]
    value: str | int | float | bool


class WorkflowAction(BaseModel):
    type: Literal["create_task", "send_webhook", "assign_owner", "update_stage"]
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    name: str
    trigger: str
    rules: list[WorkflowRule] = Field(default_factory=list)
    actions: list[WorkflowAction] = Field(default_factory=list)


@dataclass(frozen=True)
class WorkflowDecision:
    matched: bool
    actions: list[WorkflowAction]


def _matches_rule(rule: WorkflowRule, event: dict[str, Any]) -> bool:
    current = event.get(rule.field)
    if rule.operator == "eq":
        return current == rule.value
    if rule.operator == "neq":
        return current != rule.value
    if rule.operator == "gt":
        return float(current or 0) > float(rule.value)
    if rule.operator == "lt":
        return float(current or 0) < float(rule.value)
    if rule.operator == "contains":
        return str(rule.value).lower() in str(current or "").lower()
    return False


def evaluate_workflow(definition: WorkflowDefinition, event: dict[str, Any]) -> WorkflowDecision:
    matched = event.get("trigger") == definition.trigger and all(_matches_rule(rule, event) for rule in definition.rules)
    return WorkflowDecision(matched=matched, actions=definition.actions if matched else [])


@router.post("/evaluate")
def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    definition = WorkflowDefinition.model_validate(payload["definition"])
    event = dict(payload.get("event", {}))
    decision = evaluate_workflow(definition, event)
    return {"matched": decision.matched, "actions": [action.model_dump() for action in decision.actions]}


@router.get("/templates")
def templates() -> list[WorkflowDefinition]:
    return [
        WorkflowDefinition(
            name="High value deal escalation",
            trigger="deal.updated",
            rules=[WorkflowRule(field="value", operator="gt", value=25000), WorkflowRule(field="stage", operator="eq", value="negotiation")],
            actions=[WorkflowAction(type="assign_owner", params={"role": "manager"}), WorkflowAction(type="create_task", params={"title": "Review high-value negotiation"})],
        )
    ]
'''


def _api_integrations() -> str:
    return '''from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel


router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationConnection(BaseModel):
    provider: str
    status: str = "configured"
    config: dict[str, Any] = {}


def sign_payload(payload: bytes) -> str:
    secret = os.environ.get("WEBHOOK_SIGNING_SECRET", "dev").encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(payload), signature)


@router.get("/providers")
def providers() -> list[dict[str, object]]:
    return [
        {"name": "stripe", "type": "billing", "configured": bool(os.environ.get("STRIPE_SECRET_KEY"))},
        {"name": "sendgrid", "type": "email", "configured": bool(os.environ.get("SENDGRID_API_KEY"))},
        {"name": "google_calendar", "type": "calendar", "configured": bool(os.environ.get("GOOGLE_CLIENT_ID"))},
        {"name": "slack", "type": "notification", "configured": bool(os.environ.get("SLACK_BOT_TOKEN"))},
    ]


@router.post("/connections")
def upsert_connection(payload: IntegrationConnection) -> dict[str, Any]:
    return {"connection": payload.model_dump(), "secret_storage": "environment-or-vault-required"}


@router.post("/webhooks/{provider}")
async def signed_webhook(provider: str, request: Request, x_signature: str | None = Header(default=None)) -> dict[str, str]:
    body = await request.body()
    if not x_signature or not verify_signature(body, x_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    return {"status": "accepted", "provider": provider}
'''


def _api_main(product_name: str) -> str:
    return f'''from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .billing import router as billing_router
from .integrations import router as integrations_router
from .models import Account, Activity, Contact, Deal, Membership, Tenant, User
from .rbac import require_permission
from .security_headers import security_headers_middleware
from .schemas import AccountCreate, AccountRead, ActivityCreate, ActivityRead, AuthResponse, ContactCreate, ContactRead, DashboardMetrics, DealCreate, DealRead, LoginRequest
from .security import decode_token, hash_password, issue_token, verify_password
from .tenancy import TenantContext, require_tenant
from .workflows import router as workflows_router

app = FastAPI(title="{product_name} API", version="0.1.0")
app.middleware("http")(security_headers_middleware)
origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(billing_router)
app.include_router(workflows_router)
app.include_router(integrations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {{"status": "ok", "service": "{product_name.lower().replace(" ", "-")}-api"}}


@app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=payload.email, name=payload.email.split("@")[0], password_hash=hash_password(payload.password))
    tenant_slug = payload.email.split("@")[0].lower().replace(".", "-").replace("_", "-")
    tenant = Tenant(name=f"{{user.name}} Workspace", slug=f"{{tenant_slug}}-{{os.urandom(2).hex()}}")
    db.add(user)
    db.add(tenant)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="owner"))
    db.commit()
    return AuthResponse(access_token=issue_token(user.id))


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(access_token=issue_token(user.id))


@app.get("/tenants", response_model=list[dict[str, str]])
def list_tenants(db: Session = Depends(get_db), role: str = Depends(require_permission("tenant:read"))) -> list[dict[str, str]]:
    return [{{"id": tenant.id, "name": tenant.name, "slug": tenant.slug}} for tenant in db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()]


@app.get("/dashboard", response_model=DashboardMetrics)
def dashboard(
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
) -> DashboardMetrics:
    accounts = db.scalar(select(func.count(Account.id)).where(Account.tenant_id == tenant.tenant_id)) or 0
    contacts = db.scalar(select(func.count(Contact.id)).where(Contact.tenant_id == tenant.tenant_id)) or 0
    activities = db.scalar(select(func.count(Activity.id)).where(Activity.tenant_id == tenant.tenant_id)) or 0
    open_deals = db.scalar(select(func.count(Deal.id)).where(Deal.tenant_id == tenant.tenant_id, Deal.stage != "won")) or 0
    pipeline_value = db.scalar(select(func.coalesce(func.sum(Deal.value), 0)).where(Deal.tenant_id == tenant.tenant_id)) or 0
    return DashboardMetrics(accounts=accounts, contacts=contacts, open_deals=open_deals, activities=activities, pipeline_value=float(pipeline_value))


@app.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:write")),
    db: Session = Depends(get_db),
) -> Account:
    account = Account(**payload.model_dump(), tenant_id=tenant.tenant_id)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@app.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:read")),
    db: Session = Depends(get_db),
) -> list[Account]:
    return list(db.scalars(select(Account).where(Account.tenant_id == tenant.tenant_id).order_by(Account.created_at.desc())).all())


@app.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:write")),
    db: Session = Depends(get_db),
) -> Contact:
    account = db.scalar(select(Account).where(Account.id == payload.account_id, Account.tenant_id == tenant.tenant_id))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found in tenant.")
    contact = Contact(**payload.model_dump(), tenant_id=tenant.tenant_id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@app.get("/contacts", response_model=list[ContactRead])
def list_contacts(
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:read")),
    db: Session = Depends(get_db),
) -> list[Contact]:
    return list(db.scalars(select(Contact).where(Contact.tenant_id == tenant.tenant_id).order_by(Contact.created_at.desc())).all())


@app.post("/deals", response_model=DealRead, status_code=status.HTTP_201_CREATED)
def create_deal(
    payload: DealCreate,
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:write")),
    db: Session = Depends(get_db),
) -> Deal:
    account = db.scalar(select(Account).where(Account.id == payload.account_id, Account.tenant_id == tenant.tenant_id))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found in tenant.")
    deal = Deal(**payload.model_dump(), tenant_id=tenant.tenant_id)
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@app.get("/deals", response_model=list[DealRead])
def list_deals(
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:read")),
    db: Session = Depends(get_db),
) -> list[Deal]:
    return list(db.scalars(select(Deal).where(Deal.tenant_id == tenant.tenant_id).order_by(Deal.created_at.desc())).all())


@app.post("/activities", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ActivityCreate,
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:write")),
    db: Session = Depends(get_db),
) -> Activity:
    account = db.scalar(select(Account).where(Account.id == payload.account_id, Account.tenant_id == tenant.tenant_id))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found in tenant.")
    activity = Activity(**payload.model_dump(), tenant_id=tenant.tenant_id)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@app.get("/activities", response_model=list[ActivityRead])
def list_activities(
    tenant: TenantContext = Depends(require_tenant),
    role: str = Depends(require_permission("crm:read")),
    db: Session = Depends(get_db),
) -> list[Activity]:
    return list(db.scalars(select(Activity).where(Activity.tenant_id == tenant.tenant_id).order_by(Activity.created_at.desc())).all())
'''


def _alembic_env() -> str:
    return '''from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base
from app import models  # noqa: F401


config = context.config
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", "sqlite:///./crm.db"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''


def _alembic_script() -> str:
    return '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''


def _alembic_initial_revision() -> str:
    return '''"""initial crm schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False, index=True),
        sa.Column("industry", sa.String(length=120), nullable=False, server_default="General"),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, index=True),
        sa.Column("role", sa.String(length=120), nullable=False, server_default="Decision maker"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "deals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="qualified"),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "activities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False, server_default="note"),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("features_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="trialing"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="configured"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("trigger_name", sa.String(length=120), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("workflow_definitions")
    op.drop_table("integration_connections")
    op.drop_table("invoices")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    op.drop_table("activities")
    op.drop_table("deals")
    op.drop_table("contacts")
    op.drop_table("accounts")
    op.drop_table("refresh_tokens")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
'''


def _api_test_health() -> str:
    return '''from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
'''


def _desktop_package(product_name: str) -> str:
    package_name = _slugify(product_name)
    return f'''{{
  "name": "{package_name}-desktop",
  "version": "0.1.0",
  "private": true,
  "main": "src/main.js",
  "scripts": {{
    "start": "electron .",
    "package": "electron-packager . \\"{product_name}\\" --platform=win32 --arch=x64 --electron-version=42.3.3 --out=dist --overwrite --asar"
  }},
  "devDependencies": {{
    "@electron/packager": "^19.0.1",
    "electron": "^42.3.0"
  }}
}}
'''


def _desktop_main(product_name: str) -> str:
    return f'''const {{ app, BrowserWindow, shell }} = require("electron");
const {{ spawn }} = require("child_process");
const http = require("http");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";

let childProcess;

function requestOk(url) {{
  return new Promise((resolve) => {{
    const req = http.get(url, {{ timeout: 1500 }}, (res) => {{
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    }});
    req.on("timeout", () => {{
      req.destroy();
      resolve(false);
    }});
    req.on("error", () => resolve(false));
  }});
}}

async function waitForWeb() {{
  for (let i = 0; i < 60; i += 1) {{
    if (await requestOk(WEB_URL)) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }}
  return false;
}}

function startStack() {{
  childProcess = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/start.ps1"], {{
    cwd: ROOT,
    windowsHide: true,
    stdio: "ignore"
  }});
}}

async function createWindow() {{
  const win = new BrowserWindow({{
    width: 1320,
    height: 860,
    minWidth: 1000,
    minHeight: 700,
    title: "{product_name}",
    backgroundColor: "#0d1117",
    webPreferences: {{ contextIsolation: true, nodeIntegration: false, sandbox: true }}
  }});
  win.webContents.setWindowOpenHandler(({{ url }}) => {{
    shell.openExternal(url);
    return {{ action: "deny" }};
  }});
  startStack();
  if (await waitForWeb()) {{
    await win.loadURL(WEB_URL);
  }} else {{
    await win.loadURL("data:text/html,<h1>{product_name}</h1><p>Could not start local services.</p>");
  }}
}}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
'''


def _web_dockerfile() -> str:
    return """FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
"""


def _web_package() -> str:
    return '''{
  "name": "generated-crm-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -H 0.0.0.0",
    "build": "next build",
    "start": "next start -H 0.0.0.0",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@playwright/test": "^1.57.0",
    "lucide-react": "^0.562.0",
    "next": "^16.2.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "typescript": "^5.9.0"
  }
}
'''


def _web_next_config() -> str:
    return """import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
"""


def _web_tsconfig() -> str:
    return '''{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
'''


def _web_globals() -> str:
    return """* { box-sizing: border-box; }
body {
  margin: 0;
  background: #0d1117;
  color: #e6edf3;
  font-family: Arial, Helvetica, sans-serif;
}
button, input { font: inherit; }
.shell { min-height: 100vh; display: grid; grid-template-columns: 260px 1fr; }
.sidebar { border-right: 1px solid #30363d; padding: 20px; background: #161b22; }
.tenant-pill { margin-top: 18px; border: 1px solid #2f81f7; border-radius: 6px; padding: 8px; color: #79c0ff; background: #0d1117; }
.main { padding: 24px; }
.grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
.card { border: 1px solid #30363d; border-radius: 8px; padding: 16px; background: #161b22; }
.modules { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }
.module { display: flex; gap: 10px; border: 1px solid #30363d; border-radius: 8px; padding: 14px; background: #111820; }
.module h2 { margin: 0; font-size: 15px; }
.module p { margin: 6px 0 0; color: #8b949e; line-height: 1.4; }
.pipeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }
.stage { min-height: 220px; border: 1px solid #30363d; border-radius: 8px; padding: 12px; background: #0d1117; }
.deal { margin-top: 10px; border: 1px solid #30363d; border-radius: 6px; padding: 10px; background: #161b22; }
.toolbar { display: flex; gap: 8px; margin: 16px 0; }
.toolbar input { min-width: 240px; border: 1px solid #30363d; border-radius: 6px; padding: 8px; background: #0d1117; color: #e6edf3; }
.toolbar button { border: 1px solid #2ea043; border-radius: 6px; padding: 8px 12px; color: #0d1117; background: #3fb950; }
@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .grid, .pipeline, .modules { grid-template-columns: 1fr; }
}
"""


def _web_layout(product_name: str) -> str:
    return f'''import "./globals.css";

export const metadata = {{
  title: "{product_name}",
  description: "Generated CRM workspace"
}};

export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  );
}}
'''


def _web_page(product_name: str) -> str:
    return f'''"use client";

import {{ Activity, Building2, CircleDollarSign, Contact, GitBranch, ShieldCheck, Users, Workflow }} from "lucide-react";

const metrics = [
  {{ label: "Accounts", value: "128", icon: Building2 }},
  {{ label: "Contacts", value: "842", icon: Contact }},
  {{ label: "Open Deals", value: "37", icon: Users }},
  {{ label: "MRR", value: "$42.6k", icon: CircleDollarSign }},
  {{ label: "Workflow Runs", value: "1,284", icon: Workflow }},
  {{ label: "Compliance Events", value: "9,841", icon: ShieldCheck }}
];

const stages = [
  {{ name: "Qualified", deals: ["Acme expansion", "Northwind onboarding"] }},
  {{ name: "Proposal", deals: ["Globex annual plan", "Initech migration"] }},
  {{ name: "Negotiation", deals: ["Umbrella enterprise"] }},
  {{ name: "Won", deals: ["Stark support renewal"] }}
];

const operatingModules = [
  {{ title: "Tenant isolation", detail: "Every CRM query is scoped by X-Tenant-ID.", icon: Building2 }},
  {{ title: "Granular RBAC", detail: "Owner, admin, manager, contributor, and viewer roles.", icon: ShieldCheck }},
  {{ title: "Stripe billing", detail: "Checkout, portal, and signed webhook endpoints.", icon: CircleDollarSign }},
  {{ title: "Workflow engine", detail: "Rule/action automations for domain events.", icon: Workflow }},
  {{ title: "Integrations", detail: "Signed webhooks and provider connection boundaries.", icon: GitBranch }},
  {{ title: "Audit trail", detail: "Security and business activity are compliance-ready.", icon: Activity }}
];

export default function Home() {{
  return (
    <main className="shell">
      <aside className="sidebar">
        <h1>{product_name}</h1>
        <p>Premium multi-tenant SaaS operations: CRM, billing, workflows, integrations, RBAC, and compliance.</p>
        <div className="tenant-pill">Tenant: enterprise-demo</div>
      </aside>
      <section className="main">
        <div className="toolbar">
          <input aria-label="Search CRM" placeholder="Search accounts, contacts, deals..." />
          <button type="button">New workflow</button>
          <button type="button">New deal</button>
        </div>
        <div className="grid">
          {{metrics.map((metric) => {{
            const Icon = metric.icon;
            return (
              <article className="card" key={{metric.label}}>
                <Icon size={{18}} />
                <h2>{{metric.value}}</h2>
                <p>{{metric.label}}</p>
              </article>
            );
          }})}}
        </div>
        <div className="modules">
          {{operatingModules.map((module) => {{
            const Icon = module.icon;
            return (
              <article className="module" key={{module.title}}>
                <Icon size={{18}} />
                <div>
                  <h2>{{module.title}}</h2>
                  <p>{{module.detail}}</p>
                </div>
              </article>
            );
          }})}}
        </div>
        <div className="pipeline">
          {{stages.map((stage) => (
            <section className="stage" key={{stage.name}}>
              <h2>{{stage.name}}</h2>
              {{stage.deals.map((deal) => <div className="deal" key={{deal}}>{{deal}}</div>)}}
            </section>
          ))}}
        </div>
      </section>
    </main>
  );
}}
'''


def _web_api() -> str:
    return '''const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getDashboard() {
  const response = await fetch(`${API_URL}/dashboard`, { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load dashboard");
  return response.json();
}
'''


def _web_e2e(product_name: str) -> str:
    return f'''import {{ expect, test }} from "@playwright/test";

test("loads CRM dashboard", async ({{ page }}) => {{
  await page.goto("/");
  await expect(page.getByText("{product_name}")).toBeVisible();
  await expect(page.getByRole("button", {{ name: "New deal" }})).toBeVisible();
}});
'''


def _schema_sql() -> str:
    return """CREATE TABLE IF NOT EXISTS tenants (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(180) NOT NULL,
  slug VARCHAR(120) UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(36) PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  name VARCHAR(120) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memberships (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(80) NOT NULL DEFAULT 'owner',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash VARCHAR(255) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(180) NOT NULL,
  industry VARCHAR(120) NOT NULL DEFAULT 'General',
  website VARCHAR(255),
  owner_id VARCHAR(36) REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contacts (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  name VARCHAR(160) NOT NULL,
  email VARCHAR(255) NOT NULL,
  role VARCHAR(120) NOT NULL DEFAULT 'Decision maker',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deals (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  name VARCHAR(180) NOT NULL,
  stage VARCHAR(80) NOT NULL DEFAULT 'qualified',
  value NUMERIC(12, 2) NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activities (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  kind VARCHAR(80) NOT NULL DEFAULT 'note',
  summary VARCHAR(240) NOT NULL,
  due_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plans (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  price_cents INTEGER NOT NULL DEFAULT 0,
  features_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  plan_id VARCHAR(36) NOT NULL REFERENCES plans(id),
  status VARCHAR(80) NOT NULL DEFAULT 'trialing',
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoices (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  amount_cents INTEGER NOT NULL,
  status VARCHAR(80) NOT NULL DEFAULT 'draft',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS integration_connections (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider VARCHAR(120) NOT NULL,
  status VARCHAR(80) NOT NULL DEFAULT 'configured',
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_definitions (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(180) NOT NULL,
  trigger_name VARCHAR(120) NOT NULL,
  definition_json TEXT NOT NULL DEFAULT '{}',
  enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS audit_log (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(36),
  actor_id VARCHAR(36),
  event_type VARCHAR(120) NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
"""


def _spec(product_name: str, idea: str) -> str:
    return f"""# {product_name} Specification

Original idea: {idea}

## Core Workflows

- Register and log in.
- Manage accounts and contacts.
- Track deals through qualified, proposal, negotiation, and won stages.
- View dashboard metrics for accounts, contacts, open deals, and pipeline value.
- Run locally through Docker Compose.

## Acceptance Criteria

- API exposes health, auth, dashboard, accounts, contacts, and deals endpoints.
- Frontend renders a CRM workspace without external services.
- Database schema supports users, accounts, contacts, and deals.
- Secrets are provided through `.env`.
- Unit and E2E test scaffolds are present.
"""


def _architecture(product_name: str) -> str:
    return f"""# {product_name} Architecture

```mermaid
flowchart LR
  Web[Next.js Web] --> API[FastAPI]
  API --> DB[(PostgreSQL)]
  API --> Auth[Password Hashing and Token Issuing]
```

## Boundaries

- `apps/web`: user interface and CRM dashboard.
- `apps/api`: API, auth, business entities, and persistence.
- `database`: reference SQL schema; runtime schema changes are applied through Alembic.
- `docs`: generated architecture, security, and product notes.
"""


def _domain_model_doc(product_name: str) -> str:
    return f"""# {product_name} Domain Model

## Core Domains

- Identity: users, refresh tokens, memberships.
- Tenancy: tenant records and tenant-scoped business data.
- CRM: accounts, contacts, deals, activities.
- Billing: plans, subscriptions, invoices.
- Automation: workflow definitions and future workflow runs.
- Integrations: external provider connections and webhook boundaries.
- Audit: append-only security and business event history.

## Permission Model

Recommended roles:

- `owner`: full tenant administration.
- `admin`: user, billing, integration, and workflow management.
- `manager`: CRM pipeline and reporting management.
- `contributor`: create and update assigned CRM records.
- `viewer`: read-only access.

Every endpoint that reads or mutates tenant data should require tenant context and role checks.
"""


def _production_hardening_doc() -> str:
    return """# Production Hardening Plan

## Authentication

- Rotate refresh tokens on every use.
- Store only refresh token hashes.
- Add account lockout and suspicious-login audit events.
- Enforce strong password policy or external identity provider.

## Authorization

- Enforce tenant-scoped queries at repository boundaries.
- Permission dependencies are scaffolded through `app/rbac.py`.
- Add service-account scopes for integrations.

## Platform Security

- Add rate limiting at API gateway or middleware.
- Set strict CORS by environment.
- Security headers and CSP are scaffolded in `app/security_headers.py`.
- Move secrets to a vault provider.
- Add dependency scanning and image scanning in CI.

## Reliability

- Use Alembic for all schema changes.
- Add backups and restore drills.
- Add structured app logs, metrics, and trace IDs.
- Add queue workers for workflows and integrations.
"""


def _compliance_doc() -> str:
    return """# Compliance Baseline

## Implemented Scaffold

- Tenant-scoped business endpoints require `X-Tenant-ID`.
- RBAC permissions are centralized in `app/rbac.py`.
- Stripe billing endpoints avoid hard-coded secrets and require environment configuration.
- Signed integration webhooks use HMAC verification.
- Security headers include CSP, frame denial, MIME sniffing protection, referrer policy, and permissions policy.
- GitHub Actions runs secret scanning, API tests, web build, and Docker Compose validation.

## Before Internet Deployment

- Move secrets to a managed vault.
- Add persistent audit log storage with retention policy.
- Add rate limiting at gateway or middleware.
- Add refresh token rotation and replay detection.
- Add tenant-aware database indexes and repository-level policy tests.
- Add SAST, dependency scanning, image scanning, and SBOM generation.
- Add backup/restore drills and incident runbooks.
"""


def _security_doc() -> str:
    return """# Security

- Do not commit `.env`.
- Replace `JWT_SECRET` before sharing the app.
- Passwords are stored with PBKDF2 hashes.
- CORS is environment-controlled.
- Database credentials live in environment variables.
- Stripe, webhook, and provider secrets live in environment variables or vault-backed runtime secrets.
- Add gateway rate limiting and refresh-token rotation before internet deployment.
"""


def _github_ci() -> str:
    return """name: Generated App CI

on:
  push:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - name: Secret scan
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Compose config
        run: docker compose config --quiet
      - name: API tests
        working-directory: apps/api
        run: |
          pip install -r requirements.txt
          pytest -q
      - name: Web build
        working-directory: apps/web
        run: |
          npm install
          npm run build
      - name: Docker Compose build
        run: docker compose build

  deploy:
    needs: validate
    if: github.ref == 'refs/heads/main' && vars.ENABLE_CLOUD_DEPLOY == 'true'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Deploy placeholder
        run: |
          echo "Connect this step to AWS ECS, Azure Container Apps, Fly.io, Render, or your preferred platform."
          echo "Required secrets: REGISTRY_URL, REGISTRY_USERNAME, REGISTRY_PASSWORD, DATABASE_URL, JWT_SECRET, STRIPE_SECRET_KEY."
"""


def _api_domain_blueprint(product_name: str) -> str:
    return f'''"""Advanced production domain blueprint for {product_name}.

This file documents domain modules that are intentionally separated from
transport code so future agents can implement them incrementally.
"""

DOMAIN_CAPABILITIES = {{
    "multi_tenancy": [
        "tenant isolation on every business row",
        "membership-based tenant access",
        "tenant-aware audit log",
    ],
    "rbac": [
        "roles: owner, admin, manager, contributor, viewer",
        "permission checks per endpoint",
        "least-privilege service accounts",
    ],
    "billing": [
        "plans",
        "subscriptions",
        "invoices",
        "payment provider adapter boundary",
    ],
    "workflows": [
        "pipeline automations",
        "activity reminders",
        "webhook triggers",
        "workflow run history",
    ],
    "integrations": [
        "email provider adapter",
        "calendar provider adapter",
        "webhook signing",
        "CRM import/export",
    ],
    "hardening": [
        "refresh token rotation",
        "rate limiting",
        "CSP and security headers",
        "secret manager adapter",
        "dependency scanning",
    ],
}}
'''


def _roadmap() -> str:
    return """# Roadmap

- Connect Stripe products, prices, and webhook events to persistent subscription state.
- Add OAuth/SAML enterprise identity providers.
- Add queue workers for long-running workflow actions.
- Add provider-specific email, calendar, Slack, and CRM sync adapters.
- Add tenant-aware repository tests for every business entity.
- Replace placeholder cloud deploy step with your chosen platform.
"""


def _package_windows_script() -> str:
    return """$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to package the Windows desktop app."
}

Push-Location "apps\\desktop"
npm install
npm run package
Pop-Location

$Release = Join-Path $Root "release"
New-Item -ItemType Directory -Force -Path $Release | Out-Null
$DesktopDist = Join-Path $Root "apps\\desktop\\dist"
Compress-Archive -Path (Join-Path $DesktopDist "*") -DestinationPath (Join-Path $Release "windows-desktop.zip") -Force
Write-Host "Windows desktop package: $Release\\windows-desktop.zip"
"""


def _start_script() -> str:
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\\..
docker compose up --build
"""


def _test_script() -> str:
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\\..
docker compose run --rm api pytest
docker compose run --rm web npm run e2e
"""
