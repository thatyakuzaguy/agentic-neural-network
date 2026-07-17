from unsloth import FastLanguageModel
from transformers import TextStreamer

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER = "training/adapters/qwen-7b-principal-v2"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=4096,
    load_in_4bit=True,
)

model.load_adapter(ADAPTER)

FastLanguageModel.for_inference(model)

messages = [
    {
        "role": "system",
        "content": (
            "You are a Principal Software Architect. "
            "Do not write tutorials or code snippets unless requested. "
            "Use concise architecture decision format. "
            "Always include: executive summary, bounded contexts, ADRs, tradeoffs, "
            "risk register, security gates, compliance readiness, QA strategy, "
            "observability, release gates, and human approvals."
        )
    },
    {
        "role": "user",
        "content": (
            "Design a production-ready multi-tenant SaaS CRM "
            "using Next.js, FastAPI, PostgreSQL, Docker, "
            "Kubernetes, GitHub Actions, RBAC, audit logs, "
            "security review gates, compliance readiness "
            "and release approval workflows."
        )
    }
]

prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)

inputs = tokenizer(
    prompt,
    return_tensors="pt"
).to("cuda")

streamer = TextStreamer(tokenizer)

model.generate(
    **inputs,
    streamer=streamer,
    max_new_tokens=1200,
    temperature=0.2,
    top_p=0.85,
    repetition_penalty=1.12,
    do_sample=True,
)
