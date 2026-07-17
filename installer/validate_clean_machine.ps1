param(
  [string]$InstallRoot = "D:\ANN",
  [ValidateSet("local_smoke", "clean_machine")]
  [string]$EnvironmentType = "local_smoke",
  [string]$OutputPath = "",
  [switch]$RequireSignedInstaller,
  [string]$InstallerRoot = "",
  [string]$SigningEvidencePath = "",
  [string]$ReleaseTransferManifestPath = ""
)

$ErrorActionPreference = "Stop"

function Test-BlockedRoot {
  param([string]$PathValue)
  $full = [System.IO.Path]::GetFullPath($PathValue)
  if ($full -match '^[Cc]:\\') { throw "C:\ install roots are blocked by default." }
  if ($full.Length -lt 6) { throw "Refusing to validate a shallow install root." }
}

function Test-PathCheck {
  param([string]$Id, [bool]$Passed, [string]$Detail)
  [pscustomobject]@{
    id = $Id
    status = if ($Passed) { "PASS" } else { "FAIL" }
    passed = $Passed
    detail = $Detail
  }
}

function Get-SignatureCheck {
  param([string]$PathValue)
  if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
    return [pscustomobject]@{ path = $PathValue; status = "MISSING"; signer = ""; signer_thumbprint_sha256 = ""; timestamp_signer = "" }
  }
  try {
    Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
    $sig = Get-AuthenticodeSignature -FilePath $PathValue
    $signerThumbprint = if ($sig.SignerCertificate) { [string]$sig.SignerCertificate.Thumbprint } else { "" }
    return [pscustomobject]@{
      path = $PathValue
      status = [string]$sig.Status
      signer = if ($sig.SignerCertificate) { [string]$sig.SignerCertificate.Subject } else { "" }
      signer_thumbprint_sha256 = if ($signerThumbprint) { Get-StringSha256 $signerThumbprint.Replace(" ", "").ToUpperInvariant() } else { "" }
      timestamp_signer = if ($sig.TimeStamperCertificate) { [string]$sig.TimeStamperCertificate.Subject } else { "" }
    }
  } catch {
    return [pscustomobject]@{ path = $PathValue; status = "UNKNOWN"; signer = ""; signer_thumbprint_sha256 = ""; timestamp_signer = ""; error = $_.Exception.Message }
  }
}

function Get-FileSha256 {
  param([string]$PathValue)
  if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
    return ""
  }
  try {
    return [string](Get-FileHash -Algorithm SHA256 -LiteralPath $PathValue).Hash.ToLowerInvariant()
  } catch {
    return ""
  }
}

function Get-StringSha256 {
  param([string]$Value)
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $digest = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([System.BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
  } catch {
    return ""
  }
}

function Test-IsSha256 {
  param([string]$Value)
  return ($Value -match '^[0-9a-fA-F]{64}$')
}

function Get-ReleaseTransferManifestAggregateSha256 {
  param([string]$PathValue)
  if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
    return ""
  }
  try {
    $payload = Get-Content -LiteralPath $PathValue -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($payload.aggregate_sha256) {
      return [string]$payload.aggregate_sha256
    }
    return ""
  } catch {
    return ""
  }
}

function Get-MachineIdentityEvidence {
  $computer = [string]$env:COMPUTERNAME
  $domain = [string]$env:USERDOMAIN
  $os = [System.Environment]::OSVersion.VersionString
  $osProductName = ""
  try {
    $osProductName = [string](Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop).Caption
  } catch {
    $osProductName = ""
  }
  $ps = [string]$PSVersionTable.PSVersion
  $fingerprintSource = "$computer|$domain|$os|$osProductName|$ps"
  [pscustomobject]@{
    computer_name_sha256 = Get-StringSha256 $computer
    machine_fingerprint_sha256 = Get-StringSha256 $fingerprintSource
    os_version = $os
    os_product_name = $osProductName
    powershell_version = $ps
  }
}

Test-BlockedRoot $InstallRoot
$root = [System.IO.Path]::GetFullPath($InstallRoot)
if (-not $OutputPath) {
  $OutputPath = Join-Path $root "clean_machine_external_validation.json"
}
if (-not $InstallerRoot) {
  $InstallerRoot = $PSScriptRoot
}

