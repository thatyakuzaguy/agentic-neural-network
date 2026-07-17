from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import warnings
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from unsloth import FastLanguageModel
except ImportError as exc:
    FastLanguageModel = None
    UNSLOTH_IMPORT_ERROR = exc
else:
    UNSLOTH_IMPORT_ERROR = None


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "training" / "configs" / "qwen3_product_agent_v1.yaml"
CHATML_END = "<|im_end|>"
CHATML_USER_TEMPLATE = "<|im_start|>user\n"
CHATML_ASSISTANT_TEMPLATE = "<|im_start|>assistant\n"
PRODUCT_AGENT_SYSTEM_PROMPT = (
    "You are a Product Agent. Convert a software task into concise, grounded Product Agent "
    "analysis with these exact sections: REQUIREMENTS, AMBIGUITIES, ASSUMPTIONS, "
    "ACCEPTANCE CRITERIA, RISKS, CONFIDENCE. Do not output hidden reasoning, think tags, "
    "markdown headings, or a second answer. Do not introduce tenant behavior, retry_after "
    "or Retry-After headers, API secrets, direct database access, idempotency stores, reset "
    "tokens, or other technical details unless the user task explicitly asks for them. "
    "When a detail is not specified, put it under AMBIGUITIES instead of asserting it."
)
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ProductAgentTrainingConfig:
    model_name_or_path: str
    dataset_path: Path
    output_dir: Path
    max_seq_length: int
    load_in_4bit: bool
    local_files_only: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    target_modules: list[str]
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    num_train_epochs: int
    learning_rate: float
    warmup_ratio: float
    weight_decay: float
    logging_steps: int
    save_steps: int
    save_total_limit: int
    optim: str
    lr_scheduler_type: str
    packing: bool
    bf16: bool
    fp16: bool
    seed: int
    hf_home: Path
    torch_home: Path
    unsloth_cache_dir: Path


def _parse_scalar(value: str) -> Any:
    cleaned = value.strip().strip("'\"")
    lowered = cleaned.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return cleaned


def load_flat_yaml(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"Unsupported config line {line_number}: {line}")
        key, raw_value = stripped.split(":", 1)
        values[key.strip()] = _parse_scalar(raw_value)
    return values


def _path(value: Any) -> Path:
    return Path(str(value))


def load_training_config(path: Path = DEFAULT_CONFIG_PATH) -> ProductAgentTrainingConfig:
    raw = load_flat_yaml(path)
    target_modules = str(raw["target_modules"]).split(",")
    config = ProductAgentTrainingConfig(
        model_name_or_path=str(raw["model_name_or_path"]),
        dataset_path=_path(raw["dataset_path"]),
        output_dir=_path(raw["output_dir"]),
        max_seq_length=int(raw.get("max_seq_length", 2048)),
        load_in_4bit=bool(raw.get("load_in_4bit", True)),
        local_files_only=bool(raw.get("local_files_only", True)),
        lora_r=int(raw.get("lora_r", 16)),
        lora_alpha=int(raw.get("lora_alpha", 32)),
        lora_dropout=float(raw.get("lora_dropout", 0.05)),
        target_modules=[module.strip() for module in target_modules if module.strip()],
        per_device_train_batch_size=int(raw.get("per_device_train_batch_size", 1)),
        gradient_accumulation_steps=int(raw.get("gradient_accumulation_steps", 8)),
        num_train_epochs=int(raw.get("num_train_epochs", 1)),
        learning_rate=float(raw.get("learning_rate", 0.0002)),
        warmup_ratio=float(raw.get("warmup_ratio", 0.03)),
        weight_decay=float(raw.get("weight_decay", 0.01)),
        logging_steps=int(raw.get("logging_steps", 10)),
        save_steps=int(raw.get("save_steps", 100)),
        save_total_limit=int(raw.get("save_total_limit", 3)),
        optim=str(raw.get("optim", "adamw_8bit")),
        lr_scheduler_type=str(raw.get("lr_scheduler_type", "linear")),
        packing=bool(raw.get("packing", False)),
        bf16=bool(raw.get("bf16", True)),
        fp16=bool(raw.get("fp16", False)),
        seed=int(raw.get("seed", 42)),
        hf_home=_path(raw["hf_home"]),
        torch_home=_path(raw["torch_home"]),
        unsloth_cache_dir=_path(raw["unsloth_cache_dir"]),
    )
    validate_d_only_config(config)
    return config


