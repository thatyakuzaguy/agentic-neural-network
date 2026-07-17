# ADR 0001: Clean Architecture Boundaries

Status: Accepted

## Context

The first implementation had useful packages, but senior review logic, product strategy, requirements validation, security, compliance, and UI concerns were not expressed through a shared gate/score contract.

## Decision

Introduce explicit layers:

- Domain: shared quality primitives such as gates, findings, scorecards, and status.
- Application: product discovery, requirements quality, SDLC, testing strategy, and senior review services.
- Infrastructure: audit logs, Docker, Git, billing providers, integrations, and compliance evidence stores.
- Interface/API: FastAPI routes and Pydantic schemas.
- UI: Next.js workbench panels.

## Consequences

Senior gates and scorecards are reusable from API, UI, agents, and generated-project workflows. Future work should avoid putting product/security/compliance policy directly inside route handlers or React components.
