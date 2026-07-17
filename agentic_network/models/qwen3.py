"""Qwen3 local backends for GGUF and Transformers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.gpu_policy import (
    require_cuda_available,
    require_gguf_gpu_offload,
)

_QWEN3_HF_MISSING_MESSAGE = (
    "Qwen3 model is not available locally. Set QWEN3_BASE_MODEL to a local path or "
    "pre-cache it. Do not auto-download models."
)
_QWEN3_GGUF_MISSING_TEMPLATE = (
    "Qwen3 GGUF file does not exist: {path}. Set QWEN3_GGUF_PATH to a local Qwen3 GGUF "
    "file under /mnt/d/Models/qwen3. Do not auto-download models."
)
QWEN3_GGUF_STOP_SEQUENCES = ("<|im_end|>", "</s>", "Okay, let me", "Wait,", "I think")
PRODUCT_SECTION_TITLES = (
    "REQUIREMENTS",
    "AMBIGUITIES",
    "ASSUMPTIONS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "CONFIDENCE",
)
PRODUCT_SECTION_BULLET_LIMITS = {
    "REQUIREMENTS": 7,
    "AMBIGUITIES": 5,
    "ASSUMPTIONS": 5,
    "ACCEPTANCE CRITERIA": 7,
    "RISKS": 5,
    "CONFIDENCE": 1,
}
_PRODUCT_SECTION_PATTERN = re.compile(
    r"^(REQUIREMENTS|AMBIGUITIES|ASSUMPTIONS|ACCEPTANCE CRITERIA|RISKS|CONFIDENCE)\s*$",
    re.MULTILINE,
)
_REASONING_PATTERNS = (
    re.compile(r"^\s*Okay,\s+let\s+me\b.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Wait,\b.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*I\s+think\b.*$", re.IGNORECASE | re.MULTILINE),
)


class Qwen3Model(BaseModelClient):
    """Run Qwen3 through GGUF when configured, otherwise through local Transformers."""

    def __init__(self, config: PipelineConfig) -> None:
        if config.qwen3_gguf_path is not None:
            self.runtime = "gguf"
            self._backend: BaseModelClient = Qwen3GGUFModel(config)
        else:
            self.runtime = "hf"
            self._backend = Qwen3HFModel(config)

    def generate_text(self, prompt: str) -> str:
        try:
            return self._backend.generate_text(prompt)
        except Exception as exc:
            print(f"Qwen3 generation failed: {_format_exception(exc)}")
            raise

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        try:
            return self._backend.generate_chat(messages)
        except Exception as exc:
            print(f"Qwen3 generation failed: {_format_exception(exc)}")
            raise

    def diagnostics(self) -> dict[str, object]:
        diagnostics = self._backend.diagnostics()
        return {
            **diagnostics,
            "backend_name": "qwen3",
            "loaded_backend_type": f"qwen3_{self.runtime}",
        }


class Qwen3GGUFModel(BaseModelClient):
    """Run a local Qwen3 GGUF model through llama-cpp-python."""

    _cache: ClassVar[dict[tuple[str, int, int, int], object]] = {}

    def __init__(self, config: PipelineConfig) -> None:
        if config.qwen3_gguf_path is None:
            raise RuntimeError("QWEN3_GGUF_PATH is required for the Qwen3 GGUF backend.")
        model_path = Path(config.qwen3_gguf_path)
        if not model_path.exists():
            raise RuntimeError(_QWEN3_GGUF_MISSING_TEMPLATE.format(path=model_path))
        if config.require_gpu_for_llm:
            require_gguf_gpu_offload(config.qwen3_n_gpu_layers, "Qwen3 GGUF")

        Llama = _load_llama_class()
        self.config = config
        self.model_path = model_path
        cache_key = (
            str(model_path.resolve()),
            config.context_length,
            config.qwen3_n_gpu_layers,
            config.qwen3_main_gpu,
        )
        if cache_key not in self._cache:
            self._cache[cache_key] = Llama(
                model_path=str(model_path),
                n_ctx=config.context_length,
                n_gpu_layers=config.qwen3_n_gpu_layers,
                main_gpu=config.qwen3_main_gpu,
                verbose=False,
            )
        self._llm = self._cache[cache_key]
        print(f"Loaded model backend: {self.diagnostics()}")

    def generate_text(self, prompt: str) -> str:
        result = self._llm(
            prompt,
            max_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            stop=list(QWEN3_GGUF_STOP_SEQUENCES),
        )
        return str(result["choices"][0]["text"]).strip()

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        return self.generate_text(_format_chat(messages))

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend_name": "qwen3",
            "loaded_backend_type": "qwen3_gguf",
            "model_path": str(self.model_path),
            "device_mode": _gguf_device_mode(self.config.qwen3_n_gpu_layers),
            "cuda_available": _cuda_available(),
            "gpu_layers": self.config.qwen3_n_gpu_layers,
            "main_gpu": self.config.qwen3_main_gpu,
        }


class Qwen3HFModel(BaseModelClient):
    """Run a locally available Qwen3 instruct model through Transformers."""

    _cache: ClassVar[dict[tuple[str, int, bool], tuple[object, object, object, bool]]] = {}

    def __init__(self, config: PipelineConfig) -> None:
        torch, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig = (
            _load_transformers_classes()
        )

        self.config = config
        self._torch = torch
        cuda_available = bool(torch.cuda.is_available())
        if config.require_gpu_for_llm:
            require_cuda_available(torch, "Qwen3 HF")
        cache_key = (config.qwen3_base_model, config.context_length, config.use_4bit)
        if cache_key not in self._cache:
            device = torch.device("cuda" if cuda_available else "cpu")
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    config.qwen3_base_model,
                    local_files_only=True,
                )
                model_kwargs: dict[str, object] = {"local_files_only": True}
                if cuda_available:
                    model_kwargs["device_map"] = "auto"
                if config.use_4bit:
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                    )
                else:
                    model_kwargs["torch_dtype"] = (
                        torch.float16 if cuda_available else torch.float32
                    )
                model = AutoModelForCausalLM.from_pretrained(
                    config.qwen3_base_model,
                    **model_kwargs,
                )
            except OSError as exc:
                raise RuntimeError(_QWEN3_HF_MISSING_MESSAGE) from exc
            except RuntimeError as exc:
                raise RuntimeError(
                    "Qwen3 HF model failed to load locally. If this is a CUDA out-of-memory "
                    "error, use QWEN3_GGUF_PATH or reduce model size/precision. Original error: "
                    f"{exc}"
                ) from exc

            if not cuda_available and hasattr(model, "to"):
                model.to(device)
            if hasattr(model, "eval"):
                model.eval()
            self._cache[cache_key] = (model, tokenizer, device, cuda_available)

        self._model, self._tokenizer, self._device, self._cuda_available = self._cache[cache_key]
        print(f"Loaded model backend: {self.diagnostics()}")

    def generate_text(self, prompt: str) -> str:
        return self.generate_chat([{"role": "user", "content": prompt}])

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        tokenizer = self._tokenizer
        model = self._model
        prompt = self._format_messages(messages)
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.config.context_length,
        )
        inputs = _move_tokenizer_inputs(inputs, self._model_device())
        input_ids = inputs["input_ids"]

        with self._torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                do_sample=self.config.temperature > 0,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0][input_ids.shape[-1] :]
        return str(tokenizer.decode(new_tokens, skip_special_tokens=True)).strip()

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        tokenizer = self._tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return _format_chat(messages)

    def _model_device(self) -> object:
        return getattr(self._model, "device", self._device)

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend_name": "qwen3",
            "loaded_backend_type": "qwen3_hf",
            "model_path": self.config.qwen3_base_model,
            "device_mode": "cuda_device_map_auto" if self._cuda_available else "cpu",
            "cuda_available": self._cuda_available,
            "gpu_layers": None,
            "main_gpu": None,
        }


def _format_chat(messages: list[dict[str, str]]) -> str:
    formatted = []
    for message in messages:
        role = message.get("role", "user").upper()
        content = message.get("content", "")
        formatted.append(f"{role}:\n{content}")
    formatted.append("ASSISTANT:")
    return "\n\n".join(formatted)


def _move_tokenizer_inputs(inputs: object, device: object) -> object:
    if hasattr(inputs, "to"):
        return inputs.to(device)
    if isinstance(inputs, dict):
        return {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
    return inputs


def _load_llama_class() -> object:
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise RuntimeError(
            "llama-cpp-python is required for the Qwen3 GGUF backend."
        ) from exc
    return Llama


def _load_transformers_classes() -> tuple[object, object, object, object]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise RuntimeError("Transformers and torch are required for the Qwen3 HF backend.") from exc
    return torch, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def clean_qwen3_product_output(text: str) -> str:
    """Keep the first concise Product Agent answer from noisy Qwen3 output."""

    cleaned = text.replace("```", "")
    for pattern in _REASONING_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = _remove_until_first_product_section(cleaned)
    sections = _extract_first_product_sections(cleaned)
    return "\n\n".join(_format_product_section(title, body) for title, body in sections).strip()


def _remove_until_first_product_section(text: str) -> str:
    match = _PRODUCT_SECTION_PATTERN.search(text)
    if match is None:
        return text.strip()
    return text[match.start() :].strip()


def _extract_first_product_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_PRODUCT_SECTION_PATTERN.finditer(text))
    sections: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        title = match.group(1)
        if title in seen:
            if title == PRODUCT_SECTION_TITLES[0]:
                break
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((title, text[start:end].strip()))
        seen.add(title)
        if len(seen) == len(PRODUCT_SECTION_TITLES):
            break
    by_title = {title: body for title, body in sections}
    return [(title, by_title.get(title, "")) for title in PRODUCT_SECTION_TITLES if title in by_title]


def _format_product_section(title: str, body: str) -> str:
    bullets = _section_bullets(title, body)
    if not bullets:
        bullets = ["- Medium" if title == "CONFIDENCE" else "- None."]
    return "\n".join([title, *bullets])


def _section_bullets(title: str, body: str) -> list[str]:
    limit = PRODUCT_SECTION_BULLET_LIMITS[title]
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == stripped.upper() and stripped in PRODUCT_SECTION_TITLES:
            break
        if stripped.startswith(("-", "*")):
            bullet = f"- {stripped[1:].strip()}"
        else:
            bullet = f"- {stripped}"
        bullets.append(bullet)
        if len(bullets) == limit:
            break
    return bullets


def _format_exception(exc: Exception) -> str:
    message = str(exc) or "<no message>"
    return f"{type(exc).__name__}: {message}"


def _gguf_device_mode(n_gpu_layers: int) -> str:
    if n_gpu_layers == 0:
        return "cpu"
    if n_gpu_layers == -1:
        return "gpu_all_possible_layers"
    return f"gpu_{n_gpu_layers}_layers"


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    cuda: Any = getattr(torch, "cuda", None)
    return bool(cuda is not None and cuda.is_available())
