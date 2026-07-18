[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$Destination,
    [switch]$KeepExisting
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$ReleaseRoot = [IO.Path]::GetFullPath((Join-Path $SourceRoot "releases\github-public"))
$configPath = Join-Path $SourceRoot "config\public-release.json"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $ReleaseRoot ([string]$config.repository_name)
}
$Destination = [IO.Path]::GetFullPath($Destination)

$prefix = $ReleaseRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $Destination.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Public repository destination must stay inside $ReleaseRoot"
}
if ($Destination -eq $SourceRoot) {
    throw "Public repository destination cannot be the development repository."
}

$maxBytes = [int64]$config.maximum_file_size_mb * 1MB

$excludedSegments = @(
    ".git", ".next", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".tmp", ".venv", ".venv-qlora", "__pycache__", "node_modules",
    "dist", "build", "playwright-report", "test-results"
)
$excludedExtensions = @(
    ".7z", ".bin", ".dll", ".exe", ".gguf", ".gz", ".log", ".onnx",
    ".p12", ".pfx", ".pt", ".pth", ".pyc", ".pyd", ".safetensors",
    ".tar", ".tmp", ".tsbuildinfo", ".zip"
)
$excludedNames = @(".env", ".DS_Store", "Thumbs.db")

if (Test-Path -LiteralPath $Destination) {
    if ($KeepExisting) {
        throw "Destination already exists and -KeepExisting was supplied: $Destination"
    }
    $resolvedExisting = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Destination).Path)
    if (-not $resolvedExisting.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a destination outside the public release root."
    }
    Remove-Item -LiteralPath $resolvedExisting -Recurse -Force
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null

function Test-PublicPath {
    param([string]$RelativePath)

    if ($RelativePath.Replace('\', '/') -eq "docs/public/README.md") {
        return $false
    }
    $segments = $RelativePath -split '[\\/]'
    foreach ($segment in $segments) {
        if ($excludedSegments -contains $segment) {
            return $false
        }
    }
    $name = [IO.Path]::GetFileName($RelativePath)
    if ($excludedNames -contains $name) {
        return $false
    }
    if ($name -like "*.bak" -or $name -like "*.backup*") {
        return $false
    }
    $extension = [IO.Path]::GetExtension($RelativePath).ToLowerInvariant()
    return -not ($excludedExtensions -contains $extension)
}

function Copy-PublicFile {
    param(
        [Parameter(Mandatory = $true)][IO.FileInfo]$File,
        [string]$DestinationRelativePath
    )

    $sourcePath = [IO.Path]::GetFullPath($File.FullName)
    $sourcePrefix = $SourceRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $sourcePath.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source escaped repository root: $sourcePath"
    }
    $relativePath = $sourcePath.Substring($sourcePrefix.Length)
    if (-not (Test-PublicPath $relativePath)) {
        return
    }
    if ($File.Length -gt $maxBytes) {
        throw "File exceeds public size limit ($($config.maximum_file_size_mb) MiB): $relativePath"
    }
    if ([string]::IsNullOrWhiteSpace($DestinationRelativePath)) {
        $DestinationRelativePath = $relativePath
    }
    $targetPath = Join-Path $Destination $DestinationRelativePath
    $targetDirectory = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
}

foreach ($directory in $config.source_directories) {
    $sourceDirectory = Join-Path $SourceRoot ([string]$directory)
    if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
        throw "Allowlisted source directory is missing: $directory"
    }
    Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse -Force | ForEach-Object {
        Copy-PublicFile -File $_
    }
}

foreach ($relativeFile in $config.source_files) {
    $sourceFile = Join-Path $SourceRoot ([string]$relativeFile)
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Allowlisted source file is missing: $relativeFile"
    }
    Copy-PublicFile -File (Get-Item -LiteralPath $sourceFile)
}

# Public exports use a portable, inference-disabled config and a concise README.
Copy-Item -LiteralPath (Join-Path $SourceRoot "config\ann_terminal_conversation_runtime.example.json") `
    -Destination (Join-Path $Destination "config\ann_terminal_conversation_runtime.json") -Force
Copy-Item -LiteralPath (Join-Path $SourceRoot "docs\public\README.md") `
    -Destination (Join-Path $Destination "README.md") -Force

# The release manifest hashes exact exported bytes. Disabling checkout-time EOL
# conversion keeps those hashes stable on Windows, Linux, and WSL clones.
$attributes = @"
# Public release checkouts use canonical LF endings on every platform.
* text=auto eol=lf
"@
[IO.File]::WriteAllText(
    (Join-Path $Destination ".gitattributes"),
    $attributes.Replace("`r`n", "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)

$blockedIdentityPatterns = @()
if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    $blockedIdentityPatterns += [regex]::Escape($env:USERPROFILE)
}
if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
    $blockedIdentityPatterns += [regex]::Escape("/home/$($env:USERNAME)")
}
$gitEmail = (git -C $SourceRoot config user.email 2>$null)
if (-not [string]::IsNullOrWhiteSpace($gitEmail)) {
    $blockedIdentityPatterns += [regex]::Escape($gitEmail.Trim())
}
$privateKeyMarkers = @("RSA ", "EC ", "OPENSSH ", "") | ForEach-Object {
    "-----BEGIN $($_)PRIVATE KEY-----"
}
$textExtensions = @(
    ".bat", ".cfg", ".cff", ".cs", ".css", ".dockerfile", ".example", ".html",
    ".ini", ".js", ".json", ".jsonl", ".md", ".mjs", ".ps1", ".py",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml"
)
foreach ($file in Get-ChildItem -LiteralPath $Destination -File -Recurse -Force) {
    if ($textExtensions -notcontains $file.Extension.ToLowerInvariant() -and
        $file.Name -notin @("Dockerfile", ".env.example", ".gitignore", ".dockerignore")) {
        continue
    }
    $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
    foreach ($pattern in $blockedIdentityPatterns) {
        if ($content -match $pattern) {
            throw "Machine-specific identity found in public export: $($file.FullName)"
        }
    }
    foreach ($marker in $privateKeyMarkers) {
        if ($content.Contains($marker)) {
            throw "Private key material found in public export: $($file.FullName)"
        }
    }
}

