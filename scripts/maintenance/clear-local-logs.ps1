$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root
Get-ChildItem ".\logs" -Filter "*.jsonl" -ErrorAction SilentlyContinue | Remove-Item
Write-Host "Local JSONL logs cleared."

