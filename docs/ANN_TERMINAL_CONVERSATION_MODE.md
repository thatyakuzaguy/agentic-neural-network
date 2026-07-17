# ANN Terminal Conversation Mode

ANN Desktop now separates natural language from safe terminal commands.

## Purpose

The terminal panel accepts ordinary text such as `hola` and routes it to the ANN conversation layer. Registered commands such as `models`, `runtime`, `projects`, `artifacts`, `logs`, `status`, and `clear` still use the safe allowlist.

If the local conversation model is not available, ANN does not fake real inference. It reports the fallback clearly and keeps safe commands available.

The conversation identity is explicit:

- Name: ANN
- Meaning: Agentic Neural Network
- Role: official voice of ANN to the user
- Task: understand software-engineering intent, preserve constraints, select safe local pipelines, coordinate agents, explain runtime state, and request approval before critical actions

## Architecture

- UI: `apps/web/src/components/enterprise-figma-ui.tsx`
- Conversation API: `apps/web/src/app/api/conversation/message/route.ts`
- Safe command API: `apps/web/src/app/api/terminal/run/route.ts`
- Classifier/runtime helper: `apps/web/src/lib/ann-terminal.ts`

The classifier returns one of:

- `CONVERSATION_MESSAGE`
- `ANN_SAFE_COMMAND`
- `BUILTIN_COMMAND`
- `EXPLICIT_SHELL_ATTEMPT`
- `MALFORMED_INPUT`
- `EMPTY`

## Modes

- `mode auto`: natural language is conversation, registered commands are commands.
- `mode chat`: natural language remains conversation, registered commands still work.
- `mode command`: only registered safe commands are accepted.

## Safety

The conversation route does not execute shell commands. Explicit shell/package-install attempts such as `pip install ...`, `npm install ...`, `powershell ...`, or `cmd ...` are blocked and reported as policy violations.

The safe terminal route remains allowlist-only and does not invoke arbitrary host execution.

## Qwen3 Conversation Orchestrator

The conversation layer checks the configured conversation model in `config/ann_model_inventory.json` and `config/ann_terminal_conversation_runtime.json`.

If the GGUF file is missing or real model loading is disabled by `config/ann_model_policy.json`, the UI clearly reports that the backend is unavailable or simulated. It does not claim real Qwen3 inference.

Current real local conversation backend:

```text
D:/Models/qwen3-4b-instruct-2507-q4_k_m.gguf
```

```text
model: qwen3_4b_conversation_orchestrator
windows path: D:/Models/qwen3-4b-instruct-2507-q4_k_m.gguf
WSL path: /mnt/d/Models/qwen3-4b-instruct-2507-q4_k_m.gguf
runtime: /home/<user>/miniconda3/envs/qlora311/bin/python
backend: llama_cpp
```

This is configured in:

```text
config/ann_terminal_conversation_runtime.json
```

The bridge calls one fixed Python script with `shell: false`:

```text
scripts/runtime/run_conversation_llama_cpp.py
```

The script loads one local GGUF, generates one response, and exits so the model is unloaded by process teardown. It does not download, install, modify models, write adapters/datasets, or run project commands.

Manual smoke evidence:

```text
Qwen3-4B GGUF load: passed
safe rollback: active_models_after=0, parallel_llm_loads_after=0
```

## Intent Contracts

Operational language produces an `ann_intent_contract_v1` structure with:

- `primary_intent`
- `recommended_pipeline`
- `requires_confirmation`
- `requires_human_approval`
- `explicit_constraints`
- `forbidden_actions`
- `requested_capabilities`
- `missing_information`

Examples:

- `qué modelos están disponibles` -> `model_inventory_query`
- `explícame por qué el runtime está bloqueado` -> `runtime_diagnostics_query`
- `arregla el login pero no cambies la base de datos` -> `debug_and_fix` with human approval and preserved database restriction
- `aplica el parche` -> patch workflow with approval required

## Capabilities

Current typed capabilities are conservative:

- `get_model_inventory` read-only
- `get_runtime_status` read-only
- `get_active_project` read-only
- `get_recent_artifacts` read-only
- `start_pipeline` prepared only, not directly executed from the model

Unknown capabilities are blocked.

## Approvals

Write-oriented tasks create pending approval metadata. The terminal does not treat a casual `sí` as permission to write. The real Human Approval/Patch Apply gates remain authoritative.

## Cancellation

`cancel` clears transient terminal task state, pending clarification, pending approval, and selected pipeline state. It does not apply patches and does not execute shell.

## Events

Conversation responses include progressive events for the terminal:

- understanding request
- building context
- extracting intent
- validating restrictions
- selected pipeline
- approval required when relevant
- assistant response

## Limitations

This phase fixes terminal routing and state handoff. Real Qwen3 conversation inference still requires the registered GGUF model file and model policy that explicitly permits controlled real model loading.

The current implementation provides a deterministic conversation adapter and contract builder when Qwen3-4B is unavailable. It does not pretend that deterministic fallback text is real model inference.

Streaming tokens are represented as progressive terminal events. True token streaming depends on the future real backend adapter exposing streaming callbacks.
