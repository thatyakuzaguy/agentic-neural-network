# Limitations

The platform is much stronger than the first scaffold, but these limits remain honest and intentional:

- It cannot guarantee a sellable SaaS from one prompt. Product-market fit, positioning, pricing, and UX need human validation.
- Stripe works in mock mode without keys and test/live mode with real configuration. It cannot create your Stripe account or decide your financial/legal model.
- CI/CD workflows are present, but cloud deployment requires repository ownership, provider accounts, environments, and secrets.
- External integrations have mock providers and health checks. Real accounts must be connected and validated by the operator.
- Compliance templates and checklists do not guarantee GDPR, SOC2, ISO27001, accessibility, or contractual compliance.
- Complex domain logic can be generated and iterated, but deep workflows, edge cases, and third-party dependencies still require review and prompt iteration.
- Intent routing now prevents known game prompts such as Pong from receiving the SaaS dashboard template, but broad arbitrary-project support still depends on adding more artifact families beyond SaaS and canvas games.
- The correction loop is configurable and bounded. It is not literal infinity, because unbounded execution can waste GPU/CPU, disk, API credits, and time.
- Human escalation is required when the model cannot produce a clean diff or lifecycle checks continue to fail.
- Senior gates and scorecards improve review quality, but scores are heuristic until connected to richer generated-project telemetry, real coverage reports, staging data, customer evidence, and human review.
- The compensation system reduces risk with evidence and approvals, but it does not remove the need for qualified human product, architecture, security, legal/compliance, and release owners.
