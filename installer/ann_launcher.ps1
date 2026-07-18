param([string]$InstallRoot = "D:\ANN")

$ErrorActionPreference = "Stop"
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($InstallRoot -match '^[Cc]:\\') { throw "C:\ launch roots are blocked by default." }
$desktop = Join-Path $InstallRoot "desktop\ANN.exe"
$python = Join-Path $InstallRoot "runtime\python\python.exe"

if (Test-Path -LiteralPath $desktop -PathType Leaf) {
  Start-Process -FilePath $desktop -WorkingDirectory (Split-Path -Parent $desktop)
  exit 0
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Embedded Python not found: $python" }
$env:PYTHONPATH = $InstallRoot
Set-Location $InstallRoot
& $python -m agentic_network.desktop_app.run
