param(
  [string]$InstallRoot = "D:\ANN"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = if (Test-Path (Join-Path $InstallRoot "app")) { Join-Path $InstallRoot "app" } else { (Resolve-Path "$PSScriptRoot\..").Path }
@"
from agentic_network.installer.validation import validate_runtime_requirements
import json
result = validate_runtime_requirements(r"$InstallRoot")
print(json.dumps(result.to_dict(), indent=2))
"@ | python -
