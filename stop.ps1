$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose down
    Write-Host "Docker services stopped."
} else {
    Write-Warning "Docker was not found. Close local API/Web PowerShell windows if fallback mode was used."
}

