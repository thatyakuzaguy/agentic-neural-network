# ADR 0002: Senior Gates And Scorecards

Status: Accepted

## Context

The platform previously described limitations honestly but did not have a common machine-readable way to block weak product plans, critical security issues, or release readiness failures.

## Decision

Use `SeniorGateResult` and `QualityScorecard` as the shared contract. Every senior gate returns:

- status
- score
- findings
- risks
- required fixes
- optional improvements
- human review notes

## Consequences

The UI can show comparable scores across product, architecture, code, tests, security, compliance, UX, and deployment. Release is blocked when critical gates fail, while legal/compliance still requires human review.
