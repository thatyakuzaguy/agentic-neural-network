# ANN Windows Installer

This folder contains ANN's offline Windows installer, verifier, launcher, and
uninstaller. The installer never downloads dependencies or model weights.

## Layout

Default install root:

```text
D:\ANN
  agentic_network
  apps
  packages
  scripts
  desktop
  data
  projects
  outputs
  logs
  models
  adapters
  config
  runtime
```

## Split GitHub Release

The embedded CUDA runtime makes the offline archive larger than GitHub's
per-asset limit. Download every `.partNNN` asset plus
`ANN_RELEASE_PARTS.json`, `ANN_RELEASE_PARTS.sha256`, and
`assemble_release.ps1`, then follow `README_OFFLINE_RELEASE.md`. The assembler
verifies each part and the reconstructed archive. `ANN_Setup.exe` independently
verifies every payload file before installation.

## Install

### Source and runtime

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install_ann.ps1 `
  -SourceRoot D:\AgenticEngineeringNetwork `
  -InstallRoot D:\ANN `
  -RuntimeSource D:\ANN\runtime `
  -DesktopSource "D:\AgenticEngineeringNetwork\apps\desktop\dist\ANN-win32-x64"
```

### Complete offline installation with local models

ANN does not redistribute model weights. Prepare an authorized local model
pack containing `MODEL_PACK_MANIFEST.json`, then install it with exact size and
SHA-256 verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install_ann.ps1 `
  -SourceRoot D:\AgenticEngineeringNetwork `
  -InstallRoot D:\ANN `
  -RuntimeSource D:\ANN\runtime `
  -DesktopSource "D:\AgenticEngineeringNetwork\apps\desktop\dist\ANN-win32-x64" `
  -ModelSource D:\AgenticEngineeringNetwork\outputs\release_final\model_pack `
  -ModelInstallMode HardLink `
  -RequireModels
```

Use `-ModelInstallMode Copy` when the source and destination are on different
volumes or when the installed copy must be independent. `HardLink` avoids
duplicating model bytes but requires both paths to be on the same NTFS volume.

The convenience wrapper uses the default payload locations:

```bat
installer\ANN_Setup.bat
```

For automated smoke validation without creating a desktop shortcut:

```powershell
installer\ANN_Setup.exe -InstallRoot D:\ANN -SkipShortcut
```

## Launch

The installer creates a desktop shortcut that runs:

```powershell
powershell -ExecutionPolicy Bypass -File D:\ANN\installer\ann_launcher.ps1
```

The launcher opens the packaged native Desktop executable. If that executable
is unavailable, its local fallback sets `PYTHONPATH` to the installed app root
and runs:

```powershell
python -m agentic_network.desktop_app.run
```

## Uninstall

By default uninstall preserves `projects`, `models`, `outputs`, and `data`.

```powershell
powershell -ExecutionPolicy Bypass -File installer\uninstall_ann.ps1 -InstallRoot D:\ANN
```

Use `-RemoveProjects`, `-RemoveModels`, or `-RemoveOutputs` only when you intentionally want to delete those folders.

## Validate Installation

Verify the installed runtime and Desktop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\ANN\installer\verify_install.ps1 -InstallRoot D:\ANN
```

For an installation that includes the complete local model pack, also verify
the required model files and CUDA-enabled llama.cpp binding:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\ANN\installer\verify_install.ps1 -InstallRoot D:\ANN -RequireModels
```

Local smoke validation verifies the installed layout without loading models, running inference, downloading packages, or installing dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File installer\validate_clean_machine.ps1 -InstallRoot D:\ANN -EnvironmentType local_smoke
```

Final release validation must be run on a separate clean Windows 11 machine after installing ANN:

```powershell
powershell -ExecutionPolicy Bypass -File installer\validate_clean_machine.ps1 -InstallRoot D:\ANN -EnvironmentType clean_machine -RequireSignedInstaller -SigningEvidencePath installer\release_signing_evidence.json -ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json
```

That command writes:

```text
D:\ANN\clean_machine_external_validation.json
```

ANN only treats clean-machine evidence as final-release sufficient when that file reports `status: PASSED` and `environment_type: clean_machine`.

When `-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json` is supplied, the clean-machine marker records two independent transfer-manifest proofs:

- `release_transfer_manifest_sha256`: SHA256 of the actual `RELEASE_TRANSFER_MANIFEST.json` file copied to the clean machine.
- `release_transfer_manifest_aggregate_sha256`: the canonical `aggregate_sha256` value inside `RELEASE_TRANSFER_MANIFEST.json`.

Final release verification requires both values to match the verified handoff bundle.

The handoff bundle also includes two sidecars for manual inspection:

- `RELEASE_TRANSFER_MANIFEST.file.sha256`: SHA256 of the actual `RELEASE_TRANSFER_MANIFEST.json` file.
- `RELEASE_TRANSFER_MANIFEST.sha256`: canonical `aggregate_sha256` for the files declared by the transfer manifest.

## Verify Final Release Gate

After signing and clean-machine validation, run the aggregate final release verifier:

```powershell
$env:PYTHONPATH="."
python scripts\runtime\verify_final_release.py --install-root D:\ANN --installer-root installer --bundle-root outputs\release_candidates\ANN_RC_HANDOFF --clean-machine-marker D:\ANN\clean_machine_external_validation.json --signing-evidence installer\release_signing_evidence.json --certificate-thumbprint "<CERT_THUMBPRINT>" --output-dir outputs\runtime_finalization_20260707
```

