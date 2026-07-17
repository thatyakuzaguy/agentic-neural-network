from __future__ import annotations

import json
import subprocess

from agentic_network.runtime_engine import local_model_activation as activation


def test_wsl_external_runtime_bridge_detects_ready_runtime(monkeypatch) -> None:
    activation._WSL_EXTERNAL_RUNTIME_CACHE = None
    monkeypatch.setattr(activation.platform, "system", lambda: "Windows")
    monkeypatch.setattr(activation.shutil, "which", lambda name: "C:/Windows/System32/wsl.exe" if name == "wsl.exe" else None)

    payload = {
        "status": "WSL_RUNTIME_READY",
        "runtime_type": "external_wsl_conda",
        "python_executable": "/home/ann/miniconda3/envs/qlora311/bin/python",
        "python_version": "3.11.15",
        "torch_importable": True,
        "torch_version": "2.10.0+cu128",
        "torch_cuda_available": True,
        "torch_cuda_version": "12.8",
        "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
        "vram_total_mb": 8191.38,
        "llama_cpp_importable": True,
        "qwen25_gguf_exists": True,
        "blockers": [],
    }

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(activation.subprocess, "run", fake_run)

    result = activation.build_wsl_external_verified_runtime_bridge(force_refresh=True)

    assert result["status"] == "WSL_RUNTIME_READY"
    assert result["runtime_type"] == "external_wsl_conda"
    assert result["torch_cuda_available"] is True
    assert result["llama_cpp_importable"] is True
    assert result["qwen25_gguf_exists"] is True
    assert result["model_load_attempted"] is False
    assert result["real_inference_attempted"] is False


def test_best_external_runtime_selects_wsl_when_current_process_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_verified_runtime_bridge",
        lambda **_kwargs: {
            "status": "EXTERNAL_RUNTIME_BLOCKED",
            "runtime_type": "external_system",
            "is_embedded_runtime": False,
            "qwen25_gguf_exists": False,
            "qwen25_model_resolved_path": "",
            "llama_cpp_importable": False,
            "torch_cuda_available": False,
            "blockers": [{"id": "llama_cpp_importable", "passed": False}],
        },
    )
    monkeypatch.setattr(
        activation,
        "build_wsl_external_verified_runtime_bridge",
        lambda **_kwargs: {
            "status": "WSL_RUNTIME_READY",
            "runtime_type": "external_wsl_conda",
            "is_embedded_runtime": False,
            "final_release_runtime": False,
            "torch_cuda_available": True,
            "llama_cpp_importable": True,
            "qwen25_gguf_exists": True,
            "blockers": [],
        },
    )

    result = activation.build_best_external_verified_runtime_bridge()

    assert result["status"] == "EXTERNAL_RUNTIME_READY"
    assert result["selected_runtime_source"] == "wsl_conda"
    assert result["final_release_runtime"] is False


def test_external_smoke_readiness_can_use_best_wsl_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        activation,
        "build_best_external_verified_runtime_bridge",
        lambda **_kwargs: {
            "status": "EXTERNAL_RUNTIME_READY",
            "runtime_type": "external_wsl_conda",
            "selected_runtime_source": "wsl_conda",
            "is_embedded_runtime": False,
            "qwen25_gguf_exists": True,
            "qwen25_model_resolved_path": "/mnt/d/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf",
            "llama_cpp_importable": True,
            "torch_cuda_available": True,
            "blockers": [],
        },
    )

    result = activation.build_external_runtime_smoke_readiness()

    assert result["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    assert result["runtime_type"] == "external_wsl_conda"
    assert result["final_release_runtime"] is False
    assert result["model_load_attempted"] is False
