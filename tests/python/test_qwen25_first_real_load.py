from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


class FakeLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def __call__(self, prompt: str, **_kwargs):
        return {
            "choices": [{"text": "Hi there"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }

    def close(self) -> None:
        self.closed = True


def _patch_ready(monkeypatch, tmp_path: Path) -> Path:
    model = tmp_path / "qwen.gguf"
    model.write_text("model", encoding="utf-8")
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: model)
    monkeypatch.setattr(
        activation,
        "build_external_verified_runtime_bridge",
        lambda: {
            "status": "EXTERNAL_RUNTIME_READY",
            "runtime_type": "external_conda",
            "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
            "qwen25_gguf_exists": True,
        },
    )
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )
    monkeypatch.setattr(
        activation,
        "_vram_sample",
        lambda label: {"label": label, "memory_used_mb": 100.0, "gpu_name": "NVIDIA GeForce RTX 3060 Ti"},
    )
    return model


def test_qwen25_first_real_load_success_with_injected_factory(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        llama_factory=FakeLlama,
    )

    assert result["real_load_attempted"] is True
    assert result["real_load_success"] is True
    assert (tmp_path / "254_qwen25_first_real_load.json").is_file()


def test_qwen25_first_real_load_failure_aborts(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    class BrokenLlama:
        def __init__(self, **_kwargs):
            raise RuntimeError("load exploded")

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        llama_factory=BrokenLlama,
    )

    assert result["status"] == "FIRST_REAL_INFERENCE_FAILED"
    assert result["real_load_attempted"] is True
    assert result["real_load_success"] is False
    assert result["real_inference_attempted"] is False
    assert "RuntimeError: load exploded" in result["errors"]