That repo-root command is the canonical final release path contract. The transferred handoff bundle may use `--bundle-root .` only when the current working directory is the handoff bundle root.

The final release verifier checks:

- `installer-root` is `installer`.
- `bundle-root` is `outputs/release_candidates/ANN_RC_HANDOFF` when run from the repository root.
- `signing-evidence` is `installer\release_signing_evidence.json`.
- `clean-machine-marker` is `D:\ANN\clean_machine_external_validation.json`.
- release signing plan safety, external evidence safety, and operator environment safety remain read-only and non-mutating.

Exit codes:

- `0`: all release gates passed and ANN is `FINAL_RELEASE_READY`.
- `2`: release is still blocked; read the printed blockers and `362_final_release_verification.json`.

The verifier is read-only. It does not install packages, download files, sign binaries, load models, or run inference.

## Sign Release Binaries

Release binaries must be signed with a real trusted code-signing certificate. The signing script is dry-run by default:

All commands that show `<CERT_THUMBPRINT>` are templates. Replace it with the real 40-character hexadecimal SHA1 thumbprint of the trusted Authenticode certificate. `sign_release.ps1` refuses placeholders and malformed thumbprints even in dry-run mode.

Before signing, verify the release operator environment can see `signtool.exe` and the trusted Authenticode certificate:

ANN checks `PATH` first and then discovers the newest x64 SignTool under the
installed Windows SDK. The signing script also accepts an explicit
`-SigntoolPath` override. Installing the Windows SDK Signing Tools is therefore
required only when neither location contains `signtool.exe`.

```powershell
$env:PYTHONPATH="."
python scripts\runtime\verify_release_operator_environment.py --installer-root installer --certificate-thumbprint "<CERT_THUMBPRINT>" --output-dir outputs\runtime_finalization_20260707
```

```powershell
powershell -ExecutionPolicy Bypass -File installer\sign_release.ps1 -CertificateThumbprint "<CERT_THUMBPRINT>" -TimestampUrl http://timestamp.digicert.com
```

Explicit Windows SDK path example:

```powershell
powershell -ExecutionPolicy Bypass -File installer\sign_release.ps1 `
  -SigntoolPath "C:\Program Files (x86)\Windows Kits\10\bin\10.0.28000.0\x64\signtool.exe" `
  -CertificateThumbprint "<CERT_THUMBPRINT>" `
  -TimestampUrl http://timestamp.digicert.com
```

To sign on the release machine after reviewing the dry-run command plan:

```powershell
powershell -ExecutionPolicy Bypass -File installer\sign_release.ps1 -CertificateThumbprint "<CERT_THUMBPRINT>" -TimestampUrl http://timestamp.digicert.com -OutputPath installer\release_signing_evidence.json -Execute
```

### Isolated Windows Sandbox validation

ANN includes a preparation-first Windows Sandbox harness for the final clean
Windows 11 evidence step. It maps the release source, embedded runtime, Desktop
payload, signed installer, and handoff bundle read-only; executes
`ANN_Setup.exe` inside the clean sandbox; then validates the fresh `D:\ANN`
installation. Networking, vGPU, clipboard, audio, video, and printer
redirection are disabled, and only the evidence directory is writable from the
sandbox. It reuses `validate_clean_machine.ps1` and cannot replace the trusted
certificate gate.

Prepare the `.wsb` file and inspect blockers without launching anything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\invoke-windows-sandbox-validation.ps1 `
  -SourceRoot D:\AgenticEngineeringNetwork `
  -RuntimeSource D:\ANN\runtime `
  -DesktopSource "D:\AgenticEngineeringNetwork\apps\desktop\dist\ANN-win32-x64"
```

After both installers are valid and timestamped, signing evidence exists, the
handoff manifest is verified, and Windows Sandbox is enabled, launch the clean
validation explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\invoke-windows-sandbox-validation.ps1 `
  -SourceRoot D:\AgenticEngineeringNetwork `
  -RuntimeSource D:\ANN\runtime `
  -DesktopSource "D:\AgenticEngineeringNetwork\apps\desktop\dist\ANN-win32-x64" `
  -Launch
```

The harness never downloads dependencies, loads a model, or performs
inference. Windows Sandbox must be enabled by an administrator before `-Launch`
can proceed.

On Windows 11 Pro, Enterprise, or Education, inspect and enable the optional
feature from an elevated PowerShell session, then restart Windows when the
command requests it:

```powershell
Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM
Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
```

Enabling the feature changes the host operating system and is deliberately not
performed by ANN's release scripts. After the restart, confirm that
`C:\Windows\System32\WindowsSandbox.exe` exists before using `-Launch`.

The script requires `signtool.exe` from the Windows SDK and refuses to create or use fake release certificates. Final release verification requires trusted Authenticode signatures with a timestamp authority on both `ANN_Setup.exe` and `ANN_Uninstall.exe`.

The release certificate must be non-expired, non-self-signed, importable with its private key on the release machine, and include the Code Signing Enhanced Key Usage.

The signing script writes `release_signing_evidence.json` with the target file hashes, signature status, signer subject, and timestamp signer. Preserve that file with the release-candidate handoff and clean-machine evidence.

## Exclusions

The installer does not copy:

- `.git`
- historical `outputs`
- `models`
- `training`
- `training/datasets`
- `training/adapters`
- `memory`
- `knowledge`
- `unsloth_compiled_cache`
- `__pycache__`
- `.pytest_cache`
- `.ruff_cache`
- `node_modules`

## Security

The installer does not download models, install packages, run training, modify model files, or touch datasets/adapters. It reports missing runtime dependencies instead of installing them automatically.