$checks = @(
  (Test-PathCheck "install_root_not_c" ($root -notmatch '^[Cc]:\\') $root),
  (Test-PathCheck "install_manifest" (Test-Path (Join-Path $root "install_manifest.json") -PathType Leaf) (Join-Path $root "install_manifest.json")),
  (Test-PathCheck "app_package" (Test-Path (Join-Path $root "app\agentic_network") -PathType Container) (Join-Path $root "app\agentic_network")),
  (Test-PathCheck "desktop_entrypoint" (Test-Path (Join-Path $root "app\agentic_network\desktop_app\run.py") -PathType Leaf) "desktop_app.run"),
  (Test-PathCheck "runtime_python" (Test-Path (Join-Path $root "runtime\python\python.exe") -PathType Leaf) (Join-Path $root "runtime\python\python.exe")),
  (Test-PathCheck "runtime_wheelhouse" ((Test-Path (Join-Path $root "runtime\wheels") -PathType Container) -and @((Get-ChildItem (Join-Path $root "runtime\wheels") -Filter "*.whl" -File -ErrorAction SilentlyContinue)).Count -gt 0) (Join-Path $root "runtime\wheels")),
  (Test-PathCheck "runtime_config" (Test-Path (Join-Path $root "config\ann_runtime_engine.json") -PathType Leaf) "ann_runtime_engine.json"),
  (Test-PathCheck "model_policy" (Test-Path (Join-Path $root "config\ann_model_policy.json") -PathType Leaf) "ann_model_policy.json"),
  (Test-PathCheck "projects_root" (Test-Path (Join-Path $root "projects") -PathType Container) (Join-Path $root "projects")),
  (Test-PathCheck "models_root" (Test-Path (Join-Path $root "models") -PathType Container) (Join-Path $root "models")),
  (Test-PathCheck "outputs_root" (Test-Path (Join-Path $root "outputs") -PathType Container) (Join-Path $root "outputs")),
  (Test-PathCheck "data_root" (Test-Path (Join-Path $root "data") -PathType Container) (Join-Path $root "data")),
  (Test-PathCheck "protected_training_not_copied" (-not (Test-Path (Join-Path $root "app\training"))) "training excluded"),
  (Test-PathCheck "protected_models_not_copied_to_app" (-not (Test-Path (Join-Path $root "app\models"))) "models excluded"),
  (Test-PathCheck "protected_memory_not_copied" (-not (Test-Path (Join-Path $root "app\memory"))) "memory excluded"),
  (Test-PathCheck "protected_knowledge_not_copied" (-not (Test-Path (Join-Path $root "app\knowledge"))) "knowledge excluded")
)

