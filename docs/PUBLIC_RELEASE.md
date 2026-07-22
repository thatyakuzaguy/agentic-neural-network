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
D:\AgenticEngineeringNetwork\releases\github-public\ANN
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

Normal push and pull-request CI runs the repository verifier with
`-AllowContentDrift`. This still rejects unsafe manifest paths, missing files,
new unlisted tracked files, and tracked-file count mismatches, while allowing a
dependency or source PR to change the size and hash of existing files. Without
that mode, every legitimate Dependabot update would fail before its tests ran.

Release preparation must use strict verification after rebuilding the export:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\verify-public-repository.ps1
```

Strict mode validates every recorded byte count and SHA-256 hash. It remains a
release gate and is not replaced by the structural CI check.

The public tree contains `PUBLIC_RELEASE_MANIFEST.json`. When pytest detects
that manifest it visibly skips an explicit allowlist of 53 tests marked
`private_release_evidence`. Those tests require local launcher binaries,
embedded-runtime payloads, wheelhouse contents, signing evidence, model
inference evidence, canonical-install release notes, or historical release
bundles that must not be committed. The Windows CI job maps the source checkout
to the supported `D:\AgenticEngineeringNetwork` path so source-level path
contracts still run rather than being hidden. All portable runtime,
orchestration, safety, API, UI, and project builder tests continue to run. The
development repository runs the private evidence tests because it has no public
manifest.

## Dependency Audit

The release gate fails on moderate, high, or critical production dependency
findings. Next.js still declares vulnerable PostCSS 8.4.31 and Sharp 0.34.x
releases, so ANN applies root overrides to PostCSS 8.5.20 and Sharp 0.35.3 and
verifies that no vulnerable nested copy remains. Both the production-only and
complete npm audits must report zero findings. These overrides are temporary
and must be removed when a stable Next.js release declares patched versions.

## Stable Source Release Status

ANN `v0.1.5` is the stable source and unsigned portable release. The release
gate passed the public CI suite (1,574 passed, 54 intentionally skipped), Ruff,
frontend tests and TypeScript, Next.js production build, Playwright, Electron
packaging, clean Docker image builds, and a live PostgreSQL/API/web Compose
smoke. The release bundle is split into GitHub-compatible parts and protected
by an aggregate manifest and per-file SHA-256 hashes.

The final Windows offline archive is distributed in parts no larger than
1.9 GB. `ANN_RELEASE_PARTS.json` is the normative source for the aggregate
archive size, archive SHA-256, individual part sizes, and per-part SHA-256
values. Verify that manifest against `ANN_RELEASE_PARTS.sha256` before
assembling or installing the release.

Model weights are not Git-tracked or bundled. Users provide models separately,
and the optional model-pack manifest records hashes without granting
redistribution rights.

## Development And Validation Hardware

ANN `v0.1.5` was primarily developed and validated on an AMD Ryzen 5 2600,
an NVIDIA GeForce RTX 3060 Ti with 8 GB of VRAM, and 32 GB of DDR4 system
memory. This is evidence of the tested workstation, not a formal minimum or
recommended hardware requirement.

The source and unsigned portable channels are stable, but ANN must not label
the Windows installer as a trusted-publisher release until both external gates
have real, matching evidence:

- timestamped Authenticode signatures from a trusted code-signing certificate;
- transferred validation evidence from a separate clean Windows 11 machine.

Windows may show a SmartScreen warning for the unsigned portable build. The
user can review the published source, release hashes, and local build evidence
before explicitly allowing it. This is not equivalent to Authenticode trust.

## Binary Release

Desktop binaries are release assets, not Git-tracked source. Unsigned builds
must be labeled clearly. A public “trusted publisher” experience requires a
code-signing certificate and timestamped Authenticode signature.
