$ErrorActionPreference = "Stop"

$Root = $env:AEN_HOST_ROOT
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = "D:\AgenticEngineeringNetwork"
}

$CacheRoot = Join-Path $Root "data\tool-caches"
$TempRoot = Join-Path $Root "data\tmp"

$RequiredFolders = @(
    $CacheRoot,
    $TempRoot,
    (Join-Path $CacheRoot "npm"),
    (Join-Path $CacheRoot "pip"),
    (Join-Path $CacheRoot "playwright"),
    (Join-Path $CacheRoot "docker-cli")
)

foreach ($Folder in $RequiredFolders) {
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
}

$env:npm_config_cache = Join-Path $CacheRoot "npm"
$env:NPM_CONFIG_CACHE = $env:npm_config_cache
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $CacheRoot "playwright"
$env:DOCKER_CONFIG = Join-Path $CacheRoot "docker-cli"
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:NEXT_TELEMETRY_DISABLED = "1"

Write-Host "Tool caches redirected to $CacheRoot"
