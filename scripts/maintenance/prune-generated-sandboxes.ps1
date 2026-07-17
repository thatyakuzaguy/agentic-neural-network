$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not available on PATH."
}

Write-Host "Stopping/removing generated sandbox compose projects is handled by each lifecycle run."
Write-Host "Removing unused generated sandbox images..."

$ImageRefs = docker image ls --format "{{.Repository}}:{{.Tag}}" |
    Where-Object {
        ($_ -like "aen-*:latest") -or
        ($_ -like "build-me-*:latest")
    }

foreach ($ImageRef in $ImageRefs) {
    Write-Host "Removing $ImageRef"
    docker image rm $ImageRef
}

Write-Host "Removing unused generated sandbox volumes..."
$VolumeNames = docker volume ls --format "{{.Name}}" |
    Where-Object {
        ($_ -like "aen-*") -or
        ($_ -like "build-me-*")
    }

foreach ($VolumeName in $VolumeNames) {
    Write-Host "Removing volume $VolumeName"
    docker volume rm $VolumeName
}

Write-Host "Pruning dangling build cache. This removes cache only, not project source code."
docker builder prune --force --filter "until=24h"

Write-Host "Generated sandbox prune complete."
