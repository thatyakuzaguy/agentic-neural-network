$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "agentic" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "agentic_engineering_network" }

Push-Location $Root
try {
  Get-ChildItem ".\packages\database\agentic_engineering_network\database\migrations" -Filter "*.sql" |
    Sort-Object Name |
    ForEach-Object {
      Write-Host "Applying migration $($_.Name)"
      Get-Content $_.FullName -Raw | docker compose exec -T postgres psql -U $postgresUser -d $postgresDb
    }
}
finally {
  Pop-Location
}
