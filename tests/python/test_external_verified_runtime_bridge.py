from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.loader import get_loaded_models


def test_external_runtime_ready_when_cuda_llama_and_qwen_exist(monkeypatch, tmp_path: Path) -> None:
    qwen = tmp_path / "qwen2.5.gguf"
    qwen.write_text("model-placeholder", encoding="utf-8")

    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {
            "torch_importable": True,
            "torch_version": "2.10.0+cu128",
            "cuda_available": True,
            "torch_cuda_version": "12.8",
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "vram_total_mb": 8192,
        },
    )
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: qwen)
    monkeypatch.setattr(activation.importlib.util, "find_spec", lambda name: object() if name == "llama_cpp" else None)
    monkeypatch.setattr(activation.importlib.metadata, "version", lambda _name: "0.3.0")
    monkeypatch.setenv("CONDA_PREFIX", "/home/ann/miniconda3/envs/qlora311")

    bridge = activation.build_external_verified_runtime_bridge()

    assert bridge["status"] == "EXTERNAL_RUNTIME_READY"
    assert bridge["runtime_type"] == "external_conda"
    assert bridge["is_embedded_runtime"] is False
    assert bridge["final_release_runtime"] is False
    assert bridge["torch_cuda_available"] is True
    assert bridge["llama_cpp_importable"] is True
    assert bridge["qwen25_gguf_exists"] is True
    assert bridge["model_load_attempted"] is False
    assert bridge["real_inference_attempted"] is False
    assert get_loaded_models() == []


def test_external_runtime_bridge_blocks_without_qwen(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {
            "torch_importable": True,
            "torch_version": "2.10.0+cu128",
            "cuda_available": True,
            "torch_cuda_version": "12.8",
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "vram_total_mb": 8192,
        },
    )
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: tmp_path / "missing.gguf")
    monkeypatch.setattr(activation.importlib.util, "find_spec", lambda name: object() if name == "llama_cpp" else None)

    bridge = activation.build_external_verified_runtime_bridge()

    assert bridge["status"] == "EXTERNAL_RUNTIME_BLOCKED"
    assert "qwen25_gguf_exists" in {check["id"] for check in bridge["blockers"]}
