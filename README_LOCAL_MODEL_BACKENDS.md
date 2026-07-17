# ANN Local Model Backends

ANN keeps model execution local and safe by default. It does not install model
backends, download model files, compile native libraries, or enable real model
loading automatically.

## Current Backend Status

The first controlled Qwen2.5 smoke in v13.1 reached the gate, but the backend
reported `llama_cpp_binding_unavailable`. That means ANN could not import the
local `llama_cpp` binding, so no real GGUF load or inference was performed.

ANN continues to run in mock/safe mode when this happens.

## llama_cpp Readiness

Artifact `110_llama_cpp_backend_readiness.json` reports:

- Whether `llama_cpp` is importable.
- Binding version if available.
- CUDA/cuBLAS/GPU support when detectable without loading a model.
- Qwen2.5 GGUF path, file size, and basic read access.
- Whether the path is blocked or unsafe.
- Whether a controlled load can be attempted.

ANN does not run `pip install`, compile CUDA libraries, or download wheels.
Verify `llama_cpp` manually outside ANN before retrying the smoke.

## Controlled Qwen2.5 Retry

Artifact `112_qwen25_retry_smoke.json` reports the controlled retry status.

The retry:

- Only targets `qwen2_5_coder_7b_v5`.
- Requires token and explicit confirmation.
- Uses FAST mode only.
- Does not touch Qwen3.
- Does not touch DeepSeek14B.
- Does not activate POWERFUL.
- Requires one-model-at-a-time execution.
- Unloads and returns to safe/mock mode after the smoke.

The smoke prompt is:

```text
Return exactly: ANN_QWEN25_SMOKE_OK
```

ANN must not claim success unless real inference returns that exact text.

## Runtime Memory Probe

Artifact `114_runtime_memory_probe.json` reports:

- Torch availability.
- CUDA availability.
- GPU name when available.
- VRAM total/allocated/reserved when available.
- CPU RAM when detectable.

It does not load models, reserve VRAM, or run a benchmark.

## Qwen3 Preparation

Artifact `116_qwen3_activation_preparation.json` is read-only. It checks:

- `D:/Models/qwen3`
- tokenizer/model files
- `training/adapters/qwen3-8b-product-agent-v9-repaired-v2-bullets`
- `qwen_local` backend availability
- policy blocking real load
- risks for RTX 3060 Ti 8GB

Qwen3 is not activated in v13.2-v13.4.

## DeepSeek14B

DeepSeek-R1-Distill-Qwen-14B remains POWERFUL and blocked. It is not touched by
the Qwen2.5 retry or Qwen3 preparation phases.

## Sequential Policy

ANN preserves:

- `active_models <= 1`
- `max_loaded_models = 1`
- `parallel_llm_loads = 0`
- `vram_policy = SEQUENTIAL`

## Artifacts 110-117

- `110_llama_cpp_backend_readiness.json`
- `111_llama_cpp_backend_readiness.md`
- `112_qwen25_retry_smoke.json`
- `113_qwen25_retry_smoke.md`
- `114_runtime_memory_probe.json`
- `115_runtime_memory_probe.md`
- `116_qwen3_activation_preparation.json`
- `117_qwen3_activation_preparation.md`

