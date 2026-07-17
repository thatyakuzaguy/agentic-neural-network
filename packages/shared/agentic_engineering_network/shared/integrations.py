from __future__ import annotations

from dataclasses import asdict, dataclass
import os


@dataclass(frozen=True)
class IntegrationStatus:
    provider: str
    category: str
    mode: str
    configured: bool
    required_env: list[str]


def get_integration_statuses() -> list[dict[str, object]]:
    definitions = [
        ("stripe", "payments", ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID"]),
        ("mock_email", "email", []),
        ("sendgrid", "email", ["SENDGRID_API_KEY"]),
        ("mock_analytics", "analytics", []),
        ("posthog", "analytics", ["POSTHOG_API_KEY", "POSTHOG_HOST"]),
        ("mock_storage", "storage", []),
        ("s3", "storage", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_BUCKET"]),
        ("mock_auth", "auth", []),
        ("auth0", "auth", ["AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"]),
        ("mock_notifications", "notifications", []),
        ("slack", "notifications", ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"]),
    ]
    statuses = []
    for provider, category, required_env in definitions:
        configured = all(os.environ.get(name) for name in required_env)
        mode = "mock" if provider.startswith("mock_") or not configured else "real"
        statuses.append(asdict(IntegrationStatus(provider, category, mode, configured, required_env)))
    return statuses

