[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [switch]$AllowContentDrift
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$manifestPath = Join-Path $RepositoryRoot "PUBLIC_RELEASE_MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Public release manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$declaredPaths = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
$failures = [Collections.Generic.List[string]]::new()
$contentDrift = [Collections.Generic.List[string]]::new()
$actualBytes = [int64]0

foreach ($entry in $manifest.files) {
    $relativePath = ([string]$entry.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
    if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath -split '[\\/]' -contains '..') {
        $failures.Add("unsafe path: $($entry.path)")
        continue
    }
    $candidate = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $relativePath))
    $prefix = $RepositoryRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        $failures.Add("path escaped repository: $($entry.path)")
        continue
    }
    [void]$declaredPaths.Add(([string]$entry.path).Replace('\', '/'))
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        $failures.Add("missing file: $($entry.path)")
        continue
    }
    $file = Get-Item -LiteralPath $candidate
    $actualBytes += $file.Length
    if ($file.Length -ne [int64]$entry.bytes) {
        $contentDrift.Add("size mismatch: $($entry.path)")
    }
    $hash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne [string]$entry.sha256) {
        $contentDrift.Add("hash mismatch: $($entry.path)")
    }
}

if ($declaredPaths.Count -ne [int]$manifest.file_count) {
    $failures.Add("manifest file_count does not match unique entries")
}
if ($actualBytes -ne [int64]$manifest.total_bytes) {
    $contentDrift.Add("manifest total_bytes does not match checked files")
}

$gitRoot = [string](git -C $RepositoryRoot rev-parse --show-toplevel 2>$null)
$useGitInventory = $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitRoot)
if ($useGitInventory) {
    $resolvedGitRoot = [IO.Path]::GetFullPath($gitRoot.Trim())
    $useGitInventory = $resolvedGitRoot.Equals(
        $RepositoryRoot,
        [StringComparison]::OrdinalIgnoreCase
    )
}

if ($useGitInventory) {
    $tracked = @(git -C $RepositoryRoot ls-files)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to enumerate Git-tracked files."
    }
}
else {
    $tracked = @(
        Get-ChildItem -LiteralPath $RepositoryRoot -Recurse -File -Force |
            Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' } |
            ForEach-Object {
                [IO.Path]::GetRelativePath($RepositoryRoot, $_.FullName).Replace('\', '/')
            }
    )
}
foreach ($path in $tracked) {
    if ($path -eq "PUBLIC_RELEASE_MANIFEST.json") {
        continue
    }
    if (-not $declaredPaths.Contains($path.Replace('\', '/'))) {
        $failures.Add("tracked file missing from manifest: $path")
    }
}
if ($tracked.Count -ne ($declaredPaths.Count + 1)) {
    $failures.Add("tracked file count is not manifest entries plus the manifest")
}

if (-not $AllowContentDrift) {
    foreach ($message in $contentDrift) {
        $failures.Add($message)
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    throw "Public release verification failed with $($failures.Count) error(s)."
}

if ($contentDrift.Count -gt 0) {
    foreach ($message in $contentDrift) {
        Write-Warning $message
    }
    Write-Host "Public repository structure verified with $($contentDrift.Count) expected content drift item(s)."
}
else {
    Write-Host "Public release manifest verified strictly: $($manifest.file_count) files, $actualBytes bytes."
}
