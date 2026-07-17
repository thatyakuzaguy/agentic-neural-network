# Public Release Process

ANN uses a clean-room export rather than publishing the development worktree.
The development tree contains local models, runtimes, datasets, generated
projects, conversations, logs, and historical evidence that must not enter Git.

## Build the Public Repository

```powershell
Set-Location D:\AgenticEngineeringNetwork
powershell -ExecutionPolicy Bypass -File scripts\release\build-public-repository.ps1
```

The export is created at:

```text
D:\AgenticEngineeringNetwork\releases\github-public\agentic-neural-network
```

The script:

- copies only allowlisted source and documentation;
- excludes models, adapters, datasets, memory, knowledge, outputs, logs,
  databases, generated projects, caches, build products, and local `.env`;
- replaces machine-specific conversation runtime configuration with a disabled
  portable example;
- rejects private-key markers, known local identity paths, and files larger
  than 25 MiB;
- generates `PUBLIC_RELEASE_MANIFEST.json` with SHA-256 hashes;
- records exclusions in `PUBLIC_RELEASE_EXCLUSIONS.md`.

## Required Validation

Run tests from the exported repository and from a fresh local clone. Run a
secret scanner such as Gitleaks against the complete Git history before push.
Do not publish when tests, lint, build, secret scanning, or size validation
fails.

The public tree contains `PUBLIC_RELEASE_MANIFEST.json`. When pytest detects
that manifest it visibly skips 21 tests marked `private_release_evidence`.
Those tests require local launcher binaries, embedded-runtime payloads, signing
evidence, model inference evidence, or historical release bundles that must not
be committed. All portable runtime, orchestration, safety, API, UI, and project
builder tests still run. The development repository runs the private evidence
tests because it has no public manifest.

## Dependency Audit

The release gate fails on high or critical production dependency findings.
As of `0.1.1`, npm reports two moderate findings in the PostCSS copy nested
inside Next.js. npm's proposed fix incorrectly downgrades Next to 9.3.3 and is
not applied. The application pins the newest compatible Next release available
during validation, uses no dynamic user-authored CSS serialization, and enables
Dependabot so the nested fix can be adopted when upstream publishes it.

## Binary Release

Desktop binaries are release assets, not Git-tracked source. Unsigned builds
must be labeled clearly. A public “trusted publisher” experience requires a
code-signing certificate and timestamped Authenticode signature.
