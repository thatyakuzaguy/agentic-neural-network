# Dependency Security

## Active Temporary Exception

`llama-cpp-python` depends on `diskcache 5.6.3`. The Python advisory database
reports `PYSEC-2026-2447` / `CVE-2025-69872`: DiskCache uses pickle for cache
serialization, so an attacker who can replace files in a cache directory may
cause code execution when a trusted process reads them. No fixed DiskCache
release is available as of 2026-07-17.

ANN isolates `llama-cpp-python` in the optional `local-models` dependency group.
The base API, public CI, and CPU API image do not install it. The GPU image and
operators who enable local inference still receive it because it is required by
the selected backend.

Risk controls:

- use local inference only on a single-user, trusted workstation;
- keep model and cache directories on access-controlled local storage;
- never restore model caches from untrusted archives or shared writable paths;
- do not expose the llama.cpp cache directory to generated project containers;
- preserve ANN's protected-path and sequential-runtime policies;
- audit the optional requirements for every release and remove this exception
  immediately when a fixed upstream version is available.

The GitHub security workflow ignores only `PYSEC-2026-2447` for the optional
requirements file; any additional advisory still fails the job. Review date:
2026-08-17.

## JavaScript Findings

`npm audit` currently reports two moderate findings in a PostCSS version nested
inside Next.js. There are no high or critical production findings. npm proposes
a breaking downgrade to Next 9.3.3, so ANN keeps the current Next 16.2 release,
does not accept untrusted dynamic CSS serialization, and relies on Dependabot
to adopt the upstream correction when a compatible release becomes available.
