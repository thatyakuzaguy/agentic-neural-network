param(
  [string]$InstallRoot = "D:\ANN",
  [string]$ShortcutLocation = ""
)

$ErrorActionPreference = "Stop"
$desktop = Join-Path $InstallRoot "desktop\ANN.exe"
$launcher = Join-Path $InstallRoot "installer\ann_launcher.ps1"
if (-not $ShortcutLocation) {
  $ShortcutLocation = Join-Path ([Environment]::GetFolderPath("Desktop")) "ANN Desktop.lnk"
}
if (-not (Test-Path -LiteralPath $desktop -PathType Leaf) -and -not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
  throw "ANN desktop and fallback launcher are both missing."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutLocation)
if (Test-Path -LiteralPath $desktop -PathType Leaf) {
  $shortcut.TargetPath = $desktop
  $shortcut.Arguments = ""
  $shortcut.IconLocation = "$desktop,0"
} else {
  $shortcut.TargetPath = "powershell.exe"
  $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
  $shortcut.IconLocation = "powershell.exe,0"
}
$shortcut.WorkingDirectory = $InstallRoot
$shortcut.Save()
Write-Host "Shortcut created: $ShortcutLocation"
