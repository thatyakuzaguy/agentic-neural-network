"""Read-only llama.cpp Python binding check for ANN.

This script never instantiates Llama and never loads a GGUF file. It only
checks importability, metadata, and the declared Qwen2.5 model path.
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path


QWEN25_GGUF = Path("D:/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf")


def main() -> None:
    payload = {
        "script": "check_llama_cpp_cuda",
        "read_only": True,
        "installs": False,
        "downloads": False,
        "model_load": False,
        "qwen25_gguf_path": str(QWEN25_GGUF),
        "qwen25_gguf_exists": QWEN25_GGUF.is_file(),
    }
    try:
        import llama_cpp

        try:
            version = importlib.metadata.version("llama-cpp-python")
        except importlib.metadata.PackageNotFoundError:
            version = None
        payload.update(
            {
                "status": "available",
                "llama_cpp_importable": True,
                "llama_cpp_version": version,
                "llama_class_available": hasattr(llama_cpp, "Llama"),
                "gpu_offload_metadata": getattr(llama_cpp, "LLAMA_SUPPORTS_GPU_OFFLOAD", None),
            }
        )
    except Exception as exc:  # pragma: no cover - depends on optional runtime.
        payload.update(
            {
                "status": "unavailable",
                "llama_cpp_importable": False,
                "llama_class_available": False,
                "error": f"{type(exc).__name__}:{exc}",
            }
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
