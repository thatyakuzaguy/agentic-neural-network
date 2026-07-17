# Product Agent Self-Instruct Dataset

Product Agent dataset generation lives under `dataset_generation/` and writes dataset artifacts to:

```text
training/datasets/product_agent/
```

This keeps active dataset work on the repository drive (`D:`). Do not redirect dataset outputs, caches, generated examples, or model artifacts to `C:`. Use `E:` only for archives or backups, and do not move existing models.

## Workflow

Generate deterministic software engineering tasks:

```powershell
python dataset_generation/generate_tasks.py --count 100
```

Generate raw Product Agent answers with the existing DeepSeek GGUF wrapper:

```powershell
python dataset_generation/generate_product_dataset.py
```

Review raw examples with deterministic Product Agent structure checks, the shared static sanity
checker, and the same blocking-static-findings guard used by the Reviewer Agent:

```powershell
python dataset_generation/review_product_dataset.py
```

Export approved examples:

```powershell
python dataset_generation/export_product_jsonl.py
```

The exported training file is:

```text
training/datasets/product_agent/product_agent_gold_v1.jsonl
```

Each exported line has this shape:

```json
{"instruction": "<task>", "response": "<approved product output>"}
```

## Required Teacher Output

Raw examples are approved only when they use these sections exactly once, in this order:

```text
REQUIREMENTS
AMBIGUITIES
ASSUMPTIONS
ACCEPTANCE CRITERIA
RISKS
CONFIDENCE
```

`CONFIDENCE` must be exactly `High`, `Medium`, or `Low`.
