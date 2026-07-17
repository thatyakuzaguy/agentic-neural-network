param(
  [Parameter(Mandatory = $true)]
  [string]$BackupFile
)

$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
$BackupFile = [System.IO.Path]::GetFullPath($BackupFile)

if (-not $BackupFile.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Restore files must stay inside $Root"
}
if (-not (Test-Path $BackupFile)) {
  throw "Backup file not found: $BackupFile"
}

$containerPath = "/tmp/restore.dump"
$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "agentic" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "agentic_engineering_network" }

Push-Location $Root
try {
  docker compose cp $BackupFile "postgres:$containerPath"
  docker compose exec -T postgres pg_restore --clean --if-exists -U $postgresUser -d $postgresDb $containerPath
  docker compose exec -T postgres rm -f $containerPath
  Write-Host "Restore completed from: $BackupFile"
}
finally {
  Pop-Location
}
