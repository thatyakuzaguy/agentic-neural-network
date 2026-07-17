# Security Policy Template

Security owner review required before production.

## Access Control

- Enforce MFA for administrative systems.
- Use least-privilege roles.
- Review privileged access at least quarterly.

## Application Security

- Require request validation, RBAC, tenant isolation, rate limiting, and audit logs.
- Scan dependencies before release.
- Store secrets only in approved secret stores or environment managers.

## Incident Response

- Triage severity.
- Contain affected systems.
- Preserve audit evidence.
- Notify customers and regulators when required by law and contract.

## Vulnerability Disclosure

Contact: `[security@example.com]`
