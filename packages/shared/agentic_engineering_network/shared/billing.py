from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class StripeConfig:
    secret_key: str
    publishable_key: str
    webhook_secret: str
    price_id: str
    success_url: str
    cancel_url: str
    portal_return_url: str
    mock_mode: bool

    @property
    def configured(self) -> bool:
        return bool(self.secret_key and self.publishable_key and self.webhook_secret and self.price_id)


def get_stripe_config() -> StripeConfig:
    explicit_mock = os.environ.get("STRIPE_MOCK_MODE", "true").lower() in {"1", "true", "yes"}
    config = StripeConfig(
        secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
        publishable_key=os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        price_id=os.environ.get("STRIPE_PRICE_ID", ""),
        success_url=os.environ.get("STRIPE_SUCCESS_URL", "http://localhost:3000/billing/success"),
        cancel_url=os.environ.get("STRIPE_CANCEL_URL", "http://localhost:3000/billing/canceled"),
        portal_return_url=os.environ.get(
            "STRIPE_CUSTOMER_PORTAL_RETURN_URL",
            "http://localhost:3000/settings/billing",
        ),
        mock_mode=explicit_mock,
    )
    return StripeConfig(**{**config.__dict__, "mock_mode": explicit_mock or not config.configured})


class StripeBillingService:
    def __init__(self, config: StripeConfig | None = None) -> None:
        self.config = config or get_stripe_config()

    def status(self) -> dict[str, object]:
        return {
            "provider": "stripe",
            "configured": self.config.configured,
            "mock_mode": self.config.mock_mode,
            "publishable_key_present": bool(self.config.publishable_key),
            "price_id_present": bool(self.config.price_id),
            "webhook_secret_present": bool(self.config.webhook_secret),
        }

    def create_checkout_session(self, customer_email: str, tenant_id: str) -> dict[str, object]:
        if self.config.mock_mode:
            return {
                "mode": "mock",
                "checkout_url": f"http://localhost:3000/mock-billing/checkout?tenant={tenant_id}",
                "customer_email": customer_email,
                "tenant_id": tenant_id,
            }
        stripe = self._stripe_client()
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=customer_email,
            line_items=[{"price": self.config.price_id, "quantity": 1}],
            success_url=self.config.success_url,
            cancel_url=self.config.cancel_url,
            metadata={"tenant_id": tenant_id},
        )
        return {"mode": "stripe", "checkout_url": session.url, "session_id": session.id}

    def create_customer_portal(self, customer_id: str) -> dict[str, object]:
        if self.config.mock_mode:
            return {
                "mode": "mock",
                "portal_url": f"http://localhost:3000/mock-billing/portal?customer={customer_id}",
                "customer_id": customer_id,
            }
        stripe = self._stripe_client()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=self.config.portal_return_url,
        )
        return {"mode": "stripe", "portal_url": session.url, "session_id": session.id}

    def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, object]:
        if self.config.mock_mode:
            return {"mode": "mock", "received": True, "event_type": "mock.event"}
        if not signature:
            raise ValueError("Stripe-Signature header is required.")
        stripe = self._stripe_client()
        event = stripe.Webhook.construct_event(payload, signature, self.config.webhook_secret)
        return {
            "mode": "stripe",
            "received": True,
            "event_id": event.get("id"),
            "event_type": event.get("type"),
        }

    def _stripe_client(self):
        import stripe

        stripe.api_key = self.config.secret_key
        return stripe
