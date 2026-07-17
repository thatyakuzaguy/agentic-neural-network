"""Controlled llama.cpp conversation inference bridge for ANN Terminal.

This script is intentionally narrow:
- reads one JSON request file;
- loads one declared GGUF model;
- generates one short assistant response;
- exits so the model is unloaded by process teardown.

It does not download, install packages, invoke a shell, modify models, write
adapters/datasets, or execute project commands.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one controlled ANN conversation inference.")
    parser.add_argument("--request-json", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    payload = _read_request(Path(args.request_json))
    model_path = _safe_model_path(str(payload.get("model_path_wsl") or ""))
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        _print({"status": "FAILED", "error": "prompt_required"})
        return 2

    _prepare_cuda_library_path()
    _preload_cuda_libraries()
    try:
        import llama_cpp
    except Exception as exc:  # pragma: no cover - depends on optional runtime.
        _print({"status": "FAILED", "error": f"llama_cpp_import_failed:{type(exc).__name__}:{exc}"})
        return 3

    n_gpu_layers = int(payload.get("n_gpu_layers", -1))
    require_gpu = bool(payload.get("require_gpu", True))
    gpu_ready, gpu_reason = _gpu_runtime_ready(llama_cpp, n_gpu_layers)
    if require_gpu and not gpu_ready:
        _print(
            {
                "status": "FAILED",
                "error": "gpu_required_but_unavailable",
                "gpu_reason": gpu_reason,
                "gpu_required": True,
                "n_gpu_layers": n_gpu_layers,
                "active_models_after": 0,
                "parallel_llm_loads_after": 0,
                "safe_mode_final": True,
            }
        )
        return 6

    llm: Any | None = None
    try:
        load_started = time.perf_counter()
        llm = llama_cpp.Llama(
            model_path=str(model_path),
            n_ctx=int(payload.get("context_tokens") or 2048),
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        load_seconds = time.perf_counter() - load_started

        inference_started = time.perf_counter()
        result = llm(
            prompt,
            max_tokens=int(payload.get("max_tokens") or 160),
            temperature=float(payload.get("temperature") or 0.2),
            stop=["</s>", "<|im_end|>", "<|endoftext|>"],
        )
        inference_seconds = time.perf_counter() - inference_started
        text = _clean_model_text(_extract_text(result))
        usage = result.get("usage", {}) if isinstance(result, dict) else {}
        _print(
            {
                "status": "PASSED" if text else "FAILED",
                "text": text,
                "model_path": str(model_path),
                "load_time_seconds": round(load_seconds, 3),
                "inference_time_seconds": round(inference_seconds, 3),
                "total_time_seconds": round(time.perf_counter() - started, 3),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "tokens_generated": int(usage.get("completion_tokens") or 0),
                "gpu_required": require_gpu,
                "gpu_ready": gpu_ready,
                "gpu_reason": gpu_reason,
                "n_gpu_layers": n_gpu_layers,
                "active_models_after": 0,
                "parallel_llm_loads_after": 0,
                "safe_mode_final": True,
            }
        )
        return 0 if text else 4
    except Exception as exc:  # pragma: no cover - depends on model/backend state.
        _print(
            {
                "status": "FAILED",
                "error": f"{type(exc).__name__}:{exc}",
                "active_models_after": 0,
                "parallel_llm_loads_after": 0,
                "safe_mode_final": True,
            }
        )
        return 5
    finally:
        if llm is not None:
            del llm
        gc.collect()


def _read_request(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if any(part.lower() in {".git", "models", "training", "datasets", "adapters", "memory", "knowledge"} for part in resolved.parts):
        raise ValueError("request_path_protected")
    return json.loads(resolved.read_text(encoding="utf-8"))


def _safe_model_path(raw_path: str) -> Path:
    posix = PurePosixPath(raw_path)
    if not raw_path.startswith("/mnt/d/") and not raw_path.startswith("/mnt/e/"):
        raise ValueError("model_path_must_be_under_mnt_d_or_mnt_e")
    if ".." in posix.parts:
        raise ValueError("model_path_traversal_blocked")
    path = Path(raw_path)
    if not path.is_file():
        raise FileNotFoundError(raw_path)
    return path


def _prepare_cuda_library_path() -> None:
    """Expose bundled nvidia Python wheel libraries to llama.cpp if present."""

    prefix = Path(sys.prefix)
    nvidia_root = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "nvidia"
    candidates = [
        nvidia_root / "cuda_runtime" / "lib",
        nvidia_root / "cublas" / "lib",
        nvidia_root / "cuda_nvrtc" / "lib",
        nvidia_root / "cuda_cupti" / "lib",
    ]
    existing = [str(path) for path in candidates if path.is_dir()]
    if not existing:
        return
    current = os.environ.get("LD_LIBRARY_PATH", "")
    pieces = existing + ([current] if current else [])
    os.environ["LD_LIBRARY_PATH"] = ":".join(pieces)


def _preload_cuda_libraries() -> None:
    prefix = Path(sys.prefix)
    nvidia_root = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "nvidia"
    libraries = [
        nvidia_root / "cuda_runtime" / "lib" / "libcudart.so.12",
        nvidia_root / "cublas" / "lib" / "libcublasLt.so.12",
        nvidia_root / "cublas" / "lib" / "libcublas.so.12",
    ]
    for library in libraries:
        if library.is_file():
            ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)


def _gpu_runtime_ready(llama_cpp_module: object, n_gpu_layers: int) -> tuple[bool, str]:
    if n_gpu_layers == 0:
        return False, "n_gpu_layers_zero_cpu_mode"

    supports_offload = getattr(llama_cpp_module, "LLAMA_SUPPORTS_GPU_OFFLOAD", None)
    if supports_offload is False:
        return False, "llama_cpp_gpu_offload_not_supported"

    try:
        import torch
    except Exception:
        return (True, "llama_cpp_gpu_offload_supported") if supports_offload else (
            False,
            "torch_cuda_unavailable_and_llama_cpp_gpu_support_unknown",
        )

    cuda = getattr(torch, "cuda", None)
    if cuda is not None and bool(cuda.is_available()):
        return True, "torch_cuda_available"
    return (True, "llama_cpp_gpu_offload_supported") if supports_offload else (
        False,
        "torch_cuda_unavailable",
    )


def _extract_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("text") or "").strip()


def _clean_model_text(text: str) -> str:
    cleaned = text.strip()
    while "<think>" in cleaned and "</think>" in cleaned:
        start = cleaned.find("<think>")
        end = cleaned.find("</think>", start) + len("</think>")
        cleaned = (cleaned[:start] + cleaned[end:]).strip()
    cleaned = cleaned.replace("<think>", "").replace("</think>", "").strip()
    cleaned = cleaned.lstrip("`'\" .\n\r\t")
    if cleaned.lower().startswith("okay,") or cleaned.lower().startswith("the user"):
        return ""
    return cleaned


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
