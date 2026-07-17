# Changelog

## 0.1.1 - 2026-06-05

### Changed

- Added an Electron desktop shell that opens the workbench in a native Windows app window.
- Added draggable, resizable workbench panels.
- Added per-panel detach support for separate desktop/browser windows.
- Reworked the primary prompt area into a Codex-style console with progress events under assistant messages.
- Added per-run project workspace directory selection with Windows-to-Docker path mapping.
- Added per-run approval modes: supervised manual approvals and full auto-approval.
- Added run resumption after all supervised approvals are resolved.
- Replaced the placeholder two-file generator with a full-stack SaaS project scaffold generator.
- Added post-approval project lifecycle execution with validation steps, real generated-project Docker Compose build/up, live API/Web health checks, API pytest, web production build, deterministic fix attempts, Qwen/provider diff repair attempts, sandbox manifests, persisted execution results, and release ZIP packaging.
- Added Qwen/provider repair loop for failing generated projects: write repair prompt, request unified diff, validate with `git apply --check`, apply the diff, and repeat lifecycle validation.
- Changed repair attempts to use configurable `AEN_MAX_REPAIR_ATTEMPTS`, defaulting to 10 with a hard runtime cap.
- Added generated production modules for Stripe billing, tenant context enforcement, granular RBAC, workflow evaluation, signed integration webhooks, security headers, and compliance documentation.
- Added tenant IDs to generated business entities and tenant-scoped API queries for accounts, contacts, deals, activities, and dashboards.
- Expanded generated GitHub Actions with secret scanning, Compose validation/build, API tests, web build, and cloud deployment placeholder.
- Upgraded generated web UI into a premium operations dashboard covering billing, RBAC, workflows, integrations, tenant isolation, and compliance.
- Isolated generated project Compose runs from the parent API container environment so generated database credentials, ports, and URLs do not leak from Agentic Engineering Network.
- Removed generated PostgreSQL schema bind mount from runtime Compose; generated APIs now apply schema through Alembic migrations, which works when Docker is driven from inside the API container.
- Added Docker CLI and Compose plugin to the GPU API image so the backend can operate Docker sandboxes through the Docker Desktop socket.
- Hardened run failure handling so lifecycle exceptions are stored as execution results instead of leaving a run with stale pending approvals.
- Added persisted run state under `data/runs`.
- Added Alembic migration scaffolding, activities domain model, JWT expiration claims, and Windows desktop packaging scaffold to generated projects.
- Rejected Windows drive paths outside `D:\AgenticEngineeringNetwork`.
- Allowed explicitly selected project workspaces elsewhere on the `D:` drive, such as `D:\TesT`, through the `/host-d` Docker mount.
- Applied approved file create/modify requests to disk.
- Changed run submission to execute in the background so the UI no longer appears idle while Qwen is working.
- Added `/api/runs/{run_id}` polling and live `agent.started` audit events.
- Made `llama_cpp` the default local provider.
- Rebuilt the API image with CUDA tooling for `llama-cpp-python`.
- Added NVIDIA GPU passthrough for the API container and configurable local model GPU layers.
- Updated Docker startup to run `postgres`, `api`, and `web` without Ollama by default.
- Documented the Qwen2.5-Coder GGUF hard-link workflow.
- Fixed live health checks from inside the API container by targeting `host.docker.internal`.
- Fixed generated API test imports by setting `PYTHONPATH=/app` in generated API Dockerfiles.

### Verified

- Confirmed direct Qwen inference from `models/qwen2.5-coder-7b-q4_k_m.gguf` while the Ollama container was stopped.
- Confirmed Docker GPU passthrough with NVIDIA GeForce RTX 3060 Ti and Qwen inference using about `5975 MiB` of VRAM.
- Confirmed `Build me a SaaS CRM` completes in full approval mode with Docker config/build/up, live API/Web health checks, API pytest, web build, Docker cleanup, security review, and release ZIP packaging all passing.

## 0.1.0 - 2026-06-04

### Added

- Initial Agentic Engineering Network application.
- Backend FastAPI service.
- Frontend Next.js workbench.
- Multi-agent registry with 13 required agents.
- Orchestration engine and task decomposition.
- Approval center for file, shell, package, and deployment gates.
- Audit log writer.
- Secret scanner and security review workflow.
- Docker Compose with web, api, postgres, and ollama services.
- PowerShell setup, start, stop, and update scripts.
- Python and frontend test scaffolding.
- Architecture, agent, setup, troubleshooting, and roadmap documentation.
- Direct GGUF provider for `qwen2.5-coder:7b` through `llama-cpp-python`.
- Local model hard link at `models/qwen2.5-coder-7b-q4_k_m.gguf`.

### Security

- Host fallback startup is blocked when Docker is missing.
- `.env.example` contains placeholders only.
- Dependency audit currently reports a moderate Next/PostCSS advisory through Next's nested dependency.
