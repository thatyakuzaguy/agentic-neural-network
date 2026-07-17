from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from agentic_engineering_network.shared.config import Settings, ensure_inside_root


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    content: str


class AIProvider:
    name = "base"

    def generate(self, prompt: Prompt) -> ProviderResponse:
        raise NotImplementedError


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: Prompt) -> ProviderResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "prompt": f"{prompt.system}\n\nUser request:\n{prompt.user}",
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc
        return ProviderResponse(provider=self.name, model=self.model, content=body.get("response", ""))


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def generate(self, prompt: Prompt) -> ProviderResponse:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc
        text = ""
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text += content.get("text", "")
        return ProviderResponse(provider=self.name, model=self.model, content=text)


class LlamaCppProvider(AIProvider):
    name = "llama_cpp"

    def __init__(
        self,
        model_path: Path,
        context_size: int,
        max_tokens: int,
        temperature: float,
        gpu_layers: int,
        main_gpu: int,
    ) -> None:
        self.model_path = ensure_inside_root(model_path)
        self.model = self.model_path.name
        self.context_size = context_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.gpu_layers = gpu_layers
        self.main_gpu = main_gpu
        self._llm: object | None = None

    def _load(self) -> object:
        if not self.model_path.exists():
            raise RuntimeError(f"Local GGUF model not found: {self.model_path}")
        if self.gpu_layers == 0:
            raise RuntimeError(
                "LOCAL_MODEL_GPU_LAYERS=0 forces CPU inference. ANN local GGUF providers "
                "require GPU offload; use -1 or a positive layer count."
            )
        if self._llm is None:
            try:
                import llama_cpp
            except ImportError as exc:
                raise RuntimeError(
                    "llama-cpp-python is not installed. Run setup.ps1 or rebuild the API image."
                ) from exc
            if getattr(llama_cpp, "LLAMA_SUPPORTS_GPU_OFFLOAD", True) is False:
                raise RuntimeError("llama-cpp-python was built without GPU offload support.")
            self._llm = llama_cpp.Llama(
                model_path=str(self.model_path),
                n_ctx=self.context_size,
                n_threads=max(1, (os.cpu_count() or 4) - 1),
                n_gpu_layers=self.gpu_layers,
                main_gpu=self.main_gpu,
                verbose=False,
            )
        return self._llm

    def generate(self, prompt: Prompt) -> ProviderResponse:
        llm = self._load()
        text_prompt = (
            "<|im_start|>system\n"
            f"{prompt.system}\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"{prompt.user}\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        result = llm(  # type: ignore[operator]
            text_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=["<|im_end|>", "<|im_start|>"],
        )
        content = str(result["choices"][0]["text"]).strip()
        return ProviderResponse(provider=self.name, model=self.model, content=content)


class DeterministicLocalProvider(AIProvider):
    name = "deterministic-local"

    def generate(self, prompt: Prompt) -> ProviderResponse:
        idea = prompt.user.strip().replace("\n", " ")
        content = (
            "Decision: proceed with a secure, approval-gated full-stack architecture.\n"
            f"Rationale: the request '{idea[:160]}' requires product discovery, modular services, "
            "tests, docs, Docker packaging, and auditability before any generated file is committed."
        )
        return ProviderResponse(provider=self.name, model="rules-engine", content=content)


def build_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider in {"llama_cpp", "local_gguf", "qwen_direct"}:
        return LlamaCppProvider(
            settings.local_model_path,
            settings.local_model_context,
            settings.local_model_max_tokens,
            settings.local_model_temperature,
            settings.local_model_gpu_layers,
            settings.local_model_main_gpu,
        )
    if settings.ai_provider == "openai":
        return OpenAIProvider(settings.openai_model)
    if settings.ai_provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    return DeterministicLocalProvider()
