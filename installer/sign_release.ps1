param(
  [string]$InstallerRoot = "",
  [string]$SigntoolPath = "",
  [string]$CertificateThumbprint = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com",
  [string]$OutputPath = "",
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

if (-not $InstallerRoot) {
  $InstallerRoot = $PSScriptRoot
}

$root = [System.IO.Path]::GetFullPath($InstallerRoot)
$setup = Join-Path $root "ANN_Setup.exe"
$uninstall = Join-Path $root "ANN_Uninstall.exe"
if (-not $OutputPath) {
  $OutputPath = Join-Path $root "release_signing_evidence.json"
}

if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
  throw "Missing installer binary: $setup"
}
if (-not (Test-Path -LiteralPath $uninstall -PathType Leaf)) {
  throw "Missing uninstaller binary: $uninstall"
}
if (-not $CertificateThumbprint) {
  throw "CertificateThumbprint is required. Use a trusted code-signing certificate; do not self-sign release builds."
}
$NormalizedCertificateThumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()
if (($NormalizedCertificateThumbprint -eq "<CERT_THUMBPRINT>") -or ($NormalizedCertificateThumbprint -eq "CERT_THUMBPRINT")) {
  throw "CertificateThumbprint placeholder is not allowed. Provide the real trusted Authenticode certificate SHA1 thumbprint."
}
if ($NormalizedCertificateThumbprint -notmatch '^[0-9A-F]{40}$') {
  throw "CertificateThumbprint must be the real 40-character hexadecimal SHA1 thumbprint used by signtool /sha1."
}
if (-not $TimestampUrl) {
  throw "TimestampUrl is required. Use a trusted RFC3161 timestamp authority for final release builds."
}
if (-not $SigntoolPath) {
  $signtoolCommand = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
  if (-not $signtoolCommand) {
    $SigntoolPath = "signtool.exe"
    $signtoolMissing = $true
  } else {
    $SigntoolPath = $signtoolCommand.Source
    $signtoolMissing = $false
  }
} else {
  $signtoolMissing = -not (Test-Path -LiteralPath $SigntoolPath -PathType Leaf)
}
if ($Execute -and $signtoolMissing) {
  throw "signtool.exe was not found. Install Windows SDK signing tools on the release machine."
}
if ($Execute -and -not (Test-Path -LiteralPath $SigntoolPath -PathType Leaf)) {
  throw "SigntoolPath does not exist: $SigntoolPath"
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

function Get-SignatureEvidence {
  param([string]$PathValue)
  if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
    return [pscustomobject]@{ path = $PathValue; status = "MISSING"; signer = ""; signer_thumbprint_sha256 = ""; timestamp_signer = ""; sha256 = "" }
  }
  try {
    $sig = Get-AuthenticodeSignature -FilePath $PathValue
    $signerThumbprint = if ($sig.SignerCertificate) { [string]$sig.SignerCertificate.Thumbprint } else { "" }
    return [pscustomobject]@{
      path = $PathValue
      status = [string]$sig.Status
      signer = if ($sig.SignerCertificate) { [string]$sig.SignerCertificate.Subject } else { "" }
      signer_thumbprint_sha256 = if ($signerThumbprint) { Get-StringSha256 $signerThumbprint.Replace(" ", "").ToUpperInvariant() } else { "" }
      timestamp_signer = if ($sig.TimeStamperCertificate) { [string]$sig.TimeStamperCertificate.Subject } else { "" }
      sha256 = Get-FileSha256 $PathValue
    }
  } catch {
    return [pscustomobject]@{
      path = $PathValue
      status = "UNKNOWN"
      signer = ""
      signer_thumbprint_sha256 = ""
      timestamp_signer = ""
      sha256 = Get-FileSha256 $PathValue
      error = $_.Exception.Message
    }
  }
}

function Get-RedactedThumbprint {
  param([string]$Thumbprint)
  $normalized = $Thumbprint.Replace(" ", "").ToUpperInvariant()
  if ($normalized.Length -le 8) {
    return "***"
  }
  return "$($normalized.Substring(0, 4))...$($normalized.Substring($normalized.Length - 4))"
}

function Get-CodeSigningCertificateEvidence {
  param([string]$Thumbprint)
  $normalized = $Thumbprint.Replace(" ", "").ToUpperInvariant()
  $stores = @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")
  $matches = @()
  foreach ($store in $stores) {
    $certs = @(Get-ChildItem $store -ErrorAction SilentlyContinue | Where-Object {
      $_.Thumbprint.Replace(" ", "").ToUpperInvariant() -eq $normalized
    })
    foreach ($cert in $certs) {
      $matches += [pscustomobject]@{ store = $store; certificate = $cert }
    }
  }
  if ($matches.Count -eq 0) {
    return [pscustomobject]@{
      found = $false
      thumbprint = Get-RedactedThumbprint $Thumbprint
      thumbprint_sha256 = Get-StringSha256 $normalized
      store = ""
      subject = ""
      issuer = ""
      has_private_key = $false
      not_self_signed = $false
      not_expired = $false
      code_signing_eku = $false
      enhanced_key_usage = @()
      enhanced_key_usage_oids = @()
      detail = "certificate_not_found"
    }
  }
  $selected = $matches[0]
  $cert = $selected.certificate
  $ekuNames = @($cert.EnhancedKeyUsageList | ForEach-Object { $_.FriendlyName })
  $ekuOids = @($cert.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value })
  $notSelfSigned = ([string]$cert.Subject) -ne ([string]$cert.Issuer)
  $notExpired = $cert.NotAfter.ToUniversalTime() -gt (Get-Date).ToUniversalTime()
  $codeSigning = ($ekuNames -contains "Code Signing") -or ($ekuOids -contains "1.3.6.1.5.5.7.3.3")
  return [pscustomobject]@{
    found = $true
    thumbprint = Get-RedactedThumbprint $Thumbprint
    thumbprint_sha256 = Get-StringSha256 $normalized
    store = [string]$selected.store
    subject = [string]$cert.Subject
    issuer = [string]$cert.Issuer
    has_private_key = [bool]$cert.HasPrivateKey
    not_self_signed = [bool]$notSelfSigned
    not_expired = [bool]$notExpired
    code_signing_eku = [bool]$codeSigning
    enhanced_key_usage = $ekuNames
    enhanced_key_usage_oids = $ekuOids
    detail = "certificate_found"
  }
}

