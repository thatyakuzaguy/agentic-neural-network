from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from tests.python.test_qwen25_first_real_load import FakeLlama, _patch_ready


def test_qwen25_first_real_inference_captures_prompt_and_response(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        llama_factory=FakeLlama,
    )

    assert result["status"] == "FIRST_REAL_INFERENCE_PASSED"
    assert result["real_inference_attempted"] is True
    assert result["real_inference_success"] is True
    assert result["generated_text"] == "Hi there"
    assert result["tokens_generated"] == 2
    assert result["prompt_tokens"] == 1
    assert (tmp_path / "256_qwen25_first_real_inference.json").is_file()


def test_qwen25_first_real_inference_requires_exact_prompt(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        prompt="not hello",
        llama_factory=FakeLlama,
    )

    assert result["real_load_attempted"] is False
    assert result["real_inference_attempted"] is False
    assert "exact_prompt_hello_required" in result["errors"]

