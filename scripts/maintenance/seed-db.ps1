$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "agentic" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "agentic_engineering_network" }

Push-Location $Root
try {
  Get-Content ".\packages\database\agentic_engineering_network\database\seed.sql" -Raw |
    docker compose exec -T postgres psql -U $postgresUser -d $postgresDb
  Write-Host "Seed data applied."
}
finally {
  Pop-Location
}
