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

The release gate fails on high or critical production dependency findings.
As of `0.1.4-rc.3`, npm reports two moderate findings in the PostCSS copy nested
inside Next.js. npm's proposed fix incorrectly downgrades Next to 9.3.3 and is
not applied. The application pins the newest compatible Next release available
during validation, uses no dynamic user-authored CSS serialization, and enables
Dependabot so the nested fix can be adopted when upstream publishes it.

## Release Candidate Status

The [`v0.1.4-rc.3`](https://github.com/thatyakuzaguy/agentic-neural-network/releases/tag/v0.1.4-rc.3)
source candidate is published from commit
`aca2c5ad10443df5073fd919d79e878c8f5e55bd`. It passed the development-tree
Python suite, Ruff, frontend checks, Docker Compose, embedded runtime,
split-bundle, installed API, and native Desktop gates. The exact public export
then passed 1,533 tests with 54 explicitly skipped private-evidence tests, and
all seven GitHub workflows completed successfully. Its nine release assets
(4,396,352,636 bytes) were compared with the local files by size and GitHub's
SHA-256 digest.

The candidate remains intentionally a prerelease. ANN must not be declared
`FINAL_RELEASE_READY` until both of these external gates have real, matching
evidence:

- timestamped Authenticode signatures from a trusted code-signing certificate;
- transferred validation evidence from a separate clean Windows 11 machine.

Unsigned source and Desktop artifacts may be evaluated with the limitations
clearly disclosed. They are not the trusted Windows installer channel.

## Binary Release

Desktop binaries are release assets, not Git-tracked source. Unsigned builds
must be labeled clearly. A public “trusted publisher” experience requires a
code-signing certificate and timestamped Authenticode signature.
