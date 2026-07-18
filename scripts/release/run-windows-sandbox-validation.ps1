$ErrorActionPreference = "Stop"

$outputRoot = "C:\ANNOutput"
$evidencePath = Join-Path $outputRoot "clean_machine_external_validation.json"
$failurePath = Join-Path $outputRoot "windows_sandbox_validation_failed.json"
$completionPath = Join-Path $outputRoot "windows_sandbox_validation_completed.json"
$substCreated = $false

function Write-FailureEvidence {
  param([string]$Message)
  $payload = [ordered]@{
    version = "1.0"
    generated_at = [DateTime]::UtcNow.ToString("o")
    status = "FAILED"
    environment = "windows_sandbox"
    error = $Message
  }
  [IO.File]::WriteAllText(
    $failurePath,
    ($payload | ConvertTo-Json -Depth 4) + "`n",
    [Text.UTF8Encoding]::new($false)
  )
}

try {
  New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
  foreach ($requiredSource in @(
    "C:\ANNWork\sources\source",
    "C:\ANNWork\sources\runtime\python\python.exe",
    "C:\ANNWork\sources\desktop\ANN.exe",
    "C:\ANNWork\sources\installer\ANN_Setup.exe",
    "C:\ANNWork\sources\handoff\RELEASE_TRANSFER_MANIFEST.json"
  )) {
    if (-not (Test-Path -LiteralPath $requiredSource)) {
      throw "Required read-only release input is missing: $requiredSource"
    }
  }
  if (Test-Path -LiteralPath "D:\") {
    throw "The clean sandbox unexpectedly already has a D: drive."
  }
  & subst.exe D: "C:\ANNWork"
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath "D:\sources" -PathType Container)) {
    throw "Unable to create the isolated D: validation mapping."
  }
  $substCreated = $true

  $setup = "D:\sources\installer\ANN_Setup.exe"
  & $setup `
    -SourceRoot "D:\sources\source" `
    -InstallRoot "D:\ANN" `
    -RuntimeSource "D:\sources\runtime" `
    -DesktopSource "D:\sources\desktop" `
    -SkipShortcut
  if ($LASTEXITCODE -ne 0) {
    throw "ANN_Setup.exe failed in the clean sandbox with exit code $LASTEXITCODE."
  }
  if (-not (Test-Path -LiteralPath "D:\ANN\install_manifest.json" -PathType Leaf)) {
    throw "ANN_Setup.exe did not produce a fresh installation manifest."
  }

  $validator = "D:\sources\installer\validate_clean_machine.ps1"
  if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
    throw "Clean-machine validator is missing from the mapped installer folder."
  }
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validator `
    -InstallRoot "D:\ANN" `
    -EnvironmentType clean_machine `
    -OutputPath $evidencePath `
    -RequireSignedInstaller `
    -InstallerRoot "D:\sources\installer" `
    -SigningEvidencePath "D:\sources\installer\release_signing_evidence.json" `
    -ReleaseTransferManifestPath "D:\sources\handoff\RELEASE_TRANSFER_MANIFEST.json"
  if ($LASTEXITCODE -ne 0) {
    throw "The clean-machine validator rejected the sandbox environment."
  }
  if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
    throw "The validator did not produce clean-machine evidence."
  }
  $evidence = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
  if ($evidence.status -ne "PASSED" -or $evidence.environment_type -ne "clean_machine") {
    throw "The validator produced incomplete clean-machine evidence."
  }
  $evidenceHash = (Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
  $completion = [ordered]@{
    version = "1.0"
    generated_at = [DateTime]::UtcNow.ToString("o")
    status = "PASSED"
    environment = "windows_sandbox"
    evidence_path = $evidencePath
    evidence_sha256 = $evidenceHash
    machine_identity = $evidence.machine_identity
    setup_executed = $true
    fresh_install_manifest = "D:\ANN\install_manifest.json"
    no_model_load = $true
    no_inference = $true
    no_download = $true
  }
  [IO.File]::WriteAllText(
    $completionPath,
    ($completion | ConvertTo-Json -Depth 6) + "`n",
    [Text.UTF8Encoding]::new($false)
  )
} catch {
  Write-FailureEvidence $_.Exception.Message
  exit 1
} finally {
  if ($substCreated) {
    & subst.exe D: /D 2>$null
  }
}
