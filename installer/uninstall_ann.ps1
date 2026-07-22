param(
  [string]$InstallRoot = "D:\ANN",
  [switch]$RemoveProjects,
  [switch]$RemoveModels,
  [switch]$RemoveOutputs
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($root -match '^[Cc]:\\') { throw "C:\ uninstall roots are blocked by default." }
if ($root -notmatch '^[DdEe]:\\' -or $root.Length -lt 6) { throw "Unsafe ANN uninstall root: $root" }

$remove = @(
  "agentic_network", "apps", "packages", "scripts", "config", "desktop",
  "runtime", "adapters", "pyproject.toml", "README.md", "start.ps1", "stop.ps1",
  "install_manifest.json", "install_log.txt"
)
if ($RemoveProjects) { $remove += @("projects", "generated-projects") }
if ($RemoveModels) { $remove += "models" }
if ($RemoveOutputs) {
  $remove += @(
    "outputs", "data", "logs",
    "local_smoke_validation.json", "clean_machine_external_validation.json"
  )
}

foreach ($name in $remove) {
  $target = Join-Path $root $name
  if (-not (Test-Path -LiteralPath $target)) { continue }
  $full = [System.IO.Path]::GetFullPath($target)
  if (-not $full.StartsWith("$root\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove outside install root: $target"
  }
  Remove-Item -LiteralPath $target -Recurse -Force
}

$installerTarget = Join-Path $root "installer"
if (Test-Path -LiteralPath $installerTarget) {
  if ($env:ANN_LAUNCHER_PID -match '^\d+$') {
    $launcherPid = [int]$env:ANN_LAUNCHER_PID
    $escapedInstaller = $installerTarget.Replace("'", "''")
    $escapedRoot = $root.Replace("'", "''")
    $cleanupCommand = @"
Wait-Process -Id $launcherPid -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$escapedInstaller' -Recurse -Force -ErrorAction SilentlyContinue
if ((Test-Path -LiteralPath '$escapedRoot') -and @(Get-ChildItem -LiteralPath '$escapedRoot' -Force).Count -eq 0) {
  Remove-Item -LiteralPath '$escapedRoot' -Force -ErrorAction SilentlyContinue
}
"@
    $encodedCleanup = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cleanupCommand))
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
      -WorkingDirectory (Split-Path -Parent $root) `
      -ArgumentList @("-NoProfile", "-EncodedCommand", $encodedCleanup) | Out-Null
  } else {
    Remove-Item -LiteralPath $installerTarget -Recurse -Force
  }
}
Write-Host "ANN application removed. Projects, models, outputs, data, and logs were preserved unless explicitly selected."
