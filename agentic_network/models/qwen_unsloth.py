"""Qwen Unsloth adapter backend."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.gpu_policy import require_cuda_available


class QwenUnslothModel(BaseModelClient):
    """Run Qwen2.5-Coder with the local Python Expert v5 adapter."""

    _cache: ClassVar[dict[tuple[str, str, int, bool], tuple[object, object, object]]] = {}

    def __init__(self, config: PipelineConfig) -> None:
        adapter_path = Path(config.qwen_adapter_path)
        if not adapter_path.exists():
            raise RuntimeError(f"Qwen adapter path does not exist: {adapter_path}")

        try:
            import torch
            from unsloth import FastLanguageModel
        except ImportError as exc:
            raise RuntimeError("Unsloth is not installed or not available in this environment.") from exc

        self.config = config
        self.adapter_path = adapter_path
        self._torch = torch
        self._cuda_available = bool(torch.cuda.is_available())
        if config.require_gpu_for_llm:
            require_cuda_available(torch, "Qwen2.5 Unsloth")
        cache_key = (
            config.qwen_base_model,
            str(adapter_path.resolve()),
            config.context_length,
            config.use_4bit,
        )
        if cache_key not in self._cache:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=config.qwen_base_model,
                max_seq_length=config.context_length,
                dtype=None,
                load_in_4bit=config.use_4bit,
                local_files_only=True,
            )
            model.load_adapter(str(adapter_path), adapter_name="python_expert_v5")
            model.set_adapter("python_expert_v5")
            FastLanguageModel.for_inference(model)
            device = torch.device("cuda" if self._cuda_available else "cpu")
            if hasattr(model, "to"):
                model.to(device)
            self._cache[cache_key] = (model, tokenizer, device)

        self._model, self._tokenizer, self._device = self._cache[cache_key]
        print(f"Loaded model backend: {self.diagnostics()}")

    def generate_text(self, prompt: str) -> str:
        return self.generate_chat([{"role": "user", "content": prompt}])

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        tokenizer = self._tokenizer
        model = self._model
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self._device)
        with self._torch.inference_mode():
            generated = model.generate(
                input_ids=inputs,
                max_new_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                do_sample=self.config.temperature > 0,
                pad_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0][inputs.shape[-1] :]
        return str(tokenizer.decode(new_tokens, skip_special_tokens=True)).strip()

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend_name": "qwen_v5",
            "loaded_backend_type": "unsloth",
            "model_path": self.config.qwen_base_model,
            "adapter_path": str(self.adapter_path),
            "device_mode": str(self._device),
            "cuda_available": self._cuda_available,
            "gpu_layers": None,
            "main_gpu": None,
        }
