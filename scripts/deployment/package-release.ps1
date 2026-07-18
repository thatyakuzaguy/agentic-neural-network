$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root

$Version = "0.1.3"
$ReleaseRoot = Join-Path $Root "releases"
$PackageName = "ANN-$Version"
$Stage = Join-Path $ReleaseRoot $PackageName
$Out = Join-Path $ReleaseRoot "$PackageName.zip"
$Manifest = Join-Path $ReleaseRoot "$PackageName.manifest.txt"
$Checksum = Join-Path $ReleaseRoot "$PackageName.sha256.txt"

$RequiredFiles = @(
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "README.md",
    "ROADMAP.md",
    "docker-compose.yml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "setup.ps1",
    "start.ps1",
    "stop.ps1",
    "update.ps1"
)

$RequiredFolders = @(
    "apps",
    "docker",
    "docs",
    "generated-projects",
    "logs",
    "packages",
    "scripts",
    "tests"
)

$ExcludedNames = @(
    ".git",
    ".ms-playwright",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "test-results",
    "playwright-report"
)

$ExcludedExtensions = @(".pyc", ".pyo", ".log", ".jsonl")

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
if (Test-Path -LiteralPath $Out) { Remove-Item -LiteralPath $Out -Force }
if (Test-Path -LiteralPath $Manifest) { Remove-Item -LiteralPath $Manifest -Force }
if (Test-Path -LiteralPath $Checksum) { Remove-Item -LiteralPath $Checksum -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

foreach ($File in $RequiredFiles) {
    $Source = Join-Path $Root $File
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required file missing: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $Stage $File) -Force
}

foreach ($Folder in $RequiredFolders) {
    $Source = Join-Path $Root $Folder
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required folder missing: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $Stage $Folder) -Recurse -Force
}

Get-ChildItem -LiteralPath $Stage -Force -Recurse |
    Where-Object {
        ($ExcludedNames -contains $_.Name) -or
        ((-not $_.PSIsContainer) -and ($ExcludedExtensions -contains $_.Extension))
    } |
    Sort-Object FullName -Descending |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }

$Launcher = Join-Path $Stage "AgenticEngineeringNetwork.cmd"
Set-Content -LiteralPath $Launcher -Encoding ASCII -Value @(
    "@echo off",
    "setlocal",
    "cd /d %~dp0",
    "if exist ""apps\desktop\dist\ANN-win32-x64\ANN.exe"" (",
    "  start """" ""apps\desktop\dist\ANN-win32-x64\ANN.exe""",
    ") else (",
    "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File start.ps1",
    ")",
    "pause"
)

$PackageReadme = Join-Path $Stage "PACKAGE_README.md"
Set-Content -LiteralPath $PackageReadme -Encoding UTF8 -Value @(
    "# ANN (Agentic Neural Network) Package",
    "",
    "Version: $Version",
    "",
    "This package contains the application source, Docker environment, tests, scripts, and documentation.",
    "",
    "It intentionally excludes:",
    "",
    "- .env",
    "- node_modules",
    "- .venv",
    "- generated logs",
    "- PostgreSQL data",
    "- Ollama data",
    "- GGUF model files",
    "",
    "Expected local model path after setup:",
    "",
    "D:\AgenticEngineeringNetwork\models\qwen2.5-coder-7b-q4_k_m.gguf",
    "",
    "Start with:",
    "",
    "apps\desktop\dist\ANN-win32-x64\ANN.exe",
    "",
    "Or use:",
    "",
    ".\start.ps1",
    "",
    "Or double-click:",
    "",
    "AgenticEngineeringNetwork.cmd"
)

$Files = Get-ChildItem -LiteralPath $Stage -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        $_.FullName.Substring($Stage.Length + 1)
    }
$Files | Set-Content -LiteralPath $Manifest -Encoding UTF8

Compress-Archive -LiteralPath $Stage -DestinationPath $Out -CompressionLevel Optimal
$Hash = Get-FileHash -LiteralPath $Out -Algorithm SHA256
"$($Hash.Hash)  $([System.IO.Path]::GetFileName($Out))" | Set-Content -LiteralPath $Checksum -Encoding ASCII

Write-Host "Deployment package: $Out"
Write-Host "Manifest: $Manifest"
Write-Host "SHA256: $Checksum"