function Assert-CodeSigningCertificateReady {
  param([object]$CertificateEvidence)
  if (-not $CertificateEvidence.found) {
    throw "Code-signing certificate was not found for the provided thumbprint."
  }
  if (-not $CertificateEvidence.not_self_signed) {
    throw "Release signing refuses self-signed certificates."
  }
  if (-not $CertificateEvidence.not_expired) {
    throw "Release signing refuses expired certificates."
  }
  if (-not $CertificateEvidence.has_private_key) {
    throw "Release signing requires the certificate private key."
  }
  if (-not $CertificateEvidence.code_signing_eku) {
    throw "Release signing requires Code Signing Enhanced Key Usage."
  }
}

function Assert-SignatureMatchesCertificate {
  param([string]$PathValue, [string]$ExpectedThumbprintSha256)
  $evidence = Get-SignatureEvidence $PathValue
  if ($evidence.status -ne "Valid") {
    throw "Signature validation failed for $PathValue with status $($evidence.status)"
  }
  if (-not $evidence.signer_thumbprint_sha256) {
    throw "Signature thumbprint evidence missing for $PathValue."
  }
  if ($evidence.signer_thumbprint_sha256 -ne $ExpectedThumbprintSha256) {
    throw "Signature thumbprint validation failed for $PathValue."
  }
}

$targets = @($setup, $uninstall)
$preSignEvidence = @($targets | ForEach-Object { Get-SignatureEvidence $_ })
$certificateEvidence = Get-CodeSigningCertificateEvidence $NormalizedCertificateThumbprint
$planned = @()
foreach ($target in $targets) {
  $planned += [pscustomobject]@{
    target = $target
    command = @(
      $SigntoolPath,
      "sign",
      "/sha1",
      $NormalizedCertificateThumbprint,
      "/fd",
      "SHA256",
      "/tr",
      $TimestampUrl,
      "/td",
      "SHA256",
      $target
    )
  }
}

$payload = [pscustomobject]@{
  version = "19.5"
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  installer_root = $root
  execute = [bool]$Execute
  signtool_path = $SigntoolPath
  signtool_missing = [bool]$signtoolMissing
  timestamp_url = $TimestampUrl
  output_path = [System.IO.Path]::GetFullPath($OutputPath)
  certificate_evidence = $certificateEvidence
  certificate_preflight_required_for_execute = $true
  targets = $targets
  pre_sign_evidence = $preSignEvidence
  target_evidence = @($targets | ForEach-Object { Get-SignatureEvidence $_ })
  planned_commands = $planned
  no_download = $true
  no_install = $true
  no_shell = $true
  no_self_signed_certificate = $true
}

if (-not $Execute) {
  New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath -Parent) | Out-Null
  $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8
  $payload | ConvertTo-Json -Depth 6
  Write-Host "Dry run only. Re-run with -Execute on the release signing machine to sign binaries."
  Write-Host "Signing evidence written: $OutputPath"
  exit 0
}

Assert-CodeSigningCertificateReady $certificateEvidence

foreach ($entry in $planned) {
  $command = [string[]]$entry.command
  & $command[0] $command[1..($command.Count - 1)]
  if ($LASTEXITCODE -ne 0) {
    throw "signtool failed for $($entry.target) with exit code $LASTEXITCODE"
  }
}

foreach ($target in $targets) {
  Assert-SignatureMatchesCertificate $target $certificateEvidence.thumbprint_sha256
}

$payload = [pscustomobject]@{
  version = $payload.version
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  installer_root = $root
  execute = [bool]$Execute
  signtool_path = $SigntoolPath
  signtool_missing = [bool]$signtoolMissing
  timestamp_url = $TimestampUrl
  output_path = [System.IO.Path]::GetFullPath($OutputPath)
  certificate_evidence = $certificateEvidence
  certificate_preflight_required_for_execute = $true
  targets = $targets
  pre_sign_evidence = $preSignEvidence
  target_evidence = @($targets | ForEach-Object { Get-SignatureEvidence $_ })
  planned_commands = $planned
  no_download = $true
  no_install = $true
  no_shell = $true
  no_self_signed_certificate = $true
}
New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath -Parent) | Out-Null
$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8
$payload | ConvertTo-Json -Depth 8
Write-Host "Signing evidence written: $OutputPath"
