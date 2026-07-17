param(
  [string]$InstallRoot = "D:\ANN",
  [switch]$RemoveProjects,
  [switch]$RemoveModels,
  [switch]$RemoveOutputs
)

$ErrorActionPreference = "Stop"

function Test-BlockedRoot {
  param([string]$PathValue)
  $full = [System.IO.Path]::GetFullPath($PathValue)
  if ($full -match '^[Cc]:\\') { throw "C:\ uninstall roots are blocked by default." }
  if ($full.Length -lt 6) { throw "Refusing to uninstall from a shallow path." }
}

function Write-UninstallLog {
  param([string]$Message)
  $log = Join-Path $InstallRoot "uninstall_log.txt"
  New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
  Add-Content -Path $log -Value "$(Get-Date -Format o) $Message"
}

Test-BlockedRoot $InstallRoot
Write-UninstallLog "Starting ANN uninstall at $InstallRoot"

$remove = @("app", "runtime", "config", "logs", "adapters", "ANN Desktop.lnk.cmd", "install_manifest.json", "install_log.txt")
if ($RemoveProjects) { $remove += "projects" }
if ($RemoveModels) { $remove += "models" }
if ($RemoveOutputs) { $remove += "outputs"; $remove += "data" }

foreach ($name in $remove) {
  $target = Join-Path $InstallRoot $name
  if (-not (Test-Path $target)) { continue }
  $full = [System.IO.Path]::GetFullPath($target)
  $rootFull = [System.IO.Path]::GetFullPath($InstallRoot)
  if (-not $full.StartsWith($rootFull)) { throw "Refusing to remove outside install root: $target" }
  Remove-Item -LiteralPath $target -Recurse -Force
  Write-UninstallLog "Removed $target"
}

Write-UninstallLog "Uninstall complete. Preserved projects/models/outputs unless removal flags were supplied."
Write-Host "ANN uninstall complete."