$setupPath = Join-Path $InstallerRoot "ANN_Setup.exe"
$uninstallPath = Join-Path $InstallerRoot "ANN_Uninstall.exe"
$machineIdentity = Get-MachineIdentityEvidence
$checks += (Test-PathCheck "machine_identity_present" ($null -ne $machineIdentity) "machine identity captured")
$checks += (Test-PathCheck "machine_fingerprint_present" (Test-IsSha256 $machineIdentity.machine_fingerprint_sha256) $machineIdentity.machine_fingerprint_sha256)
$machineOsText = "$($machineIdentity.os_product_name) $($machineIdentity.os_version)"
$checks += (Test-PathCheck "machine_windows11_present" ($machineOsText -match 'Windows 11') $machineOsText)
$setupSignature = Get-SignatureCheck $setupPath
$uninstallSignature = Get-SignatureCheck $uninstallPath
$setupSha256 = Get-FileSha256 $setupPath
$uninstallSha256 = Get-FileSha256 $uninstallPath
$resolvedSigningEvidencePath = ""
$signingEvidenceSha256 = ""
if ($SigningEvidencePath) {
  $resolvedSigningEvidencePath = [System.IO.Path]::GetFullPath($SigningEvidencePath)
  $signingEvidenceSha256 = Get-FileSha256 $resolvedSigningEvidencePath
}
$resolvedReleaseTransferManifestPath = ""
$releaseTransferManifestSha256 = ""
$releaseTransferManifestAggregateSha256 = ""
if ($ReleaseTransferManifestPath) {
  $resolvedReleaseTransferManifestPath = [System.IO.Path]::GetFullPath($ReleaseTransferManifestPath)
  $releaseTransferManifestSha256 = Get-FileSha256 $resolvedReleaseTransferManifestPath
  $releaseTransferManifestAggregateSha256 = Get-ReleaseTransferManifestAggregateSha256 $resolvedReleaseTransferManifestPath
}
if ($RequireSignedInstaller) {
  $checks += (Test-PathCheck "setup_signature_valid" ($setupSignature.status -eq "Valid") $setupSignature.status)
  $checks += (Test-PathCheck "uninstall_signature_valid" ($uninstallSignature.status -eq "Valid") $uninstallSignature.status)
  $checks += (Test-PathCheck "setup_timestamp_present" ($setupSignature.timestamp_signer.Length -gt 0) $setupSignature.timestamp_signer)
  $checks += (Test-PathCheck "uninstall_timestamp_present" ($uninstallSignature.timestamp_signer.Length -gt 0) $uninstallSignature.timestamp_signer)
  $checks += (Test-PathCheck "setup_signer_thumbprint_sha256_present" (Test-IsSha256 $setupSignature.signer_thumbprint_sha256) $setupSignature.signer_thumbprint_sha256)
  $checks += (Test-PathCheck "uninstall_signer_thumbprint_sha256_present" (Test-IsSha256 $uninstallSignature.signer_thumbprint_sha256) $uninstallSignature.signer_thumbprint_sha256)
  $checks += (Test-PathCheck "setup_sha256_present" (Test-IsSha256 $setupSha256) $setupSha256)
  $checks += (Test-PathCheck "uninstall_sha256_present" (Test-IsSha256 $uninstallSha256) $uninstallSha256)
  $checks += (Test-PathCheck "signing_evidence_path_required" ($SigningEvidencePath.Length -gt 0) $(if ($SigningEvidencePath) { $resolvedSigningEvidencePath } else { "missing" }))
  $checks += (Test-PathCheck "release_transfer_manifest_path_required" ($ReleaseTransferManifestPath.Length -gt 0) $(if ($ReleaseTransferManifestPath) { $resolvedReleaseTransferManifestPath } else { "missing" }))
  if ($SigningEvidencePath) {
    $checks += (Test-PathCheck "signing_evidence_sha256_present" (Test-IsSha256 $signingEvidenceSha256) $signingEvidenceSha256)
  }
  if ($ReleaseTransferManifestPath) {
    $checks += (Test-PathCheck "release_transfer_manifest_sha256_present" (Test-IsSha256 $releaseTransferManifestSha256) $releaseTransferManifestSha256)
    $checks += (Test-PathCheck "release_transfer_manifest_aggregate_sha256_present" (Test-IsSha256 $releaseTransferManifestAggregateSha256) $releaseTransferManifestAggregateSha256)
  }
}

$failed = @($checks | Where-Object { -not $_.passed })
$status = if ($failed.Count -eq 0) { "PASSED" } else { "FAILED" }
$payload = [pscustomobject]@{
  version = "18.9.8"
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  status = $status
  environment_type = $EnvironmentType
  machine_identity = $machineIdentity
  install_root = $root
  installer_root = [System.IO.Path]::GetFullPath($InstallerRoot)
  require_signed_installer = [bool]$RequireSignedInstaller
  setup_signature = $setupSignature
  uninstall_signature = $uninstallSignature
  setup_sha256 = $setupSha256
  uninstall_sha256 = $uninstallSha256
  signing_evidence_path = $resolvedSigningEvidencePath
  signing_evidence_sha256 = $signingEvidenceSha256
  release_transfer_manifest_path = $resolvedReleaseTransferManifestPath
  release_transfer_manifest_sha256 = $releaseTransferManifestSha256
  release_transfer_manifest_aggregate_sha256 = $releaseTransferManifestAggregateSha256
  checks = $checks
  blockers = @($failed | ForEach-Object { $_.id })
  no_model_load = $true
  no_inference = $true
  no_download = $true
  no_training = $true
}

New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath -Parent) | Out-Null
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $OutputPath -Encoding UTF8
Write-Host "Clean-machine validation evidence written: $OutputPath"
if ($status -ne "PASSED") {
  exit 1
}
