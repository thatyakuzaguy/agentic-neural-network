"""DeepSeek GGUF backend using llama-cpp-python."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.gpu_policy import require_gguf_gpu_offload

_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_THINK_BLOCK_PATTERN = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_TAG_PATTERN = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)


def clean_deepseek_output(text: str) -> str:
    """Remove DeepSeek reasoning tags and duplicated structured answers.

    Fenced Markdown code blocks are protected before cleanup so examples and generated code remain
    byte-for-byte intact.
    """

    protected_text, code_blocks = _protect_code_blocks(text)
    cleaned = _clean_non_code_text(protected_text).strip()
    cleaned = _remove_duplicated_structured_answer(cleaned).strip()
    return _restore_code_blocks(cleaned, code_blocks).strip()


class DeepSeekGGUFModel(BaseModelClient):
    """Run a local DeepSeek GGUF model through llama-cpp-python."""

    def __init__(self, config: PipelineConfig) -> None:
        if config.deepseek_gguf_path is None:
            raise RuntimeError("DEEPSEEK_GGUF_PATH is required and must point to a local GGUF file.")
        model_path = Path(config.deepseek_gguf_path)
        if not model_path.exists():
            raise RuntimeError(f"DeepSeek GGUF file does not exist: {model_path}")
        if config.require_gpu_for_llm:
            require_gguf_gpu_offload(config.deepseek_n_gpu_layers, "DeepSeek GGUF")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. Install it with: pip install llama-cpp-python"
            ) from exc

        self.config = config
        self.model_path = model_path
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=config.context_length,
            n_gpu_layers=config.deepseek_n_gpu_layers,
            main_gpu=config.deepseek_main_gpu,
            verbose=False,
        )
        print(f"Loaded model backend: {self.diagnostics()}")

    def generate_text(self, prompt: str) -> str:
        result = self._llm(
            prompt,
            max_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
        )
        return clean_deepseek_output(str(result["choices"][0]["text"]))

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        return self.generate_text(self._format_chat(messages))

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend_name": "deepseek",
            "loaded_backend_type": "gguf",
            "model_path": str(self.model_path),
            "device_mode": _gguf_device_mode(self.config.deepseek_n_gpu_layers),
            "cuda_available": _cuda_available(),
            "gpu_layers": self.config.deepseek_n_gpu_layers,
            "main_gpu": self.config.deepseek_main_gpu,
        }

    @staticmethod
    def _format_chat(messages: list[dict[str, str]]) -> str:
        formatted = []
        for message in messages:
            role = message.get("role", "user").upper()
            content = message.get("content", "")
            formatted.append(f"{role}:\n{content}")
        formatted.append("ASSISTANT:")
        return "\n\n".join(formatted)


def _protect_code_blocks(text: str) -> tuple[str, list[str]]:
    code_blocks: list[str] = []

    def replace(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"__AEN_CODE_BLOCK_{len(code_blocks) - 1}__"

    return _CODE_BLOCK_PATTERN.sub(replace, text), code_blocks


def _restore_code_blocks(text: str, code_blocks: list[str]) -> str:
    restored = text
    for index, block in enumerate(code_blocks):
        restored = restored.replace(f"__AEN_CODE_BLOCK_{index}__", block)
    return restored


def _clean_non_code_text(text: str) -> str:
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    text = _THINK_BLOCK_PATTERN.sub("", text)
    return _THINK_TAG_PATTERN.sub("", text)


def _remove_duplicated_structured_answer(text: str) -> str:
    lines = _trim_blank_lines(text.splitlines())
    if not lines:
        return ""

    duplicate = _find_repeated_line_block(lines)
    if duplicate is not None:
        return "\n".join(duplicate)

    duplicate = _dedupe_repeated_structured_sections(lines)
    return "\n".join(duplicate)


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _find_repeated_line_block(lines: list[str]) -> list[str] | None:
    for split_at in range(1, len(lines)):
        first = _trim_blank_lines(lines[:split_at])
        second = _trim_blank_lines(lines[split_at:])
        if first and _normalize_lines(first) == _normalize_lines(second):
            return second
    return None


def _dedupe_repeated_structured_sections(lines: list[str]) -> list[str]:
    section_starts = [
        index
        for index, line in enumerate(lines)
        if _is_structured_heading(line) and line.strip() in {_line.strip() for _line in lines[:index]}
    ]
    if not section_starts:
        return lines

    for start in section_starts:
        first = _trim_blank_lines(lines[:start])
        second = _trim_blank_lines(lines[start:])
        if first and _structured_heading_sequence(first) == _structured_heading_sequence(second):
            if _normalize_lines(first) == _normalize_lines(second):
                return second
    return lines


def _normalize_lines(lines: list[str]) -> list[str]:
    return [line.rstrip() for line in _trim_blank_lines(lines) if line.strip()]


def _structured_heading_sequence(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if _is_structured_heading(line)]


def _is_structured_heading(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped == stripped.upper() and re.fullmatch(r"[A-Z][A-Z0-9 /:-]*", stripped)


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
