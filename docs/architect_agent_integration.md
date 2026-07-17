# Architect Agent Integration

## Purpose

The Architect Agent converts the Product Agent requirements artifact into an implementation-ready
technical plan for the Code Agent. It is an integration stage only; it does not train models, write
final code, modify adapters, or change datasets.

## Pipeline Position

```text
User request
-> Product Agent
-> Architect Agent
-> Code Agent
```

The pipeline now writes:

- `01_product_requirements.md`
- `02_architecture_plan.md`

## Modes

- `fast`: default mode. Uses Qwen3-8B or the lightweight local model path configured by
  `ANN_ARCHITECT_FAST_MODEL`.
- `deep`: explicit high-impact mode. Uses the local DeepSeek 14B path configured by
  `ANN_ARCHITECT_DEEP_MODEL`.
- `auto`: starts from fast mode and routes to deep mode only when the task looks large or risky.
  Risk indicators include security-sensitive changes, auth flows, payment flows, migrations, large
  refactors, multi-file architecture changes, or unclear acceptance criteria.

DeepSeek 14B is intentionally reserved for deep mode. A local DeepSeek run can take around 40
minutes, so do not use it for every pipeline step.

## Expected Output Format

```text
TECHNICAL SUMMARY
- ...

AFFECTED AREAS
- ...

FILES TO INSPECT
- ...

IMPLEMENTATION PLAN
- ...

DATA OR STATE CHANGES
- ...

TEST STRATEGY
- ...

RISKS
- ...

HANDOFF TO CODE AGENT
- ...

CONFIDENCE
High
```

The validator requires every section exactly once, `CONFIDENCE` set to `High`, no code fences, no
think tags, no markdown headings, at least one `HANDOFF TO CODE AGENT` bullet, and a
`FILES TO INSPECT` bullet even when no specific files are known yet.

## Config Keys

```env
ANN_ARCHITECT_MODE=fast
ANN_ARCHITECT_FAST_MODEL=/mnt/d/Models/qwen3
ANN_ARCHITECT_DEEP_MODEL=/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf
ANN_ARCHITECT_OUTPUT=02_architecture_plan.md
ANN_STAGE_ISOLATION=subprocess
```

`ARCHITECT_MODEL_BACKEND=qwen3` remains documented for compatibility with the role-backend routing
table, but Architect Agent mode selection is controlled by the `ANN_ARCHITECT_*` keys.

`ANN_STAGE_ISOLATION=subprocess` runs real Product and Architect LLM stages through their CLI entry
points in separate Python processes. This prevents Product Agent Unsloth/FastLanguageModel global
patches from leaking into the Architect Agent Qwen3 runtime. Mock mode remains in-process for fast
tests.

If the DeepSeek path differs locally, set `ANN_ARCHITECT_DEEP_MODEL` to the existing `/mnt/d` model
path. Do not point it at `/mnt/c`.

## CLI Smoke Test

Real fast-mode CLI:

```bash
python -m agentic_network.architect_agent.run --mode fast "Add rate limits to password reset requests."
```

Fast smoke test without loading a real model:

```bash
python -m agentic_network.architect_agent.run --mode fast --mock "Add rate limits to password reset requests."
```

To write an artifact explicitly:

```bash
python -m agentic_network.architect_agent.run --mode fast --mock \
  --output /mnt/d/AgenticEngineeringNetwork/outputs/runs/architect_smoke/02_architecture_plan.md \
  "Add rate limits to password reset requests."
```
