$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
$BlobDir = Join-Path $Root "data\ollama\models\blobs"
$ModelDir = Join-Path $Root "models"
$Target = Join-Path $ModelDir "qwen2.5-coder-7b-q4_k_m.gguf"

Set-Location $Root
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

if (-not (Test-Path -LiteralPath $BlobDir)) {
    throw "Ollama blob directory not found: $BlobDir"
}

$Blob = Get-ChildItem -Path $BlobDir -File |
    Sort-Object Length -Descending |
    Select-Object -First 1

if (-not $Blob) {
    throw "No Ollama model blobs found. Pull qwen2.5-coder:7b first."
}

$Buffer = New-Object byte[] 4
$Stream = [System.IO.File]::OpenRead($Blob.FullName)
try {
    [void]$Stream.Read($Buffer, 0, 4)
} finally {
    $Stream.Dispose()
}

$Header = [System.Text.Encoding]::ASCII.GetString($Buffer)
if ($Header -ne "GGUF") {
    throw "Largest Ollama blob is not a GGUF file: $($Blob.FullName)"
}

if (Test-Path -LiteralPath $Target) {
    Write-Host "Model link already exists: $Target"
} else {
    New-Item -ItemType HardLink -Path $Target -Target $Blob.FullName | Out-Null
    Write-Host "Created hard link: $Target"
}

Get-Item -LiteralPath $Target | Select-Object FullName, Length, LinkType

