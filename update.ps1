$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root
. ".\scripts\setup\use-d-drive-caches.ps1"

git pull --ff-only
npm install

if (Test-Path ".\.venv\Scripts\python.exe") {
    & ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose build
    docker compose up -d postgres api web
} else {
    Write-Warning "Docker was not found. Skipped container rebuild."
}

Write-Host "Update complete."
