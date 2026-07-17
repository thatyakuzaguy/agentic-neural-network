import json
import os
from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
BASE_ADAPTER = "training/adapters/qwen-7b-unsloth-agentic-v1"
DATASET_PATH = "training/datasets/agentic_principal_v2.jsonl"
OUTPUT_DIR = "training/adapters/qwen-7b-principal-v2"

MAX_SEQ_LENGTH = 512

def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def latest_checkpoint(path):
    if not os.path.exists(path):
        return None
    checkpoints = []
    for name in os.listdir(path):
        if name.startswith("checkpoint-"):
            try:
                checkpoints.append((int(name.split("-")[-1]), os.path.join(path, name)))
            except ValueError:
                pass
    if not checkpoints:
        return None
    checkpoints.sort(key=lambda x: x[0])
    return checkpoints[-1][1]

def main():
    print("Loading base model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )

    print("Loading previous adapter...")
    model.load_adapter(BASE_ADAPTER)

    print("Preparing PEFT model for continued training...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=8,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    print("Loading dataset...")
    rows = load_jsonl(DATASET_PATH)

    def format_row(row):
        return {
            "text": tokenizer.apply_chat_template(
                row["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        }

    dataset = Dataset.from_list([format_row(row) for row in rows])
    print(f"Loaded {len(dataset)} examples.")

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=1,
        learning_rate=5e-5,
        fp16=False,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        warmup_ratio=0.03,
        report_to="none",
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=config,
    )

    checkpoint = latest_checkpoint(OUTPUT_DIR)

    if checkpoint:
        print(f"Resuming from checkpoint: {checkpoint}")
        trainer.train(resume_from_checkpoint=checkpoint)
    else:
        trainer.train()

    print("Saving principal v2 adapter...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Done. Saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
