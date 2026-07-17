param(
  [string]$InstallRoot = "D:\ANN"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$repoDesktopEntry = Join-Path $repoRoot "agentic_network\desktop_app\run.py"
if (Test-Path $repoDesktopEntry) {
  $appRoot = $repoRoot
} else {
  $appRoot = Join-Path $InstallRoot "app"
}
$env:PYTHONPATH = $appRoot
Set-Location $appRoot
python -m agentic_network.desktop_app.run