$exclusionDocument = @"
# Public Release Exclusions

This source export intentionally excludes local or sensitive runtime material:

- model weights and quantized model files;
- private adapters and training datasets;
- `.env`, credentials, signing certificates, and approval state;
- memory, knowledge, conversations, logs, outputs, and generated projects;
- databases, tool caches, virtual environments, dependencies, and build output;
- packaged executables and historical release archives.

These exclusions keep the Git history reviewable and prevent machine-local data
from being mistaken for distributable source. Users supply models and secrets
locally after cloning.
"@
Set-Content -LiteralPath (Join-Path $Destination "PUBLIC_RELEASE_EXCLUSIONS.md") `
    -Value $exclusionDocument -Encoding UTF8

# Normalize exported text before hashing so a fresh Windows clone verifies the
# same bytes as Linux and WSL. Binary assets are never decoded or rewritten.
$textNames = @(
    "Dockerfile", "LICENSE", ".dockerignore", ".env.example",
    ".gitattributes", ".gitignore", ".gitleaks.toml"
)
$utf8NoBom = [Text.UTF8Encoding]::new($false)
foreach ($file in Get-ChildItem -LiteralPath $Destination -File -Recurse -Force) {
    $extension = $file.Extension.ToLowerInvariant()
    if ($textExtensions -notcontains $extension -and $textNames -notcontains $file.Name) {
        continue
    }
    $content = [IO.File]::ReadAllText($file.FullName)
    $normalized = $content.Replace("`r`n", "`n").Replace("`r", "`n")
    [IO.File]::WriteAllText($file.FullName, $normalized, $utf8NoBom)
}

$manifestFiles = @(
    Get-ChildItem -LiteralPath $Destination -File -Recurse -Force |
        Where-Object { $_.Name -ne "PUBLIC_RELEASE_MANIFEST.json" } |
        Sort-Object FullName
)
$entries = foreach ($file in $manifestFiles) {
    [ordered]@{
        path = $file.FullName.Substring($Destination.Length + 1).Replace('\', '/')
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    release_stage = [string]$config.release_stage
    source_revision = (git -C $SourceRoot rev-parse HEAD).Trim()
    file_count = $manifestFiles.Count
    total_bytes = [int64](($manifestFiles | Measure-Object Length -Sum).Sum)
    maximum_file_size_mb = [int]$config.maximum_file_size_mb
    files = $entries
}
$manifestLines = [Collections.Generic.List[string]]::new()
$manifestLines.Add("{")
$manifestLines.Add("  `"schema_version`": $($manifest.schema_version),")
$manifestLines.Add("  `"generated_at_utc`": $(ConvertTo-Json -InputObject $manifest.generated_at_utc -Compress),")
$manifestLines.Add("  `"release_stage`": $(ConvertTo-Json -InputObject $manifest.release_stage -Compress),")
$manifestLines.Add("  `"source_revision`": $(ConvertTo-Json -InputObject $manifest.source_revision -Compress),")
$manifestLines.Add("  `"file_count`": $($manifest.file_count),")
$manifestLines.Add("  `"total_bytes`": $($manifest.total_bytes),")
$manifestLines.Add("  `"maximum_file_size_mb`": $($manifest.maximum_file_size_mb),")
$manifestLines.Add("  `"files`": [")
for ($index = 0; $index -lt $entries.Count; $index++) {
    $entry = $entries[$index]
    $suffix = if ($index -lt ($entries.Count - 1)) { "," } else { "" }
    $manifestLines.Add("    {")
    $manifestLines.Add("      `"path`": $(ConvertTo-Json -InputObject $entry.path -Compress),")
    $manifestLines.Add("      `"bytes`": $($entry.bytes),")
    $manifestLines.Add("      `"sha256`": $(ConvertTo-Json -InputObject $entry.sha256 -Compress)")
    $manifestLines.Add("    }$suffix")
}
$manifestLines.Add("  ]")
$manifestLines.Add("}")
$manifestJson = $manifestLines -join "`n"
[IO.File]::WriteAllText(
    (Join-Path $Destination "PUBLIC_RELEASE_MANIFEST.json"),
    $manifestJson + "`n",
    $utf8NoBom
)

Write-Host "ANN public repository exported successfully."
Write-Host "Destination: $Destination"
Write-Host "Files: $($manifest.file_count)"
Write-Host "Size: $([math]::Round($manifest.total_bytes / 1MB, 2)) MiB"
