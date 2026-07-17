# Public Release Exclusions

This source export intentionally excludes local or sensitive runtime material:

- model weights and quantized model files;
- private adapters and training datasets;
- .env, credentials, signing certificates, and approval state;
- memory, knowledge, conversations, logs, outputs, and generated projects;
- databases, tool caches, virtual environments, dependencies, and build output;
- packaged executables and historical release archives.

These exclusions keep the Git history reviewable and prevent machine-local data
from being mistaken for distributable source. Users supply models and secrets
locally after cloning.
