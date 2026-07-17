$ErrorActionPreference = "Stop"
$checks = "git", "node", "npm", "python", "docker"
foreach ($check in $checks) {
    $cmd = Get-Command $check -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "$check: $($cmd.Source)"
    } else {
        Write-Warning "$check was not found on PATH"
    }
}

