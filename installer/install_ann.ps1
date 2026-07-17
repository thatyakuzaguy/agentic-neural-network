param(
  [string]$SourceRoot = (Resolve-Path "$PSScriptRoot\..").Path,
  [string]$InstallRoot = "D:\ANN",
  [switch]$SkipShortcut,
  [string]$ShortcutLocation = ""
)

$ErrorActionPreference = "Stop"
$ExcludedNames = @(
  ".git", "models", "training", "outputs", "memory", "knowledge",
  "unsloth_compiled_cache", "__pycache__", ".pytest_cache", ".ruff_cache",
  "node_modules", ".venv-qlora"
)
$IncludeNames = @("agentic_network", "config", "installer", "pyproject.toml", "README.md")

function Write-InstallLog {
  param([string]$Message)
  $log = Join-Path $InstallRoot "install_log.txt"
  Add-Content -Path $log -Value "$(Get-Date -Format o) $Message"
}

function Test-BlockedRoot {
  param([string]$PathValue)
  $full = [System.IO.Path]::GetFullPath($PathValue)
  if ($full -match '^[Cc]:\\') { throw "C:\ install roots are blocked by default." }
  if ($full -eq [System.IO.Path]::GetFullPath($SourceRoot)) { throw "Install root must not equal source root." }
}

Test-BlockedRoot $InstallRoot
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Write-InstallLog "Starting ANN install from $SourceRoot to $InstallRoot"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found on PATH."
}

@'
import importlib.util
if importlib.util.find_spec("PySide6") is None:
    print("WARNING: PySide6 is not importable. ANN Desktop requires PySide6 or a bundled runtime.")
'@ | python -

foreach ($dir in @("app", "data", "projects", "outputs", "logs", "models", "adapters", "config", "runtime")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $dir) | Out-Null
}

$appRoot = Join-Path $InstallRoot "app"
foreach ($name in $IncludeNames) {
  $source = Join-Path $SourceRoot $name
  if (-not (Test-Path $source)) { continue }
  if ($ExcludedNames -contains $name) { continue }
  $target = Join-Path $appRoot $name
  if (Test-Path $source -PathType Container) {
    robocopy $source $target /E /XD $ExcludedNames /XF "*.pyc" | Out-Null
    if ($LASTEXITCODE -le 7) { $global:LASTEXITCODE = 0 } else { throw "robocopy failed for $source" }
  } else {
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
  }
}

Copy-Item -LiteralPath (Join-Path $SourceRoot "config\ann_runtime_engine.json") -Destination (Join-Path $InstallRoot "config\ann_runtime_engine.json") -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath (Join-Path $SourceRoot "config\ann_model_policy.json") -Destination (Join-Path $InstallRoot "config\ann_model_policy.json") -Force -ErrorAction SilentlyContinue

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "ann_launcher.ps1") -Destination (Join-Path $InstallRoot "runtime\ann_launcher.ps1") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "create_shortcut.ps1") -Destination (Join-Path $InstallRoot "runtime\create_shortcut.ps1") -Force

if (-not $SkipShortcut) {
  $shortcutArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "create_shortcut.ps1"),
    "-InstallRoot", $InstallRoot
  )
  if ($ShortcutLocation) {
    $shortcutArgs += @("-ShortcutLocation", $ShortcutLocation)
  }
  & powershell @shortcutArgs
}

$manifest = @{
  installed_at = (Get-Date -Format o)
  source_root = $SourceRoot
  install_root = $InstallRoot
  shortcut_skipped = [bool]$SkipShortcut
  shortcut_location = $ShortcutLocation
  preserved_by_default = @("projects", "models", "outputs", "data")
  excluded = $ExcludedNames
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $InstallRoot "install_manifest.json") -Encoding UTF8
Write-InstallLog "Install complete."
Write-Host "ANN installed to $InstallRoot"
