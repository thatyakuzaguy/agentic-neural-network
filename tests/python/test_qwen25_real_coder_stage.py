from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from tests.python.test_developer_team_pipeline import _fake_child


def test_qwen25_real_coder_stage_uses_real_child_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )
    monkeypatch.setattr(activation, "_resolve_runtime_filesystem_path", lambda _path: tmp_path / "model.gguf")
    monkeypatch.setattr(activation, "_run_qwen25_external_child_process", lambda *_args, **_kwargs: _fake_child())
    (tmp_path / "model.gguf").write_text("model", encoding="utf-8")

    stage = activation.build_qwen25_real_coder_stage(
        approval_token=activation.LOCAL_TEST_TOKEN,
        manual_confirmation=True,
        output_dir=tmp_path,
        execute_real=True,
    )

    assert stage["status"] == "PASSED"
    assert stage["real_inference_required"] is True
    assert stage["real_inference_attempted"] is True
    assert stage["real_inference_success"] is True
    assert stage["safe_mode_final"] is True
    assert stage["active_models_after"] == 0
    assert stage["parallel_llm_loads_after"] == 0

