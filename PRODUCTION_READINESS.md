# Production Readiness

ANN (Agentic Neural Network) exposes a SaaS production-readiness module through `/api/readiness` and the `Production Readiness` workbench panel.

This module reduces launch risk. It does not guarantee that a generated SaaS is sellable, legally compliant, or operationally complete without human product, engineering, security, and legal review.

## Checklist Areas

- Product-market validation: target segment, problem evidence, buyer, ICP, competitor notes, success metrics.
- Pricing: value metric, tiers, trial strategy, coupons, cancellation path, invoice language.
- Onboarding: first-run flow, seed data, role setup, checklist, sample workspace, activation event.
- Billing: Stripe configuration, checkout, customer portal, webhooks, entitlement mapping, failure handling.
- Observability: structured logs, health/readiness endpoints, error tracking, audit events, dashboard plan.
- Support/admin: admin dashboard, impersonation policy, support notes, account recovery, runbooks.
- Deployment: Docker build, environment validation, backup/restore, migrations, rollback, CI/CD gates.

## Operational Flow

1. Refine requirements with `/api/requirements/refine`.
2. Pick or adapt a SaaS template from `/api/saas-templates`.
3. Generate with supervised approval for first runs.
4. Run the lifecycle checks and inspect `.aen/retry-history.json`.
5. Review readiness, compliance, and integration status in the UI.
6. Configure real providers only after local checks pass in mock mode.

## Backup Commands

```powershell
Set-Location D:\AgenticEngineeringNetwork
.\scripts\maintenance\backup-postgres.ps1
.\scripts\maintenance\restore-postgres.ps1 -BackupFile D:\AgenticEngineeringNetwork\backups\<file>.dump
```
