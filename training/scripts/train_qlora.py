import argparse
import json
import os
import yaml
import torch

from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig
from trl import SFTTrainer


def load_jsonl(path: str):
    rows = []

    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if "messages" not in row:
                raise ValueError(f"Missing messages on line {line_number}")

            rows.append(row)

    if not rows:
        raise ValueError("Dataset is empty.")

    return rows


def format_example(example, tokenizer):
    return tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )


def find_latest_checkpoint(output_dir: str):
    if not os.path.exists(output_dir):
        return None

    checkpoints = []

    for name in os.listdir(output_dir):
        if not name.startswith("checkpoint-"):
            continue

        full_path = os.path.join(output_dir, name)

        if not os.path.isdir(full_path):
            continue

        try:
            step = int(name.split("-")[-1])
        except ValueError:
            continue

        checkpoints.append((step, full_path))

    if not checkpoints:
        return None

    checkpoints.sort(key=lambda item: item[0])
    return checkpoints[-1][1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as file:
        cfg = yaml.safe_load(file)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not detected.")

    print("CUDA available:", torch.cuda.is_available())
    print("GPU:", torch.cuda.get_device_name(0))

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        cfg["base_model"],
        trust_remote_code=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Loading dataset...")
    raw_rows = load_jsonl(cfg["dataset_path"])
    texts = [format_example(row, tokenizer) for row in raw_rows]

    max_length = cfg.get("max_seq_length", 512)

    def tokenize_batch(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            padding=False,
            max_length=max_length,
        )

    dataset = Dataset.from_dict({"text": texts})

    tokenized_dataset = dataset.map(
        tokenize_batch,
        batched=True,
        remove_columns=["text"],
    )

    print(f"Loaded {len(tokenized_dataset)} training examples.")

    print("Loading model in 4-bit QLoRA mode...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"],
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model.config.use_cache = False

    peft_config = LoraConfig(
        r=cfg.get("lora_r", 8),
        lora_alpha=cfg.get("lora_alpha", 16),
        lora_dropout=cfg.get("lora_dropout", 0.05),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )

    training_args = TrainingArguments(
        output_dir=cfg["output_dir"],
        per_device_train_batch_size=cfg.get("batch_size", 1),
        gradient_accumulation_steps=cfg.get("gradient_accumulation_steps", 4),
        num_train_epochs=cfg.get("epochs", 1),
        learning_rate=cfg.get("learning_rate", 2e-4),
        fp16=True,
        bf16=False,
        logging_steps=cfg.get("logging_steps", 10),
        save_strategy="steps",
        save_steps=cfg.get("save_steps", 200),
        save_total_limit=cfg.get("save_total_limit", 4),
        optim="paged_adamw_8bit",
        gradient_checkpointing=cfg.get("gradient_checkpointing", True),
        report_to="none",
        remove_unused_columns=False,
        max_grad_norm=cfg.get("max_grad_norm", 0.3),
    )

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    print("Starting QLoRA training...")

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        peft_config=peft_config,
        processing_class=tokenizer,
        data_collator=data_collator,
    )

    latest_checkpoint = find_latest_checkpoint(cfg["output_dir"])

    if latest_checkpoint:
        print(f"Resuming from checkpoint: {latest_checkpoint}")
        trainer.train(resume_from_checkpoint=latest_checkpoint)
    else:
        trainer.train()

    print("Saving adapter...")
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])

    print(f"Done. Adapter saved to: {cfg['output_dir']}")


if __name__ == "__main__":
    main()
