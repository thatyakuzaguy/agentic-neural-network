from __future__ import annotations

import inspect
import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from tests.python.test_qwen25_first_real_load import FakeLlama, _patch_ready


def test_safe_rollback_after_real_inference(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch, tmp_path)

    result = activation.run_qwen25_first_real_inference_external(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        llama_factory=FakeLlama,
    )
    rollback = json.loads((tmp_path / "260_safe_rollback_validation.json").read_text(encoding="utf-8"))

    assert result["safe_mode_final"] is True
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert rollback["status"] == "SAFE_ROLLBACK_PASSED"
    assert get_loaded_models() == []
    assert get_runtime_metrics().get("active_models", 0) == 0
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_real_inference_runner_does_not_use_shell_true() -> None:
    source = inspect.getsource(activation.run_qwen25_first_real_inference_external)
    helper_source = inspect.getsource(activation._nvidia_smi_memory_used_mb)

    assert "shell=True" not in source
    assert "shell=True" not in helper_source

