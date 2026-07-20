"""In-process llama.cpp backend for local GPU-only GGUF inference."""

from __future__ import annotations

import gc
import importlib
import importlib.util
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload
from agentic_network.models.llama_cpp_security import load_secure_llama_cpp
from agentic_network.runtime_engine.backends.base import (
    BackendGenerateResult,
    BackendHealthResult,
    BackendLoadResult,
    BackendUnloadResult,
)
from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths


class LlamaCppBackend:
    """Load one inventory-declared GGUF model through llama-cpp-python."""

    name = "llama_cpp"

    def __init__(self, policy: dict[str, Any] | None = None, *, binding: Any | None = None) -> None:
        self.policy = dict(policy or {})
        self._binding = binding
        self._model: Any | None = None
        self._model_name: str | None = None
        self._model_record: Any | None = None
        self.binding_available = binding is not None or _binding_is_available()

    def load_model(self, model_name: str) -> BackendLoadResult:
        clean_name = model_name.strip()
        if not self.policy.get("allow_real_model_load", False):
            return self._load_result(
                "BLOCKED",
                clean_name,
                errors=["llama_cpp_real_model_load_blocked_by_policy"],
                warnings=["No GGUF file was opened."],
            )
        if self._model is not None:
            if self._model_name == clean_name:
                return self._load_result(
                    "LOADED",
                    clean_name,
                    loaded=True,
                    warnings=["llama_cpp_model_already_loaded"],
                )
            return self._load_result(
                "BLOCKED",
                clean_name,
                errors=[f"llama_cpp_model_already_active:{self._model_name}"],
            )

        record = _resolve_model_record(clean_name)
        validation_errors = _validate_record(record, clean_name)
        if validation_errors:
            status = "UNAVAILABLE" if record is None or "model_path_missing" in validation_errors else "BLOCKED"
            return self._load_result(status, clean_name, errors=validation_errors)

        n_gpu_layers = int(getattr(record, "n_gpu_layers", -1))
        if n_gpu_layers == 0:
            return self._load_result(
                "BLOCKED",
                clean_name,
                errors=["llama_cpp_gpu_offload_required:n_gpu_layers_must_not_be_0"],
            )

        try:
            binding = self._load_binding()
        except (ImportError, OSError, RuntimeError) as exc:
            return self._load_result(
                "UNAVAILABLE",
                clean_name,
                errors=["llama_cpp_binding_unavailable", _exception_error("llama_cpp_import_failed", exc)],
            )
        if llama_cpp_supports_gpu_offload(binding) is not True:
            return self._load_result(
                "UNAVAILABLE",
                clean_name,
                errors=["llama_cpp_native_gpu_offload_required"],
                warnings=["CPU inference and unknown GPU-offload capability are rejected."],
            )

        llama_factory = getattr(binding, "Llama", None)
        if not callable(llama_factory):
            return self._load_result(
                "UNAVAILABLE",
                clean_name,
                errors=["llama_cpp_Llama_class_unavailable"],
            )

        try:
            model = llama_factory(
                model_path=str(Path(record.path)),
                n_ctx=max(1, int(getattr(record, "context_tokens", 4096))),
                n_gpu_layers=n_gpu_layers,
                main_gpu=max(0, int(getattr(record, "main_gpu", 0))),
                verbose=False,
            )
        except Exception as exc:
            return self._load_result(
                "FAILED",
                clean_name,
                errors=[_exception_error("llama_cpp_model_load_failed", exc)],
            )

        self._model = model
        self._model_name = clean_name
        self._model_record = record
        return self._load_result("LOADED", clean_name, loaded=True)

    def generate(
        self,
        model_name: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> BackendGenerateResult:
        started = perf_counter()
        clean_name = model_name.strip()
        if self._model is None or self._model_name != clean_name:
            return BackendGenerateResult(
                status="BLOCKED",
                model_name=clean_name,
                backend=self.name,
                text="",
                tokens_in=len(prompt.split()),
                tokens_out=0,
                duration_ms=_elapsed_ms(started),
                errors=["llama_cpp_generate_requires_loaded_model"],
                warnings=[],
            )

        settings = _generation_settings(self._model_record, options)
        try:
            create_chat_completion = getattr(self._model, "create_chat_completion", None)
            if callable(create_chat_completion):
                response = create_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    **settings,
                )
            else:
                response = self._model(prompt, **settings)
            text, tokens_in, tokens_out = _parse_completion(response, prompt)
        except Exception as exc:
            return BackendGenerateResult(
                status="FAILED",
                model_name=clean_name,
                backend=self.name,
                text="",
                tokens_in=len(prompt.split()),
                tokens_out=0,
                duration_ms=_elapsed_ms(started),
                errors=[_exception_error("llama_cpp_generation_failed", exc)],
                warnings=[],
            )

        generation_errors = [] if text else ["llama_cpp_empty_output_after_reasoning_cleanup"]
        return BackendGenerateResult(
            status="SUCCESS" if text else "FAILED",
            model_name=clean_name,
            backend=self.name,
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=_elapsed_ms(started),
            errors=generation_errors,
            warnings=[],
        )

    def unload_model(self, model_name: str) -> BackendUnloadResult:
        clean_name = model_name.strip()
        model = self._model
        loaded_name = self._model_name
        self._model = None
        self._model_name = None
        self._model_record = None
        if model is None:
            return BackendUnloadResult(
                status="UNLOADED",
                model_name=clean_name,
                backend=self.name,
                unloaded=True,
                errors=[],
                warnings=["No llama.cpp model was loaded."],
            )

        warnings = [] if loaded_name == clean_name else [f"unloaded_active_model:{loaded_name}"]
        errors: list[str] = []
        close = getattr(model, "close", None)
        try:
            if callable(close):
                close()
        except Exception as exc:
            errors.append(_exception_error("llama_cpp_model_close_failed", exc))
        finally:
            del model
            gc.collect()
        return BackendUnloadResult(
            status="UNLOADED" if not errors else "FAILED",
            model_name=clean_name,
            backend=self.name,
            unloaded=not errors,
            errors=errors,
            warnings=warnings,
        )

    def health_check(self) -> BackendHealthResult:
        if not self.policy.get("allow_real_model_load", False):
            return BackendHealthResult(
                status="BLOCKED_BY_POLICY",
                backend=self.name,
                available=False,
                errors=["real_model_load_blocked_by_policy"],
                warnings=["llama.cpp backend is present but real load is disabled."],
            )
        try:
            binding = self._load_binding()
        except (ImportError, OSError, RuntimeError) as exc:
            return BackendHealthResult(
                status="UNAVAILABLE",
                backend=self.name,
                available=False,
                errors=["llama_cpp_binding_unavailable", _exception_error("llama_cpp_import_failed", exc)],
                warnings=[],
            )
        if not callable(getattr(binding, "Llama", None)):
            return BackendHealthResult(
                status="UNAVAILABLE",
                backend=self.name,
                available=False,
                errors=["llama_cpp_Llama_class_unavailable"],
                warnings=[],
            )
        if llama_cpp_supports_gpu_offload(binding) is not True:
            return BackendHealthResult(
                status="GPU_UNAVAILABLE",
                backend=self.name,
                available=False,
                errors=["llama_cpp_native_gpu_offload_required"],
                warnings=["CPU inference and unknown GPU-offload capability are rejected."],
            )
        return BackendHealthResult(
            status="AVAILABLE",
            backend=self.name,
            available=True,
            errors=[],
            warnings=[],
        )

    def _load_binding(self) -> Any:
        if self._binding is None:
            configure_windows_runtime_dll_paths()
            self._binding = load_secure_llama_cpp()
            self.binding_available = True
        return self._binding

    def _load_result(
        self,
        status: str,
        model_name: str,
        *,
        loaded: bool = False,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> BackendLoadResult:
        return BackendLoadResult(
            status=status,
            model_name=model_name,
            backend=self.name,
            loaded=loaded,
            errors=list(errors or []),
            warnings=list(warnings or []),
        )


def _binding_is_available() -> bool:
    if "llama_cpp" in sys.modules:
        return True
    try:
        return importlib.util.find_spec("llama_cpp") is not None
    except (ImportError, ValueError):
        return False


def _resolve_model_record(model_name: str) -> Any | None:
    from agentic_network.runtime_engine.model_inventory import resolve_model_record

    return resolve_model_record(model_name)


def _validate_record(record: Any | None, model_name: str) -> list[str]:
    if record is None:
        return [f"llama_cpp_inventory_model_not_found:{model_name}"]
    errors: list[str] = []
    if not bool(getattr(record, "enabled", False)):
        errors.append("llama_cpp_inventory_model_disabled")
    if str(getattr(record, "backend", "")).strip().lower() != "llama_cpp":
        errors.append("llama_cpp_inventory_backend_mismatch")
    model_path = Path(str(getattr(record, "path", "")))
    if not model_path.is_file():
        errors.append("model_path_missing")
    elif model_path.suffix.lower() != ".gguf":
        errors.append("llama_cpp_model_must_be_gguf")
    return errors


def _generation_settings(record: Any, options: dict[str, Any] | None) -> dict[str, Any]:
    requested = options or {}
    max_tokens = int(requested.get("max_tokens", getattr(record, "max_tokens", 768)))
    temperature = float(requested.get("temperature", getattr(record, "temperature", 0.2)))
    settings: dict[str, Any] = {
        "max_tokens": max(1, min(max_tokens, 8192)),
        "temperature": max(0.0, min(temperature, 2.0)),
        "top_p": max(0.0, min(float(requested.get("top_p", 0.95)), 1.0)),
    }
    stop = requested.get("stop")
    if isinstance(stop, str):
        settings["stop"] = [stop]
    elif isinstance(stop, list) and all(isinstance(item, str) for item in stop):
        settings["stop"] = stop
    return settings


def _parse_completion(response: Any, prompt: str) -> tuple[str, int, int]:
    if not isinstance(response, dict):
        raise TypeError("llama_cpp_completion_response_must_be_a_mapping")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("llama_cpp_completion_choices_missing")
    first = choices[0]
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    text = _clean_completion_text(str(message.get("content") or first.get("text") or ""))
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    tokens_in = int(usage.get("prompt_tokens") or len(prompt.split()))
    tokens_out = int(usage.get("completion_tokens") or len(text.split()))
    return text, tokens_in, tokens_out


def _clean_completion_text(text: str) -> str:
    from agentic_network.models.deepseek_gguf import clean_deepseek_output

    cleaned = clean_deepseek_output(text)
    for token in ("<|im_end|>", "<|endoftext|>", "</s>"):
        cleaned = cleaned.split(token, maxsplit=1)[0]
    return cleaned.strip()


def _exception_error(prefix: str, exc: Exception) -> str:
    detail = str(exc).strip()
    return f"{prefix}:{type(exc).__name__}" + (f":{detail}" if detail else "")


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))
