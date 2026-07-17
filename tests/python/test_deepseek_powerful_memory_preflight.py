from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_8gb_gpu_marks_deepseek_hf_full_load_unsafe(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "deepseek"
    model.mkdir()
    (model / "model-00001-of-00002.safetensors").write_text("", encoding="utf-8")
    monkeypatch.setattr(activation, "_directory_file_size_mb", lambda *_args, **_kwargs: 28600.0)
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {
            "cuda_available": True,
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "vram_total_mb": 8192.0,
        },
    )
    monkeypatch.setattr(activation, "_query_nvidia_smi_memory", lambda: {"available": True, "free_mb": 7000.0})
    monkeypatch.setattr(activation, "_deepseek_gguf_alternative_exists", lambda _path=None: False)

    result = activation.build_deepseek_powerful_memory_preflight(output_dir=tmp_path, model_path=model)

    assert result["status"] == "POWERFUL_REQUIRES_QUANTIZED_MODEL"
    assert result["reason"] == activation.POWERFUL_DEFERRED_REASON
    assert result["full_gpu_load_unsafe"] is True
    assert result["cpu_offload_likely_required"] is True
    assert result["quantized_or_gguf_model_likely_required"] is True
    assert (tmp_path / "298_deepseek_memory_preflight.json").is_file()
    assert (tmp_path / "299_deepseek_memory_preflight.md").is_file()


def test_8gb_gpu_allows_deepseek_powerful_when_quantized_gguf_exists(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "deepseek"
    model.mkdir()
    gguf = tmp_path / "deepseek-q4.gguf"
    gguf.write_bytes(b"gguf")
    (model / "model-00001-of-00002.safetensors").write_text("", encoding="utf-8")
    monkeypatch.setattr(activation, "_directory_file_size_mb", lambda *_args, **_kwargs: 28600.0)
    monkeypatch.setattr(
        activation,
        "diagnose_cuda_environment",
        lambda: {
            "cuda_available": True,
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "vram_total_mb": 8192.0,
        },
    )
    monkeypatch.setattr(activation, "_query_nvidia_smi_memory", lambda: {"available": True, "free_mb": 7000.0})
    monkeypatch.setattr(activation, "_deepseek_gguf_alternative_exists", lambda _path=None: True)
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda path: gguf if str(path).endswith(".gguf") else model)

    result = activation.build_deepseek_powerful_memory_preflight(output_dir=tmp_path, model_path=model)
    fallback = activation.build_powerful_fallback_gate(preflight=result)

    assert result["status"] == "POWERFUL_QUANTIZED_GGUF_SAFE_TO_ATTEMPT"
    assert result["reason"] is None
    assert result["llama_cpp_gguf_alternative_exists"] is True
    assert fallback["status"] == "POWERFUL_REAL_READY"
    assert fallback["attempt_real_deepseek_load"] is True
    assert fallback["defer_powerful"] is False
