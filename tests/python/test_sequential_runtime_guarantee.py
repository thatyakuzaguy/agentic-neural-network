from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from tests.python.test_developer_team_pipeline import _fake_child


def test_developer_team_pipeline_preserves_sequential_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: tmp_path / "model.gguf")
    monkeypatch.setattr(activation, "_run_qwen25_external_child_process", lambda *_args, **_kwargs: _fake_child())
    (tmp_path / "model.gguf").write_text("model", encoding="utf-8")

    result = activation.build_developer_team_pipeline(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real_coder=True,
    )

    assert result["sequential_runtime"] == "ACTIVE"
    assert result["active_models_after"] == 0
    assert result["parallel_llm_loads_after"] == 0
    assert get_loaded_models() == []
    assert get_runtime_metrics().get("active_models", 0) == 0
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0

