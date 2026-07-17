# Contributing to ANN

Thank you for helping improve ANN. This project values reproducible evidence,
small changes, and explicit safety boundaries.

## Development Setup

1. Use Windows 11 with Python 3.11+ and Node.js 22 LTS.
2. Clone to a path on `D:` when following the default local configuration.
3. Create `.env` from `.env.example`; never commit it.
4. Install Python and npm dependencies using the commands in `README.md`.
5. Keep models, adapters, datasets, generated projects, and run artifacts out
   of Git.

## Before Opening a Pull Request

Run:

```powershell
python -m ruff check agentic_network packages tests/python scripts
python -m pytest tests/python -q
npm --workspace apps/web run lint
npm --workspace apps/web run test
npm --workspace apps/web run build
```

Describe the behavior changed, safety impact, tests run, and remaining risk.
Do not weaken approval gates or path protections to make a test pass.

## Scope

Useful contributions include runtime portability, deterministic orchestration,
failure localization, security gates, provider adapters, desktop accessibility,
tests, and documentation. Large architectural changes should begin with an
issue so their ownership boundaries can be agreed first.
