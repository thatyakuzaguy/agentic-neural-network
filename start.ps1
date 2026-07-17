param(
    [string[]]$Services = @("postgres", "api", "web")
)
$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root
. ".\scripts\setup\use-d-drive-caches.ps1"

if (-not $env:API_DOCKERFILE) {
    $env:API_DOCKERFILE = "docker/api.Dockerfile"
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose up -d @Services
    Write-Host "API: http://localhost:8000/api/health"
    Write-Host "Web: http://localhost:3000"
} else {
    throw "Docker was not found on PATH. Install Docker Desktop with WSL2 support before starting services. Host execution is intentionally blocked."
}
