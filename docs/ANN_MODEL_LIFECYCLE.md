# ANN Model Lifecycle

ANN keeps sequential VRAM policy:

- `active_models <= 1`
- `parallel_llm_loads = 0`
- no parallel POWERFUL execution
- unload before loading the next model

## Conversation Orchestrator Lifecycle

1. Inspect `qwen3_4b_conversation_orchestrator`.
2. If model/backend/policy is missing, record `SKIPPED_MODEL_UNAVAILABLE`.
3. If ready, use the existing loader for load/unload readiness.
4. Never assume unload succeeded without runtime state.

## Policy

The model is registered only for `CONVERSATION_ORCHESTRATOR`.

It does not unlock:

- Qwen3-8B Product Agent
- DeepSeek POWERFUL
- other Qwen3-family models

## Manual Model Setup

Place the GGUF manually at:

`D:/Models/qwen3-4b-instruct-2507-q4_k_m.gguf`

ANN will detect it through inventory validation. ANN will not download it.