def is_d_path(path_value: str | Path) -> bool:
    text = str(path_value).replace("\\", "/")
    path = Path(text)
    if path.drive:
        return path.drive.upper() == "D:"
    return text.startswith("/mnt/d/")


def require_d_path(path_value: str | Path, label: str) -> None:
    if not is_d_path(path_value):
        raise ValueError(f"{label} must be on D: or /mnt/d. Got: {path_value}")


def validate_d_only_config(config: ProductAgentTrainingConfig) -> None:
    require_d_path(config.model_name_or_path, "model_name_or_path")
    require_d_path(config.dataset_path, "dataset_path")
    require_d_path(config.output_dir, "output_dir")
    require_d_path(config.hf_home, "hf_home")
    require_d_path(config.torch_home, "torch_home")
    require_d_path(config.unsloth_cache_dir, "unsloth_cache_dir")
    if not config.load_in_4bit:
        raise ValueError("This training job must use load_in_4bit=True.")
    if not config.local_files_only:
        raise ValueError("This training job must use local_files_only=True.")


def configure_offline_d_cache(config: ProductAgentTrainingConfig) -> None:
    for cache_dir in (config.hf_home, config.torch_home, config.unsloth_cache_dir):
        cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(config.hf_home)
    os.environ["HF_HUB_CACHE"] = str(config.hf_home / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(config.hf_home / "transformers")
    os.environ["TORCH_HOME"] = str(config.torch_home)
    os.environ["UNSLOTH_CACHE_DIR"] = str(config.unsloth_cache_dir)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def normalize_training_row(row: dict[str, Any], line_number: int) -> dict[str, str]:
    instruction = row.get("instruction")
    response = row.get("response")
    if instruction is None and "candidate_task" in row:
        instruction = row.get("candidate_task")
    if response is None and "candidate_response" in row:
        response = row.get("candidate_response")

    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError(f"Line {line_number} is missing a non-empty instruction.")
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"Line {line_number} is missing a non-empty response.")

    return {"instruction": instruction.strip(), "response": response.strip()}


def load_product_agent_jsonl(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    require_d_path(path, "dataset_path")
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            rows.append(normalize_training_row(json.loads(line), line_number))
            if limit is not None and len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f"Dataset is empty: {path}")
    return rows


def format_product_agent_prompt(instruction: str, response: str) -> str:
    clean_response = sanitize_assistant_response_for_training(response)
    return (
        "<|im_start|>system\n"
        f"{PRODUCT_AGENT_SYSTEM_PROMPT}{CHATML_END}\n"
        f"{CHATML_USER_TEMPLATE}"
        f"{instruction.strip()}{CHATML_END}\n"
        f"{CHATML_ASSISTANT_TEMPLATE}"
        f"{clean_response}{CHATML_END}"
    )


def format_product_agent_inference_prompt(instruction: str) -> str:
    return (
        "<|im_start|>system\n"
        f"{PRODUCT_AGENT_SYSTEM_PROMPT}{CHATML_END}\n"
        f"{CHATML_USER_TEMPLATE}"
        f"{instruction.strip()}{CHATML_END}\n"
        f"{CHATML_ASSISTANT_TEMPLATE}"
    )


def sanitize_assistant_response_for_training(response: str) -> str:
    text = THINK_BLOCK.sub("", response)
    for token in (
        CHATML_END,
        "<|im_start|>assistant",
        "<|im_start|>user",
        "<|im_start|>system",
        "<think>",
        "</think>",
    ):
        text = text.replace(token, "")
    return text.strip()


def _tokenizer_truncate_text(tokenizer: Any, text: str, max_seq_length: int) -> str:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        truncation=True,
        max_length=max_seq_length,
    )
    input_ids = encoded["input_ids"]
    return tokenizer.decode(input_ids, skip_special_tokens=False)


def build_training_texts(
    rows: list[dict[str, str]],
    *,
    tokenizer: Any | None = None,
    max_seq_length: int | None = None,
) -> list[dict[str, str]]:
    examples = []
    for row in rows:
        text = format_product_agent_prompt(row["instruction"], row["response"])
        if tokenizer is not None and max_seq_length is not None:
            text = _tokenizer_truncate_text(tokenizer, text, max_seq_length)
        examples.append({"text": text})
    return examples


