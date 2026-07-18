param(
  [string]$OutputDirectory = "D:\AgenticEngineeringNetwork\backups"
)

$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

if (-not $OutputDirectory.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Backups must stay inside $Root"
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$fileName = "ann-$timestamp.dump"
$containerPath = "/tmp/$fileName"
$hostPath = Join-Path $OutputDirectory $fileName
$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "agentic" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "agentic_engineering_network" }

Push-Location $Root
try {
  docker compose exec -T postgres pg_dump -U $postgresUser -d $postgresDb -Fc -f $containerPath
  docker compose cp "postgres:$containerPath" $hostPath
  docker compose exec -T postgres rm -f $containerPath
  Write-Host "Backup created: $hostPath"
}
finally {
  Pop-Location
}
