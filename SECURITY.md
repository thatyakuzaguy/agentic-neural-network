# Security Policy

## Supported Version

ANN is currently a public alpha. Security fixes are applied to the latest
revision on the default branch; older snapshots are not supported.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability that could expose secrets,
execute unapproved commands, escape a workspace, or modify protected files.
Use GitHub's private vulnerability reporting feature on this repository.

Include the affected revision, reproduction steps, expected and observed
behavior, and any relevant audit artifact with secrets removed. A maintainer
will acknowledge a complete report as soon as practical and coordinate a fix
before public disclosure.

## Security Boundaries

ANN is designed around explicit approval, filesystem policy, terminal
allowlists, bounded retry loops, sequential model loading, and audit artifacts.
Those controls reduce risk; they do not make generated code trustworthy by
default. Review patches, use disposable project workspaces, keep credentials
outside source control, and independently assess generated software before
production use.

The repository does not distribute model weights, private adapters, training
datasets, runtime databases, approval tokens, generated projects, or local
environment files.
