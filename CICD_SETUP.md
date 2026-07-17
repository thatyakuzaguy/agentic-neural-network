# CI/CD Setup

GitHub Actions templates are stored in `.github/workflows`.

## Workflows

- `lint.yml`: Python Ruff and web TypeScript checks.
- `test.yml`: backend pytest, frontend vitest, frontend production build.
- `docker-build.yml`: Docker Compose config and API/web image builds.
- `security-scan.yml`: gitleaks, pip-audit, npm audit.
- `deploy-template.yml`: provider-configurable manual deployment entrypoint.

## Required GitHub Secrets

Set only the secrets your provider actually uses:

```powershell
gh secret set DATABASE_URL --body "postgresql+psycopg://..."
gh secret set OPENAI_API_KEY --body "sk-..."
gh secret set STRIPE_SECRET_KEY --body "sk_live_or_test_..."
gh secret set STRIPE_WEBHOOK_SECRET --body "whsec_..."
gh secret set STRIPE_PRICE_ID --body "price_..."
gh secret set SENDGRID_API_KEY --body "SG..."
gh secret set POSTHOG_API_KEY --body "phc_..."
gh secret set AWS_ACCESS_KEY_ID --body "..."
gh secret set AWS_SECRET_ACCESS_KEY --body "..."
gh secret set SENTRY_DSN --body "https://..."
```

## Required GitHub Variables

```powershell
gh variable set DEPLOY_PROVIDER --body "manual"
gh variable set REGISTRY_IMAGE --body "ghcr.io/<owner>/<repo>/agentic-engineering-network"
```

## Provider Handoff

`deploy-template.yml` intentionally stops after build until a real target is selected. Add provider commands for Fly.io, Render, Azure, AWS, GCP, or another platform after secrets and environments are configured.
