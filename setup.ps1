$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"

if (-not (Test-Path -LiteralPath "D:\")) {
    throw "Drive D: does not exist. Create or mount D: before setup."
}

if (-not (Test-Path -LiteralPath $Root)) {
    New-Item -ItemType Directory -Path $Root | Out-Null
}

Set-Location $Root
. ".\scripts\setup\use-d-drive-caches.ps1"

$RequiredFolders = @(
    "apps\web", "apps\api", "packages\agents", "packages\orchestration",
    "packages\sandbox", "packages\git", "packages\logs", "packages\shared",
    "packages\database", "packages\security", "generated-projects", "logs",
    "data\postgres", "data\ollama", "models"
)

foreach ($Folder in $RequiredFolders) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $Folder) | Out-Null
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

if (-not (Test-Path ".git")) {
    git init -b main
}

Write-Host "Verifying host tools..."
git --version
node --version
npm --version
python --version

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker --version
    docker compose build
} else {
    Write-Warning "Docker was not found on PATH. Install Docker Desktop with WSL2 support, then rerun setup.ps1."
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "models\qwen2.5-coder-7b-q4_k_m.gguf"))) {
    Write-Warning "Qwen GGUF model link was not found. Pull qwen2.5-coder:7b with the optional Ollama profile, then run scripts\setup\link-qwen-gguf-from-ollama.ps1."
}

Write-Host "Installing frontend dependencies inside $Root..."
npm install

Write-Host "Creating Python virtual environment inside $Root..."
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"

Write-Host "Setup complete."
