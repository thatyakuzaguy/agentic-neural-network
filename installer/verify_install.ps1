param(
  [string]$InstallRoot = "D:\ANN",
  [switch]$RequireModels
)

$ErrorActionPreference = "Stop"
$python = Join-Path $InstallRoot "runtime\python\python.exe"
$desktop = Join-Path $InstallRoot "desktop\ANN.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Embedded Python missing: $python" }
if (-not (Test-Path -LiteralPath $desktop -PathType Leaf)) { throw "Desktop executable missing: $desktop" }
$env:PYTHONPATH = $InstallRoot
& $python -c "from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload; from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend"
if ($LASTEXITCODE -ne 0) { throw "ANN model runtime modules are not importable." }
& $python -c "from agentic_network.installer.validation import validate_runtime_requirements; import json; result=validate_runtime_requirements(r'$InstallRoot'); print(json.dumps(result.to_dict(), indent=2)); raise SystemExit(0 if result.status == 'VALID' else 1)"
if ($LASTEXITCODE -ne 0) { throw "ANN runtime validation failed." }

if ($RequireModels) {
  $requiredModels = @(
    "qwen2.5-coder-7b-q4_k_m.gguf",
    "qwen3-4b-instruct-2507-q4_k_m.gguf",
    "Qwen3-8B-Q4_K_M.gguf",
    "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
  )
  foreach ($model in $requiredModels) {
    $modelPath = Join-Path $InstallRoot "models\$model"
    if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
      throw "Required ANN model missing: $modelPath"
    }
  }
  & $python -c "from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths; from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload; configure_windows_runtime_dll_paths(); import llama_cpp; raise SystemExit(0 if llama_cpp_supports_gpu_offload(llama_cpp) is True else 1)"
  if ($LASTEXITCODE -ne 0) { throw "Embedded llama.cpp runtime does not expose GPU offload support." }
  Write-Host "ANN model payload and CUDA llama.cpp runtime: VALID"
}
