from unsloth import FastLanguageModel

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER = "training/adapters/qwen-7b-python-expert-v5"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=4096,
    load_in_4bit=True,
)

model.load_adapter(ADAPTER, adapter_name="python_v5")
model.set_adapter("python_v5")

FastLanguageModel.for_inference(model)

prompt = """
Design ONLY the CSV contact import endpoint for a multi-tenant SaaS CRM.

Rules:
- Do NOT explain concepts.
- Do NOT create CRUD endpoints.
- Do NOT create update/delete endpoints.
- Output code only.

Requirements:
- FastAPI
- AsyncSession
- PostgreSQL
- SQLAlchemy 2.0
- tenant_id enforced in every database operation
- RBAC using require_permission("contacts:import")
- Idempotency-Key header
- Audit logs
- Structured logging
- Background job queue
- Repository pattern
- Service layer
- Pydantic v2
- pytest tests

Must include:

1. ContactImportJob model
2. Idempotency model
3. Repository
4. Service
5. Router endpoint
6. Pytest examples

Reject any design that:
- accepts tenant_id from request body
- uses synchronous Session
- uses requests instead of httpx
- omits audit logs
- omits RBAC
- omits tenant filtering

Generate production-ready code.
"""

messages = [
    {
        "role": "system",
        "content": "You are a senior Python backend engineer."
    },
    {
        "role": "user",
        "content": prompt
    }
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)

inputs = tokenizer(text, return_tensors="pt").to("cuda")

outputs = model.generate(
    **inputs,
    max_new_tokens=1200,
    temperature=0.2,
    top_p=0.85,
    repetition_penalty=1.12,
    do_sample=True,
)

print(tokenizer.decode(outputs[0], skip_special_tokens=True))
