# Integrations

The integration provider abstraction reports health through `/api/integrations/status` and the `Production Readiness` panel.

## Provider Categories

- Email: mock local provider, SendGrid setup path.
- Payments: Stripe mock mode and real Stripe test/live mode.
- Analytics: mock local provider, PostHog setup path.
- Storage: mock local provider, S3-compatible setup path.
- Auth: mock local provider, Auth0/OIDC setup path.
- Notifications: mock local provider, Slack webhook setup path.

## Configuration

Use `.env` variables only. Do not hardcode provider secrets.

```env
EMAIL_PROVIDER=mock
SENDGRID_API_KEY=
ANALYTICS_PROVIDER=mock
POSTHOG_API_KEY=
STORAGE_PROVIDER=mock
S3_BUCKET=
AUTH_PROVIDER=mock
AUTH0_DOMAIN=
NOTIFICATIONS_PROVIDER=mock
SLACK_WEBHOOK_URL=
```

Real providers should be connected one at a time, tested in sandbox/test mode, and reviewed before production.
