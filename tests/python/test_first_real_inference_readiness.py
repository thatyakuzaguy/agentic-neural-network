from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    build_first_real_inference_readiness,
    write_first_real_inference_readiness_artifacts,
)


def test_first_real_inference_readiness_not_ready_and_no_load() -> None:
    before = get_loaded_models()
    readiness = build_first_real_inference_readiness()

    assert readiness["status"] == "NOT_READY"
    assert set(readiness["blocking"]).intersection({"llama_cpp", "qwen25_backend", "launch_guard"})
    assert "wheelhouse" not in readiness["blocking"]
    assert readiness["real_inference_attempted"] is False
    assert readiness["model_load_attempted"] is False
    assert readiness["qwen3_blocked"] is True
    assert readiness["deepseek_blocked"] is True
    assert readiness["powerful_blocked"] is True
    assert get_loaded_models() == before == []
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_first_real_inference_readiness_artifacts(tmp_path: Path) -> None:
    artifacts = write_first_real_inference_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"194_first_real_inference_readiness.json", "195_first_real_inference_readiness.md"}
    payload = json.loads((tmp_path / "194_first_real_inference_readiness.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.2"