def latest_checkpoint(output_dir: Path) -> str | None:
    if not output_dir.exists():
        return None
    checkpoints: list[tuple[int, Path]] = []
    for child in output_dir.iterdir():
        if not child.name.startswith("checkpoint-"):
            continue
        try:
            checkpoints.append((int(child.name.rsplit("-", 1)[1]), child))
        except ValueError:
            continue
    if not checkpoints:
        return None
    checkpoints.sort(key=lambda item: item[0])
    return str(checkpoints[-1][1])


def training_metadata(
    config: ProductAgentTrainingConfig,
    *,
    dataset_rows: int,
    max_steps: int | None,
) -> dict[str, Any]:
    payload = asdict(config)
    for key in ("dataset_path", "output_dir", "hf_home", "torch_home", "unsloth_cache_dir"):
        payload[key] = str(payload[key])
    return {
        "created_at": datetime.now(tz=UTC).isoformat(),
        "base_model": config.model_name_or_path,
        "dataset_path": str(config.dataset_path),
        "dataset_rows": dataset_rows,
        "output_dir": str(config.output_dir),
        "load_in_4bit": config.load_in_4bit,
        "local_files_only": config.local_files_only,
        "max_seq_length": config.max_seq_length,
        "max_steps": max_steps,
        "adapter_only": True,
        "merged_adapter": False,
        "config": payload,
    }


def callable_supports_kwarg(callable_obj: Any, kwarg: str) -> bool:
    parameters = inspect.signature(callable_obj).parameters
    return kwarg in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


def supported_kwargs(callable_obj: Any, candidate_kwargs: dict[str, Any]) -> dict[str, Any]:
    parameters = inspect.signature(callable_obj).parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return dict(candidate_kwargs)
    return {key: value for key, value in candidate_kwargs.items() if key in parameters}


def sft_config_kwargs(
    config: ProductAgentTrainingConfig,
    *,
    max_steps: int | None,
) -> dict[str, Any]:
    return {
        "output_dir": str(config.output_dir),
        "dataset_text_field": "text",
        "max_seq_length": config.max_seq_length,
        "per_device_train_batch_size": config.per_device_train_batch_size,
        "gradient_accumulation_steps": config.gradient_accumulation_steps,
        "num_train_epochs": config.num_train_epochs,
        "max_steps": max_steps if max_steps is not None else -1,
        "learning_rate": config.learning_rate,
        "fp16": config.fp16,
        "bf16": config.bf16,
        "logging_steps": config.logging_steps,
        "save_strategy": "steps",
        "save_steps": config.save_steps,
        "save_total_limit": config.save_total_limit,
        "optim": config.optim,
        "weight_decay": config.weight_decay,
        "lr_scheduler_type": config.lr_scheduler_type,
        "warmup_ratio": config.warmup_ratio,
        "report_to": "none",
        "packing": config.packing,
        "seed": config.seed,
    }


def trainer_tokenizer_argument_name(sft_trainer_cls: Any) -> str | None:
    if callable_supports_kwarg(sft_trainer_cls, "processing_class"):
        return "processing_class"
    if callable_supports_kwarg(sft_trainer_cls, "tokenizer"):
        return "tokenizer"
    return None


def trainer_kwargs(
    sft_trainer_cls: Any,
    *,
    model: Any,
    tokenizer: Any,
    train_dataset: Any,
    args: Any,
    max_seq_length: int,
    pass_max_seq_length: bool,
    dataset_text_field: str | None = None,
    packing: bool | None = None,
) -> dict[str, Any]:
    kwargs = {
        "model": model,
        "train_dataset": train_dataset,
        "args": args,
    }
    tokenizer_arg = trainer_tokenizer_argument_name(sft_trainer_cls)
    if tokenizer_arg:
        kwargs[tokenizer_arg] = tokenizer
    if pass_max_seq_length:
        kwargs["max_seq_length"] = max_seq_length
    if dataset_text_field is not None:
        kwargs["dataset_text_field"] = dataset_text_field
    if packing is not None:
        kwargs["packing"] = packing
    return supported_kwargs(sft_trainer_cls, kwargs)


def _load_train_on_responses_only() -> Any | None:
    try:
        from unsloth.chat_templates import train_on_responses_only
    except ImportError:
        return None
    return train_on_responses_only


