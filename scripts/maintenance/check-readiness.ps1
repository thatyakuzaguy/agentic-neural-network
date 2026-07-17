$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"

Push-Location $Root
try {
  $api = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 5
  $readiness = Invoke-RestMethod -Uri "http://localhost:8000/api/readiness" -TimeoutSec 10
  $compliance = Invoke-RestMethod -Uri "http://localhost:8000/api/compliance" -TimeoutSec 10
  $integrations = Invoke-RestMethod -Uri "http://localhost:8000/api/integrations/status" -TimeoutSec 10

  [PSCustomObject]@{
    ApiStatus = $api.status
    ReadinessSections = $readiness.sections.Count
    ComplianceSections = $compliance.sections.Count
    IntegrationProviders = $integrations.providers.Count
  } | Format-List
}
finally {
  Pop-Location
}
