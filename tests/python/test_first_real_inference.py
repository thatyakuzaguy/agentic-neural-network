from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    LOCAL_TEST_TOKEN,
    QWEN25_MODEL_NAME,
    run_controlled_first_real_inference,
    write_beta_runtime_live_macro_artifacts,
)


class FakeQwen25Backend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load_model(self, model_name: str) -> dict[str, object]:
        self.calls.append(f"load:{model_name}")
        return {"status": "LOADED", "model_name": model_name, "backend": "llama_cpp", "loaded": True}

    def generate(self, model_name: str, prompt: str) -> dict[str, object]:
        self.calls.append(f"generate:{model_name}:{prompt}")
        return {
            "status": "SUCCESS",
            "model_name": model_name,
            "backend": "llama_cpp",
            "text": "4",
            "tokens_in": 3,
            "tokens_out": 1,
        }

    def unload_model(self, model_name: str) -> dict[str, object]:
        self.calls.append(f"unload:{model_name}")
        return {"status": "UNLOADED", "model_name": model_name, "backend": "llama_cpp", "unloaded": True}


def test_first_real_inference_blocked_by_default(tmp_path: Path) -> None:
    result = run_controlled_first_real_inference(output_dir=tmp_path)

    assert result["status"] == "NOT_READY"
    assert result["real_load_attempted"] is False
    assert result["real_inference_attempted"] is False
    assert result["safe_mode_final"] is True
    assert get_loaded_models() == []


def test_first_real_inference_successful_load_run_unload(monkeypatch, tmp_path: Path) -> None:
    fake = FakeQwen25Backend()
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_controlled_first_inference_gate",
        lambda *_args, **_kwargs: {"status": "READY_FOR_CONTROLLED_SMOKE", "blocking": []},
    )

    result = run_controlled_first_real_inference(
        approval_token=LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        backend=fake,
    )

    assert result["status"] == "SUCCESS"
    assert result["real_load_succeeded"] is True
    assert result["real_inference_succeeded"] is True
    assert result["safe_mode_final"] is True
    assert result["loaded_models_after"] == []
    assert result["unload_status"] == "UNLOADED"
    assert fake.calls == [
        f"load:{QWEN25_MODEL_NAME}",
        f"generate:{QWEN25_MODEL_NAME}:Return exactly: 4",
        f"unload:{QWEN25_MODEL_NAME}",
    ]
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_first_real_inference_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_runtime_live_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "210_runtime_materialization_watcher.json",
        "211_runtime_materialization_watcher.md",
        "212_beta_runtime_activation.json",
        "213_beta_runtime_activation.md",
        "214_first_real_inference.json",
        "215_first_real_inference.md",
        "216_runtime_benchmark_real.json",
        "217_runtime_benchmark_real.md",
    } == names
    payload = json.loads((tmp_path / "214_first_real_inference.json").read_text(encoding="utf-8"))
    assert payload["version"] == "17.1"
    assert payload["qwen3_touched"] is False
    assert payload["deepseek_touched"] is False
    assert payload["powerful_activated"] is False
