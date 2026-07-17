import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

base_model = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
adapter_path = "training/adapters/agentic-v1"

tokenizer = AutoTokenizer.from_pretrained(adapter_path)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    base_model,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(model, adapter_path)
model.eval()

messages = [
    {"role": "system", "content": "You are a senior software architect."},
    {"role": "user", "content": "Design a SaaS CRM architecture."},
]

prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    outputs = model.generate(
    **inputs,
    max_new_tokens=350,
    temperature=0.4,
    top_p=0.85,
    repetition_penalty=1.18,
    no_repeat_ngram_size=4,
    do_sample=True,
)

print(tokenizer.decode(outputs[0], skip_special_tokens=True))
