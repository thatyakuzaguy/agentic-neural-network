$ErrorActionPreference = "Stop"
$Root = "D:\AgenticEngineeringNetwork"
Set-Location $Root

Write-Host "Host NVIDIA status:"
nvidia-smi

Write-Host "Docker NVIDIA status:"
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi

Write-Host "API CUDA Python package check:"
$Code = @"
from app.core.settings import settings
from agentic_engineering_network.shared.providers import build_provider
provider = build_provider(settings)
print(type(provider).__name__)
print("gpu_layers", settings.local_model_gpu_layers)
print("main_gpu", settings.local_model_main_gpu)
"@
docker compose exec api python3 -c $Code
