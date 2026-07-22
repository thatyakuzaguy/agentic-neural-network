# Changelog

## Unreleased

## 0.1.5 - 2026-07-22

- Pinned Sharp 0.35.3 and PostCSS 8.5.20 across the npm workspace and lockfile
  to remove newly disclosed production dependency vulnerabilities.
- Added regression checks that reject vulnerable root or nested Sharp and
  PostCSS resolutions before a release can pass.
- Documented the workstation used for primary development and validation:
  Ryzen 5 2600, RTX 3060 Ti with 8 GB VRAM, and 32 GB DDR4 memory.
- Rebuilt the unsigned Windows offline distribution from the audited lockfile.
- Installed the native uninstaller with ANN and added deferred self-cleanup so
  complete removal succeeds on Windows without leaving locked files.

## 0.1.4 - 2026-07-21

- Renamed the public product and repository to ANN (Agentic Neural Network),
  while retaining compatibility identifiers used by existing installations.
- Renamed the packaged Windows desktop executable to `ANN.exe` and updated
  installer, validation, and release tooling to the new product identity.
- Validated the complete hermetic Python suite with 1,621 passing tests and
  one intentional skip, plus a clean full Ruff run.
- Validated the production web application with 22 component tests, TypeScript,
  a Next.js standalone build, Playwright, and a packaged Windows Electron app.
- Rebuilt the official API and web containers from a clean Docker cache and
  passed live PostgreSQL, API health/readiness, web, Docker socket, and Compose
  integration smokes.
- Added a reproducible offline release bundle, isolated installer validation,
  embedded runtime integrity checks, and a hash-verified optional model pack.
- Promoted the source and unsigned portable distribution to stable. A trusted
  Windows publisher experience still requires an externally issued
  Authenticode certificate and independent clean-machine signing evidence.

## 0.1.4-rc.3 - 2026-07-18

- Added a preparation-first Windows Sandbox harness for isolated final-release
  validation. It runs the signed setup launcher against read-only release
  inputs, validates a fresh sandbox installation, disables networking, and
  strictly reuses the existing signed clean-machine evidence gate.
- Replaced the contaminated embedded environment with a minimal, exact,
  46-wheel Python 3.11 CUDA runtime and verified llama.cpp GPU offload.
- Added strict embedded-package, wheel-closure, unexpected-distribution, and
  runtime-integrity gates.
- Added a reproducible split offline Windows bundle with per-part and aggregate
  SHA-256 verification for GitHub-compatible release assets.
- Added installer-side payload verification, portable model-path rewriting,
  and fail-closed inference policy when no verified model pack is supplied.
- Reconstructed and installed the release from its split assets, verified all
  16,850 payload files, and passed installed API and native Desktop smokes.
- Fixed clean-machine validation to match the installed application layout and
  distinguish Python model modules from forbidden binary model weights.

## 0.1.4-rc.2 - 2026-07-18

- Added deterministic discovery of the newest x64 Windows SDK SignTool when it
  is installed but absent from `PATH`, with an explicit signing-path override.
- Rebuilt and hash-verified the release-candidate handoff after the signing
  toolchain correction.
- Confirmed that the remaining final-release gates are trusted Authenticode
  signing and transferred validation on a separate clean Windows 11 machine.

## 0.1.4-rc.1 - 2026-07-18

- Added an embedded Windows CUDA DLL bootstrap and verified llama.cpp GPU
  offload in the installed runtime.
- Completed sequential real-model lifecycle validation for Qwen3 4B, Qwen3 8B,
  Qwen2.5-Coder 7B, and DeepSeek-R1-Distill-Qwen 14B.
- Added a hash-verified offline model-pack installer contract with copy and NTFS
  hard-link modes.
- Verified a clean isolated install, native Desktop startup, real local
  conversation inference, safe unload, and zero residual loaded models.
- Hardened role-based routing and shared local providers so specialist stages
  use the configured local model inventory without parallel model loads.
- Fixed standalone CUDA diagnostics and embedded package audits so optional CI
  environments report unavailable bindings without false runtime failures.
- Promoted the public source channel from alpha to release candidate. Trusted
  final Windows release remains blocked on real Authenticode and independent
  clean-machine evidence.

## 0.1.3 - 2026-07-18

### Security

- Restricted the safe terminal to fixed executable mappings and read-only
  allowlisted pytest, Ruff, and package-inspection arguments.
- Replaced path and comment classification regular expressions flagged for
  denial-of-service or ambiguous tag filtering with bounded string parsing.
- Added a release gate that fails CI while the current revision has open high
  or critical CodeQL alerts.

### Changed

- Added regression coverage for blocked pytest plugin loading, arbitrary Python
  modules, and write-capable Ruff arguments.

## 0.1.2 - 2026-07-18

### Changed

- Made public-release hashes reproducible across Windows, Linux, and WSL clones.
- Added executable manifest and local Markdown link verification gates.
- Updated GitHub Actions to their current Node 24-compatible major versions.
- Added CodeQL analysis, issue forms, and a pull request checklist.
- Enabled grouped, non-major Dependabot version updates to reduce review noise.
- Removed the redundant internal public README whose root-relative links were invalid.

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
