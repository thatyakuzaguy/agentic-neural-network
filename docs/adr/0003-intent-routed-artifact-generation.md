# ADR 0003: Intent-Routed Artifact Generation

## Status

Accepted

## Context

The first artifact generator always used the SaaS/CRM starter template. That was acceptable for prompts such as "Build me a SaaS CRM", but it failed for non-SaaS requests. A prompt for a playable 3D Pong game produced a dashboard because the orchestration engine called the SaaS template directly.

This is a product correctness issue, not a visual issue. The generator must choose an artifact family before writing files.

## Decision

Artifact generation now passes through `artifact_router.py`.

- Game prompts are classified before generation.
- SaaS prompts continue to use the SaaS production template.
- Unrecognized web app prompts currently fall back to the SaaS-capable full-stack template until more artifact families exist.
- Game projects use a dedicated playable canvas template with score, AI opponent, controls, Docker packaging, tests, and desktop packaging scaffolding.
- Lifecycle migration validation checks for generic Alembic structure instead of CRM-specific tables.

## Consequences

- A Pong prompt can no longer silently produce the CRM dashboard.
- Tests assert that game prompts contain game markers and do not contain SaaS dashboard markers.
- Future project families should be added behind the router instead of branching inside the main orchestration engine.

## Follow-Up Work

- Add more specialized artifact families for CLI tools, mobile apps, browser extensions, data pipelines, AI services, and native games.
- Replace keyword scoring with provider-assisted classification plus deterministic fallbacks.
- Add artifact-family compatibility checks to the approval center so incompatible diffs can be blocked before file approval.
