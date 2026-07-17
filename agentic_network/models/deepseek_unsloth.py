"""DeepSeek Unsloth backend for local GPU-first inference."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output
from agentic_network.models.gpu_policy import require_cuda_available


class DeepSeekUnslothModel(BaseModelClient):
    """Run a local DeepSeek-R1-Distill-Qwen checkpoint through Unsloth."""

    _cache: ClassVar[dict[tuple[str, int, bool], tuple[object, object, object]]] = {}

    def __init__(self, config: PipelineConfig) -> None:
        model_path = Path(config.deepseek_unsloth_model)
        if not model_path.exists():
            raise RuntimeError(f"DeepSeek Unsloth model path does not exist: {model_path}")

        try:
            import torch
            from unsloth import FastLanguageModel
        except ImportError as exc:
            raise RuntimeError("Unsloth is not installed or not available in this environment.") from exc

        self.config = config
        self.model_path = model_path
        self._torch = torch
        self._cuda_available = bool(torch.cuda.is_available())
        if config.require_gpu_for_llm:
            require_cuda_available(torch, "DeepSeek Unsloth")
        cache_key = (
            str(model_path.resolve()),
            config.deepseek_unsloth_max_seq_length,
            config.deepseek_unsloth_load_in_4bit,
        )
        if cache_key not in self._cache:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=str(model_path),
                max_seq_length=config.deepseek_unsloth_max_seq_length,
                dtype=None,
                load_in_4bit=config.deepseek_unsloth_load_in_4bit,
                local_files_only=True,
            )
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
                max_new_tokens=self.config.deepseek_unsloth_max_new_tokens,
                temperature=self.config.deepseek_unsloth_temperature,
                top_p=self.config.deepseek_unsloth_top_p,
                do_sample=self.config.deepseek_unsloth_temperature > 0,
                pad_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0][inputs.shape[-1] :]
        return clean_deepseek_output(
            str(tokenizer.decode(new_tokens, skip_special_tokens=True))
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend_name": "deepseek_unsloth",
            "loaded_backend_type": "unsloth",
            "model_path": str(self.model_path),
            "device": str(self._device),
            "device_mode": str(self._device),
            "cuda_available": self._cuda_available,
            "load_in_4bit": self.config.deepseek_unsloth_load_in_4bit,
            "max_seq_length": self.config.deepseek_unsloth_max_seq_length,
            "gpu_layers": None,
            "main_gpu": None,
        }
