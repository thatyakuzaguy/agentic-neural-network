from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from tests.python.test_qwen25_first_real_load import FakeLlama, _patch_ready


def test_qwen25_real_benchmark_artifact_contains_timings_and_vram(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        llama_factory=FakeLlama,
    )

    payload = json.loads((tmp_path / "258_qwen25_real_benchmark.json").read_text(encoding="utf-8"))
    assert payload["status"] == result["status"]
    assert payload["load_time_seconds"] >= 0
    assert payload["inference_time_seconds"] >= 0
    assert payload["peak_vram_mb"] == 100.0
    assert payload["tokens_generated"] == 2
    assert payload["tokens_per_second"] >= 0

