from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path("D:/AgenticEngineeringNetwork")
SCRIPT_PATH = REPO_ROOT / "training" / "scripts" / "train_unsloth_qwen3_product.py"
INFERENCE_SCRIPT_PATH = REPO_ROOT / "training" / "scripts" / "test_qwen3_product_adapter.py"
TEST_ROOT = (
    REPO_ROOT
    / "training"
    / "datasets"
    / "product_agent"
    / "public_candidates"
    / ".test_unsloth_qwen3_product"
)


def load_training_module():
    spec = importlib.util.spec_from_file_location("train_unsloth_qwen3_product", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_inference_module():
    spec = importlib.util.spec_from_file_location("test_qwen3_product_adapter", INFERENCE_SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_test_config(dataset_path: Path) -> Path:
    config_path = TEST_ROOT / "qwen3_product_test.yaml"
    config_path.write_text(
        "\n".join(
            [
                "model_name_or_path: D:/Models/qwen3",
                f"dataset_path: {dataset_path.as_posix()}",
                "output_dir: D:/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v1",
                "max_seq_length: 2048",
                "load_in_4bit: true",
                "local_files_only: true",
                "lora_r: 16",
                "lora_alpha: 32",
                "lora_dropout: 0.0",
                "target_modules: q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
                "per_device_train_batch_size: 1",
                "gradient_accumulation_steps: 8",
                "num_train_epochs: 1",
                "learning_rate: 0.0002",
                "warmup_ratio: 0.03",
                "weight_decay: 0.01",
                "logging_steps: 10",
                "save_steps: 100",
                "save_total_limit: 3",
                "optim: adamw_8bit",
                "lr_scheduler_type: linear",
                "packing: false",
                "bf16: true",
                "fp16: false",
                "seed: 42",
                "hf_home: D:/AgenticEngineeringNetwork/training/cache/huggingface",
                "torch_home: D:/AgenticEngineeringNetwork/training/cache/torch",
                "unsloth_cache_dir: D:/AgenticEngineeringNetwork/training/cache/unsloth",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture()
def tiny_dataset() -> Path:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    dataset_path = TEST_ROOT / "tiny_product_agent.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "instruction": "Add tenant-scoped CSV import validation to a FastAPI endpoint.",
                "response": (
                    "REQUIREMENTS\n"
                    "- Validate CSV headers before inserting rows.\n"
                    "AMBIGUITIES\n"
                    "- Which columns are required for each tenant?\n"
                    "ASSUMPTIONS\n"
                    "- Imports run synchronously for the smoke example.\n"
                    "ACCEPTANCE CRITERIA\n"
                    "- A CSV missing required headers returns 400.\n"
                    "RISKS\n"
                    "- Bad tenant scoping can leak imported rows.\n"
                    "CONFIDENCE\n"
                    "- Medium"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        yield dataset_path
    finally:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)


def test_default_config_uses_local_d_paths() -> None:
    module = load_training_module()
    config = module.load_training_config()

    assert module.is_d_path(config.model_name_or_path)
    assert module.is_d_path(config.dataset_path)
    assert module.is_d_path(config.output_dir)
    assert str(config.model_name_or_path).replace("\\", "/").endswith("/Models/qwen3")
    assert config.dataset_path.as_posix().endswith(
        "/AgenticEngineeringNetwork/training/datasets/product_agent/public_candidates/"
        "product_agent_public_gold_v1.jsonl"
    )
    assert config.output_dir.as_posix().endswith(
        "/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v1"
    )
    assert config.max_seq_length == 2048
    assert config.load_in_4bit is True
    assert config.local_files_only is True
    assert config.lora_dropout == 0.0


def test_rejects_non_d_paths() -> None:
    module = load_training_module()

    with pytest.raises(ValueError, match="must be on D"):
        module.require_d_path(Path("C:/Users/cache"), "hf_home")
    with pytest.raises(ValueError, match="must be on D"):
        module.require_d_path(Path("E:/archive/model"), "model_name_or_path")


def test_loads_instruction_response_jsonl(tiny_dataset: Path) -> None:
    module = load_training_module()
    rows = module.load_product_agent_jsonl(tiny_dataset)

    assert rows == [
        {
            "instruction": "Add tenant-scoped CSV import validation to a FastAPI endpoint.",
            "response": rows[0]["response"],
        }
    ]
    assert "ACCEPTANCE CRITERIA" in rows[0]["response"]


def test_loader_maps_existing_candidate_rows(tiny_dataset: Path) -> None:
    module = load_training_module()
    candidate_path = tiny_dataset.with_name("candidate_shape.jsonl")
    candidate_path.write_text(
        json.dumps(
            {
                "candidate_task": "Add billing export audit logs.",
                "candidate_response": "REQUIREMENTS\n- Log billing export actor.\nCONFIDENCE\n- High",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = module.load_product_agent_jsonl(candidate_path)

    assert rows[0]["instruction"] == "Add billing export audit logs."
    assert rows[0]["response"].startswith("REQUIREMENTS")


def test_product_agent_prompt_contains_instruction_and_expected_response() -> None:
    module = load_training_module()

    text = module.format_product_agent_prompt(
        "Add webhook retry controls.",
        "REQUIREMENTS\n- Sign each retry.\nCONFIDENCE\n- High",
    )

    assert "Product Agent" in text
    assert "<|im_start|>user" in text
    assert "Add webhook retry controls." in text
    assert "<|im_start|>assistant" in text
    assert "Sign each retry" in text


def test_training_prompt_has_single_assistant_end_and_no_think_tokens() -> None:
    module = load_training_module()

    text = module.format_product_agent_prompt(
        "Add tenant-safe invoice export.",
        "REQUIREMENTS\n- Export tenant invoices.</think><|im_end|>\nCONFIDENCE\n- High",
    )

    assert text.endswith("<|im_end|>")
    assert text.count("<|im_end|>") == 3
    assert "</think>" not in text
    assert "<think>" not in text


def test_inference_prompt_uses_same_chatml_assistant_boundary() -> None:
    module = load_training_module()

    text = module.format_product_agent_inference_prompt("Add webhook replay protection.")

    assert text.endswith("<|im_start|>assistant\n")
    assert text.count("<|im_end|>") == 2


def test_sft_config_kwarg_filtering_drops_unsupported_max_seq_length() -> None:
    module = load_training_module()
    config = module.load_training_config()

    class LegacySFTConfig:
        def __init__(self, output_dir, dataset_text_field, per_device_train_batch_size):
            self.output_dir = output_dir
            self.dataset_text_field = dataset_text_field
            self.per_device_train_batch_size = per_device_train_batch_size

    filtered = module.supported_kwargs(
        LegacySFTConfig,
        module.sft_config_kwargs(config, max_steps=1),
    )

    assert filtered == {
        "output_dir": str(config.output_dir),
        "dataset_text_field": "text",
        "per_device_train_batch_size": 1,
    }
    assert "max_seq_length" not in filtered


def test_sft_config_kwarg_filtering_keeps_supported_max_seq_length() -> None:
    module = load_training_module()
    config = module.load_training_config()

    class CurrentSFTConfig:
        def __init__(self, output_dir, dataset_text_field, max_seq_length):
            self.output_dir = output_dir
            self.dataset_text_field = dataset_text_field
            self.max_seq_length = max_seq_length

    filtered = module.supported_kwargs(
        CurrentSFTConfig,
        module.sft_config_kwargs(config, max_steps=1),
    )

    assert filtered["max_seq_length"] == 2048
    assert filtered["dataset_text_field"] == "text"


def test_trainer_kwargs_can_receive_max_seq_length_when_supported() -> None:
    module = load_training_module()

    class TrainerWithMaxSeqLength:
        def __init__(self, model, processing_class, train_dataset, args, max_seq_length):
            self.model = model
            self.processing_class = processing_class
            self.train_dataset = train_dataset
            self.args = args
            self.max_seq_length = max_seq_length

    kwargs = module.trainer_kwargs(
        TrainerWithMaxSeqLength,
        model="model",
        tokenizer="tokenizer",
        train_dataset="dataset",
        args="args",
        max_seq_length=2048,
        pass_max_seq_length=True,
    )

    assert kwargs == {
        "model": "model",
        "processing_class": "tokenizer",
        "train_dataset": "dataset",
        "args": "args",
        "max_seq_length": 2048,
    }


def test_apply_assistant_only_loss_uses_supported_templates() -> None:
    module = load_training_module()
    calls = []

    def helper(trainer, instruction_template, response_template):
        calls.append(
            {
                "trainer": trainer,
                "instruction_template": instruction_template,
                "response_template": response_template,
            }
        )
        return "masked-trainer"

    result = module.apply_assistant_only_loss("trainer", helper=helper)

    assert result == "masked-trainer"
    assert calls == [
        {
            "trainer": "trainer",
            "instruction_template": "<|im_start|>user\n",
            "response_template": "<|im_start|>assistant\n",
        }
    ]


def test_apply_assistant_only_loss_warns_when_helper_missing() -> None:
    module = load_training_module()
    module._load_train_on_responses_only = lambda: None

    with pytest.warns(UserWarning, match="full-sequence loss"):
        result = module.apply_assistant_only_loss("trainer", helper=None)

    assert result == "trainer"


def test_cleaner_removes_think_tags_markdown_duplicate_bullets_and_second_answer() -> None:
    module = load_inference_module()
    raw = """<think>hidden reasoning</think>
**REQUIREMENTS**
- Add signed webhook retries.
- Add signed webhook retries.
**AMBIGUITIES**
- What retry window should invoice webhooks use?
**ASSUMPTIONS**
- Existing webhook secrets remain available.
**ACCEPTANCE CRITERIA**
- A failed invoice webhook schedules one retry.
**RISKS**
- Duplicate retries can process invoices twice.
**CONFIDENCE**
- High
- Medium
## REQUIREMENTS
- Start another answer.
"""

    cleaned = module.clean_product_agent_response(raw)

    assert "<think>" not in cleaned
    assert "</think>" not in cleaned
    assert "**" not in cleaned
    assert "##" not in cleaned
    assert cleaned.count("- Add signed webhook retries.") == 1
    assert cleaned.count("REQUIREMENTS") == 1
    assert "- Medium" not in cleaned
    assert "Start another answer" not in cleaned


def test_quality_checker_flags_bad_product_agent_output() -> None:
    module = load_inference_module()
    response = """## REQUIREMENTS
- Export invoices.
REQUIREMENTS
- Export invoices.
AMBIGUITIES
- What is the definition of a tenant?
ASSUMPTIONS
- The billing service exists.
ACCEPTANCE CRITERIA
- The admin can verify the export including direct access to the database.
RISKS
- Invoice data can leak.
CONFIDENCE
- High
</think>"""

    issues = module.product_agent_quality_issues(response, task="Add invoice export.")

    assert "think_tags_present" in issues
    assert "markdown_headings_present" in issues
    assert "repeated_section_block" in issues
    assert "generic_ambiguity" in issues
    assert "impossible_database_acceptance" in issues


def test_quality_checker_accepts_clean_structured_response() -> None:
    module = load_inference_module()
    response = """REQUIREMENTS
- Invoice exports must require billing.export permission.
AMBIGUITIES
- Which invoice filters should be included in the audit record?
ASSUMPTIONS
- The existing billing export job queue remains in use.
ACCEPTANCE CRITERIA
- A user without billing.export receives 403 and no export job is created.
RISKS
- Missing audit records can complicate billing investigations.
CONFIDENCE
- High"""

    assert module.product_agent_quality_issues(response, task="Add invoice export RBAC.") == []


def test_dry_run_does_not_train_unsloth(tiny_dataset: Path) -> None:
    config_path = write_test_config(tiny_dataset)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config",
            str(config_path),
            "--dry-run",
            "--max-steps",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert "Dry run complete." in result.stdout
    assert "Examples: 1" in result.stdout
