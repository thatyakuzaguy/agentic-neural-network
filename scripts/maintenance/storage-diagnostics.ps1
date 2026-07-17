$ErrorActionPreference = "Stop"

$Root = "D:\AgenticEngineeringNetwork"

function Get-FolderSizeGb {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $Bytes = (Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum

    [pscustomobject]@{
        Path = $Path
        GB = [math]::Round(($Bytes / 1GB), 2)
    }
}

Write-Host "Volumes"
Get-Volume -DriveLetter C, D, E | Select-Object DriveLetter, FileSystemLabel, SizeRemaining, Size | Format-Table -AutoSize

Write-Host "`nLikely cache and runtime folders"
$Paths = @(
    "$env:USERPROFILE\AppData\Local\Docker",
    "$env:USERPROFILE\AppData\Local\Temp",
    "$env:USERPROFILE\AppData\Local\npm-cache",
    "$env:USERPROFILE\AppData\Roaming\npm-cache",
    "$env:USERPROFILE\AppData\Local\pip\Cache",
    "$env:USERPROFILE\.cache",
    "$env:USERPROFILE\.docker",
    "$env:USERPROFILE\.ollama",
    "$env:USERPROFILE\AppData\Local\ms-playwright",
    "$env:USERPROFILE\Documents\Codex",
    "$Root\data",
    "$Root\data\tool-caches",
    "$Root\data\tmp",
    "$Root\tests\.tmp",
    "$Root\generated-projects"
)

$Results = foreach ($Path in $Paths) {
    Get-FolderSizeGb -Path $Path
}
$Results | Where-Object { $null -ne $_ } | Sort-Object GB -Descending | Format-Table -AutoSize

Write-Host "`nDocker Desktop WSL disks"
Get-ChildItem "$env:USERPROFILE\AppData\Local\Docker" -Recurse -Force -ErrorAction SilentlyContinue -Include *.vhdx |
    Select-Object FullName, @{Name = "GB"; Expression = { [math]::Round($_.Length / 1GB, 2) } } |
    Sort-Object GB -Descending |
    Format-Table -AutoSize

Write-Host "`nDocker system df"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker system df
} else {
    Write-Warning "Docker is not available on PATH."
}

Write-Host "`nNotes"
Write-Host "- If docker_data.vhdx is on C:, Docker builds can fill C: even when projects are stored on D:."
Write-Host "- Move Docker Desktop disk image location to D:\AgenticEngineeringNetwork\data\docker-desktop from Docker Desktop Settings > Resources > Advanced."
Write-Host "- To reclaim Docker build cache manually, run: docker builder prune"
