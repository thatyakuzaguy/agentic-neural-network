# Stripe Setup

Stripe is mock-first. If keys are missing or `STRIPE_MOCK_MODE=true`, the API returns mock checkout and customer portal URLs.

## Environment Variables

```env
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
STRIPE_SUCCESS_URL=http://localhost:3000/billing/success
STRIPE_CANCEL_URL=http://localhost:3000/billing/canceled
STRIPE_CUSTOMER_PORTAL_RETURN_URL=http://localhost:3000/settings/billing
STRIPE_MOCK_MODE=true
```

## Test Mode Commands

Install and authenticate the Stripe CLI:

```powershell
winget install Stripe.StripeCLI
stripe login
```

Create a test product and recurring price:

```powershell
stripe products create --name "Agentic SaaS Pro"
stripe prices create --currency usd --unit-amount 2900 --recurring interval=month --product prod_REPLACE_WITH_PRODUCT_ID
```

Forward webhooks to the local API:

```powershell
stripe listen --forward-to http://localhost:8000/api/billing/webhook
```

Set local variables in `.env`:

```powershell
(Get-Content .env) `
  -replace '^STRIPE_SECRET_KEY=.*','STRIPE_SECRET_KEY=sk_test_REPLACE' `
  -replace '^STRIPE_PUBLISHABLE_KEY=.*','STRIPE_PUBLISHABLE_KEY=pk_test_REPLACE' `
  -replace '^STRIPE_WEBHOOK_SECRET=.*','STRIPE_WEBHOOK_SECRET=whsec_REPLACE' `
  -replace '^STRIPE_PRICE_ID=.*','STRIPE_PRICE_ID=price_REPLACE' `
  -replace '^STRIPE_MOCK_MODE=.*','STRIPE_MOCK_MODE=false' |
  Set-Content .env
docker compose up -d --build api web
```

## API Checks

```powershell
Invoke-RestMethod http://localhost:8000/api/billing/status
Invoke-RestMethod http://localhost:8000/api/billing/checkout -Method Post -ContentType "application/json" -Body '{"customer_email":"buyer@example.com","tenant_id":"demo"}'
Invoke-RestMethod http://localhost:8000/api/billing/portal -Method Post -ContentType "application/json" -Body '{"customer_id":"cus_REPLACE"}'
```

Never commit real Stripe keys.
