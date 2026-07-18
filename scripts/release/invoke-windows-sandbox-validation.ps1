[CmdletBinding()]
param(
  [string]$SourceRoot = "",
  [string]$RuntimeSource = "D:\ANN\runtime",
  [string]$DesktopSource = "",
  [string]$InstallerRoot = "",
  [string]$BundleRoot = "",
  [string]$OutputRoot = "",
  [string]$SigningEvidencePath = "",
  [string]$ReleaseTransferManifestPath = "",
  [int]$TimeoutSeconds = 1800,
  [switch]$Launch
)

$ErrorActionPreference = "Stop"

function Assert-ReleasePath {
  param([string]$PathValue, [string]$Label)
  $full = [IO.Path]::GetFullPath($PathValue)
  if ($full -match '^[Cc]:\\') {
    throw "$Label must not use C:\: $full"
  }
  if ($full.Length -lt 6) {
    throw "$Label is too shallow: $full"
  }
  return $full
}

function Get-SignatureState {
  param([string]$PathValue)
  if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
    return [pscustomobject]@{ path = $PathValue; status = "MISSING"; timestamped = $false }
  }
  try {
    $signature = Get-AuthenticodeSignature -FilePath $PathValue
    return [pscustomobject]@{
      path = $PathValue
      status = [string]$signature.Status
      timestamped = [bool]$signature.TimeStamperCertificate
    }
  } catch {
    return [pscustomobject]@{ path = $PathValue; status = "UNKNOWN"; timestamped = $false }
  }
}

function ConvertTo-XmlText {
  param([string]$Value)
  return [Security.SecurityElement]::Escape($Value)
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $SourceRoot) {
  $SourceRoot = $repoRoot
}
if (-not $DesktopSource) {
  $DesktopSource = Join-Path $repoRoot "apps\desktop\dist\ANN-win32-x64"
}
if (-not $InstallerRoot) {
  $InstallerRoot = Join-Path $repoRoot "installer"
}
if (-not $BundleRoot) {
  if (Test-Path -LiteralPath (Join-Path $repoRoot "RELEASE_TRANSFER_MANIFEST.json") -PathType Leaf) {
    $BundleRoot = $repoRoot
  } else {
    $BundleRoot = Join-Path $repoRoot "outputs\release_candidates\ANN_RC_HANDOFF"
  }
}
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $repoRoot "outputs\release_final\windows_sandbox"
}

$source = Assert-ReleasePath $SourceRoot "SourceRoot"
$runtime = Assert-ReleasePath $RuntimeSource "RuntimeSource"
$desktop = Assert-ReleasePath $DesktopSource "DesktopSource"
$installer = Assert-ReleasePath $InstallerRoot "InstallerRoot"
$bundle = Assert-ReleasePath $BundleRoot "BundleRoot"
$output = Assert-ReleasePath $OutputRoot "OutputRoot"
if (-not $SigningEvidencePath) {
  $SigningEvidencePath = Join-Path $installer "release_signing_evidence.json"
}
if (-not $ReleaseTransferManifestPath) {
  $ReleaseTransferManifestPath = Join-Path $bundle "RELEASE_TRANSFER_MANIFEST.json"
}
$signingEvidence = [IO.Path]::GetFullPath($SigningEvidencePath)
$transferManifest = [IO.Path]::GetFullPath($ReleaseTransferManifestPath)
$bootstrap = Join-Path $PSScriptRoot "run-windows-sandbox-validation.ps1"
$setup = Join-Path $installer "ANN_Setup.exe"
$uninstall = Join-Path $installer "ANN_Uninstall.exe"
$setupSignature = Get-SignatureState $setup
$uninstallSignature = Get-SignatureState $uninstall
$sandboxCommand = Get-Command "WindowsSandbox.exe" -ErrorAction SilentlyContinue
$sandboxExecutable = if ($sandboxCommand) {
  [string]$sandboxCommand.Source
} else {
  "C:\Windows\System32\WindowsSandbox.exe"
}