def apply_assistant_only_loss(trainer: Any, helper: Any | None = None) -> Any:
    helper = helper or _load_train_on_responses_only()
    if helper is None:
        warnings.warn(
            "train_on_responses_only is unavailable; training will use full-sequence loss.",
            stacklevel=2,
        )
        return trainer

    candidate_kwargs = {
        "instruction_template": CHATML_USER_TEMPLATE,
        "response_template": CHATML_ASSISTANT_TEMPLATE,
        "instruction_part": CHATML_USER_TEMPLATE,
        "response_part": CHATML_ASSISTANT_TEMPLATE,
    }
    helper_parameters = inspect.signature(helper).parameters
    kwargs = supported_kwargs(helper, candidate_kwargs)
    try:
        if "trainer" in helper_parameters:
            return helper(trainer=trainer, **kwargs)
        return helper(trainer, **kwargs)
    except TypeError as exc:
        warnings.warn(
            f"train_on_responses_only could not be applied: {exc}. "
            "Training will use full-sequence loss.",
            stacklevel=2,
        )
        return trainer


def run_dry_run(config: ProductAgentTrainingConfig, dataset_limit: int | None) -> None:
    configure_offline_d_cache(config)
    rows = load_product_agent_jsonl(config.dataset_path, limit=dataset_limit)
    examples = build_training_texts(rows)
    print("Dry run complete.")
    print(f"Examples: {len(examples)}")
    print(f"First prompt characters: {len(examples[0]['text'])}")
    print(f"Model path: {config.model_name_or_path}")
    print(f"Output adapter: {config.output_dir}")


def train(config: ProductAgentTrainingConfig, *, max_steps: int | None, dataset_limit: int | None) -> None:
    configure_offline_d_cache(config)
    if FastLanguageModel is None:
        raise RuntimeError("Unsloth is required for training.") from UNSLOTH_IMPORT_ERROR

    import torch
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    print("CUDA:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    print("Loading Qwen3 base model from local D: storage...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name_or_path,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
        local_files_only=config.local_files_only,
    )

    print("Attaching trainable LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=config.lora_r,
        target_modules=config.target_modules,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=config.seed,
        use_rslora=False,
        loftq_config=None,
    )

    requested_sft_config_kwargs = sft_config_kwargs(config, max_steps=max_steps)
    filtered_sft_config_kwargs = supported_kwargs(SFTConfig, requested_sft_config_kwargs)
    sft_config_accepts_max_seq_length = "max_seq_length" in filtered_sft_config_kwargs
    trainer_accepts_max_seq_length = callable_supports_kwarg(SFTTrainer, "max_seq_length")
    trainer_dataset_text_field = (
        "text" if "dataset_text_field" not in filtered_sft_config_kwargs else None
    )
    trainer_packing = config.packing if "packing" not in filtered_sft_config_kwargs else None
    truncate_with_tokenizer = (
        not sft_config_accepts_max_seq_length and not trainer_accepts_max_seq_length
    )

    rows = load_product_agent_jsonl(config.dataset_path, limit=dataset_limit)
    dataset = Dataset.from_list(
        build_training_texts(
            rows,
            tokenizer=tokenizer if truncate_with_tokenizer else None,
            max_seq_length=config.max_seq_length if truncate_with_tokenizer else None,
        )
    )
    print(f"Loaded {len(dataset)} Product Agent examples.")

    sft_config = SFTConfig(**filtered_sft_config_kwargs)
    trainer = SFTTrainer(
        **trainer_kwargs(
            SFTTrainer,
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            args=sft_config,
            max_seq_length=config.max_seq_length,
            pass_max_seq_length=(
                not sft_config_accepts_max_seq_length and trainer_accepts_max_seq_length
            ),
            dataset_text_field=trainer_dataset_text_field,
            packing=trainer_packing,
        )
    )
    trainer = apply_assistant_only_loss(trainer)

    checkpoint = latest_checkpoint(config.output_dir)
    if checkpoint:
        print(f"Resuming from checkpoint: {checkpoint}")
        trainer.train(resume_from_checkpoint=checkpoint)
    else:
        trainer.train()

    print("Saving adapter and tokenizer files...")
    trainer.save_model(str(config.output_dir))
    tokenizer.save_pretrained(str(config.output_dir))
    metadata = training_metadata(config, dataset_rows=len(rows), max_steps=max_steps)
    metadata_path = config.output_dir / "training_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Done. Adapter saved to {config.output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a Qwen3 8B Product Agent LoRA adapter with Unsloth."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--dataset-limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_training_config(args.config)
    if args.dry_run:
        run_dry_run(config, args.dataset_limit)
        return
    train(config, max_steps=args.max_steps, dataset_limit=args.dataset_limit)


if __name__ == "__main__":
    main()
