param(
  [string]$InstallRoot = "D:\ANN",
  [string]$ShortcutLocation = ""
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $InstallRoot "runtime\ann_launcher.ps1"
if (-not $ShortcutLocation) {
  $ShortcutLocation = Join-Path ([Environment]::GetFolderPath("Desktop")) "ANN Desktop.lnk"
}

if (-not (Test-Path $launcher)) {
  throw "ANN launcher not found: $launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutLocation)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$launcher`""
$shortcut.WorkingDirectory = $InstallRoot
$shortcut.IconLocation = "powershell.exe,0"
$shortcut.Save()
Write-Host "Shortcut created: $ShortcutLocation"