$blockers = [Collections.Generic.List[string]]::new()
if (-not (Test-Path -LiteralPath $source -PathType Container)) { $blockers.Add("source_root_missing") }
if (-not (Test-Path -LiteralPath (Join-Path $source "agentic_network") -PathType Container)) { $blockers.Add("source_app_missing") }
if (-not (Test-Path -LiteralPath (Join-Path $source "apps\web\.next\standalone") -PathType Container)) { $blockers.Add("source_web_standalone_missing") }
if (-not (Test-Path -LiteralPath (Join-Path $runtime "python\python.exe") -PathType Leaf)) { $blockers.Add("runtime_python_missing") }
if (-not (Test-Path -LiteralPath (Join-Path $desktop "ANN.exe") -PathType Leaf)) { $blockers.Add("desktop_executable_missing") }
if (-not (Test-Path -LiteralPath $installer -PathType Container)) { $blockers.Add("installer_root_missing") }
if (-not (Test-Path -LiteralPath $bundle -PathType Container)) { $blockers.Add("bundle_root_missing") }
if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) { $blockers.Add("sandbox_bootstrap_missing") }
if ($setupSignature.status -ne "Valid") { $blockers.Add("setup_signature_not_valid") }
if ($uninstallSignature.status -ne "Valid") { $blockers.Add("uninstall_signature_not_valid") }
if (-not $setupSignature.timestamped) { $blockers.Add("setup_timestamp_missing") }
if (-not $uninstallSignature.timestamped) { $blockers.Add("uninstall_timestamp_missing") }
if (-not (Test-Path -LiteralPath $signingEvidence -PathType Leaf)) { $blockers.Add("signing_evidence_missing") }
if (-not (Test-Path -LiteralPath $transferManifest -PathType Leaf)) { $blockers.Add("release_transfer_manifest_missing") }
if (-not (Test-Path -LiteralPath $sandboxExecutable -PathType Leaf)) { $blockers.Add("windows_sandbox_not_enabled") }

New-Item -ItemType Directory -Force -Path $output | Out-Null
$configPath = Join-Path $output "ANN_Final_Release_Validation.wsb"
$planPath = Join-Path $output "windows_sandbox_validation_plan.json"
$evidencePath = Join-Path $output "clean_machine_external_validation.json"
$failurePath = Join-Path $output "windows_sandbox_validation_failed.json"
$completionPath = Join-Path $output "windows_sandbox_validation_completed.json"

$xml = @"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <PrinterRedirection>Disable</PrinterRedirection>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MemoryInMB>8192</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $source)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\source</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $runtime)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\runtime</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $desktop)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\desktop</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $installer)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\installer</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $bundle)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\handoff</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $PSScriptRoot)</HostFolder>
      <SandboxFolder>C:\ANNWork\sources\harness</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(ConvertTo-XmlText $output)</HostFolder>
      <SandboxFolder>C:\ANNOutput</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\ANNWork\sources\harness\run-windows-sandbox-validation.ps1</Command>
  </LogonCommand>
</Configuration>
"@
[IO.File]::WriteAllText($configPath, $xml.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))

$plan = [ordered]@{
  version = "1.0"
  generated_at = [DateTime]::UtcNow.ToString("o")
  status = if ($blockers.Count -eq 0) { "WINDOWS_SANDBOX_VALIDATION_READY" } else { "WINDOWS_SANDBOX_VALIDATION_BLOCKED" }
  launch_requested = [bool]$Launch
  launch_allowed = $blockers.Count -eq 0
  source_root = $source
  runtime_source = $runtime
  desktop_source = $desktop
  installer_root = $installer
  bundle_root = $bundle
  output_root = $output
  config_path = $configPath
  sandbox_executable = $sandboxExecutable
  setup_signature = $setupSignature
  uninstall_signature = $uninstallSignature
  signing_evidence_path = $signingEvidence
  release_transfer_manifest_path = $transferManifest
  blockers = @($blockers)
  network = "DISABLED"
  vgpu = "DISABLED"
  mapped_inputs_read_only = $true
  setup_executed_in_sandbox = $Launch -and $blockers.Count -eq 0
  no_model_load = $true
  no_inference = $true
  no_download = $true
}
[IO.File]::WriteAllText(
  $planPath,
  ($plan | ConvertTo-Json -Depth 6) + "`n",
  [Text.UTF8Encoding]::new($false)
)

Write-Host "Windows Sandbox validation plan: $planPath"
Write-Host "Status: $($plan.status)"
if (-not $Launch) {
  Write-Host "Preparation only. Use -Launch after every blocker is resolved."
  exit 0
}
if ($blockers.Count -gt 0) {
  throw "Windows Sandbox validation is blocked: $($blockers -join ', ')"
}

foreach ($path in @($evidencePath, $failurePath, $completionPath)) {
  if (Test-Path -LiteralPath $path -PathType Leaf) {
    Remove-Item -LiteralPath $path -Force
  }
}
Start-Process -FilePath $configPath | Out-Null
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline) {
  if (Test-Path -LiteralPath $failurePath -PathType Leaf) {
    throw "Windows Sandbox validation failed. See $failurePath"
  }
  if (Test-Path -LiteralPath $completionPath -PathType Leaf) {
    $completion = Get-Content -LiteralPath $completionPath -Raw | ConvertFrom-Json
    if ($completion.status -ne "PASSED") {
      throw "Windows Sandbox returned an unexpected status: $($completion.status)"
    }
    if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
      throw "Windows Sandbox completion marker exists but evidence is missing."
    }
    Write-Host "Windows Sandbox validation passed: $evidencePath"
    exit 0
  }
  Start-Sleep -Seconds 2
}
throw "Timed out waiting for Windows Sandbox validation after $TimeoutSeconds seconds."
