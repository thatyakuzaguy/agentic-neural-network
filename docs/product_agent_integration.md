# Stable Product Agent Integration

## Purpose

The Product Agent is the first stage of the local ANN pipeline. It receives
a short software or product instruction and converts it into grounded product analysis before any
planning, architecture, coding, or testing stage runs.

It behaves as a senior Product Manager / Business Analyst. It must not generate code, APIs,
endpoints, database design, architecture, tenants, workspaces, organizations, admins, email
domains, HTTP status codes, or implementation details unless the user explicitly asks for them.

## Adapter

```text
/mnt/d/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v9-repaired-v2-bullets
```

## Base Model

```text
/mnt/d/Models/qwen3
```

## Config

```text
/mnt/d/AgenticEngineeringNetwork/training/configs/qwen3_product_agent_v9_repaired_v2_bullets.yaml
```

The config keeps Hugging Face, Torch, and Unsloth caches under `/mnt/d`.

## Dataset Used

```text
/mnt/d/AgenticEngineeringNetwork/training/datasets/product_agent/combined/product_agent_combined_v9_repaired_v2_bullets.jsonl
```

## Benchmark

```text
/mnt/d/AgenticEngineeringNetwork/training/eval/product_agent_v9_repaired_v2_bullets_report.txt
```

Result:

```text
prompts: 30
runtime_failures: 0
responses_with_forbidden_terms: 0
responses_with_format_issues: 0
```

## Expected Output

```text
REQUIREMENTS
- ...

AMBIGUITIES
- ...

ASSUMPTIONS
- ...

ACCEPTANCE CRITERIA
- ...

RISKS
- ...

CONFIDENCE
High
```

## Runtime API

```python
from agentic_network.product_agent import run_product_agent

result = run_product_agent("Add rate limits to password reset requests.")
print(result.cleaned_response)
print(result.parsed_sections)
print(result.quality_warnings)
```

The returned object includes:

- `raw_instruction`
- `cleaned_response`
- `parsed_sections`
- `quality_warnings`
- `adapter_path`
- `config_path`

If validation fails, the response is still returned and validation errors are surfaced; failures are
not silently hidden.

## CLI Smoke Test

```bash
cd /mnt/d/AgenticEngineeringNetwork
python -m agentic_network.product_agent.run "Add rate limits to password reset requests."
python -m agentic_network.product_agent.run "Support pagination for product search."
```

For structured JSON:

```bash
python -m agentic_network.product_agent.run "Add rate limits to password reset requests." --json
```

## Pipeline Connection

The local pipeline now routes the first stage as:

```text
user request
-> Product Agent stable Qwen3 adapter
-> Architect / Planning stage
-> Code / Test / Security / Review stages
```

The Product Agent stage receives the raw user instruction. Its cleaned structured output is saved as
`01_product_requirements.md` and is passed to the next stage without losing section boundaries.

The default route is controlled by:

```env
PRODUCT_MODEL_BACKEND=qwen3
PRODUCT_AGENT_CONFIG_PATH=/mnt/d/AgenticEngineeringNetwork/training/configs/qwen3_product_agent_v9_repaired_v2_bullets.yaml
```

When `PRODUCT_MODEL_BACKEND=qwen3`, the product stage uses the stable Product Agent adapter rather
than the generic Qwen3 base model.
