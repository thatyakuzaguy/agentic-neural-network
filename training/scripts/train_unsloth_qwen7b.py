import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig


MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"
DATASET_PATH = "training/datasets/external_50k_mixed.jsonl"
OUTPUT_DIR = "training/adapters/qwen-7b-unsloth-agentic-v1"

MAX_SEQ_LENGTH = 512
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.05

BATCH_SIZE = 1
GRAD_ACCUM = 8
EPOCHS = 1
LEARNING_RATE = 1e-4

SAVE_STEPS = 200
SAVE_TOTAL_LIMIT = 3


def load_jsonl(path):
    rows = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))

    if not rows:
        raise ValueError("Dataset is empty.")

    return rows


def main():
    print("CUDA:", torch.cuda.is_available())
    print("GPU:", torch.cuda.get_device_name(0))

    print("Loading model with Unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )

    print("Loading dataset...")
    raw = load_jsonl(DATASET_PATH)

    def format_row(row):
        text = tokenizer.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}

    dataset = Dataset.from_list([format_row(row) for row in raw])

    print(f"Loaded {len(dataset)} examples.")

    latest_checkpoint = None
    if os.path.exists(OUTPUT_DIR):
        checkpoints = []
        for name in os.listdir(OUTPUT_DIR):
            if name.startswith("checkpoint-"):
                try:
                    step = int(name.split("-")[-1])
                    checkpoints.append((step, os.path.join(OUTPUT_DIR, name)))
                except ValueError:
                    pass
        if checkpoints:
            checkpoints.sort(key=lambda x: x[0])
            latest_checkpoint = checkpoints[-1][1]

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        num_train_epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        fp16=False,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=SAVE_STEPS,
        save_total_limit=SAVE_TOTAL_LIMIT,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        warmup_ratio=0.03,
        report_to="none",
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=config,
    )

    if latest_checkpoint:
        print(f"Resuming from checkpoint: {latest_checkpoint}")
        trainer.train(resume_from_checkpoint=latest_checkpoint)
    else:
        trainer.train()

    print("Saving final adapter...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Done. Saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
