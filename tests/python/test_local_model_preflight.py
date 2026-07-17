from __future__ import annotations

import subprocess

from agentic_network.runtime_engine.local_model_activation import build_local_model_preflight


def test_local_model_preflight_is_safe_mode_and_read_only(monkeypatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Local model preflight must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    preflight = build_local_model_preflight()

    assert preflight["status"] == "SAFE_MODE"
    assert preflight["runtime"]["safe_mode"] is True
    assert preflight["policy"]["allow_real_model_load"] is False
    assert preflight["policy"]["max_loaded_models"] == 1
    assert preflight["policy"]["parallel_llm_loads"] == 0
    assert preflight["runtime"]["active_models"] <= 1
    assert preflight["runtime"]["parallel_llm_loads"] == 0


def test_preflight_detects_fast_and_powerful_targets() -> None:
    preflight = build_local_model_preflight()
    names = {model["model_name"]: model for model in preflight["models"]}

    assert "qwen2_5_coder_7b_v5" in names
    assert "qwen3_8b_product_v9_repaired_v2_bullets" in names
    assert "deepseek_r1_distill_qwen_14b" in names
    assert preflight["fast"]["available"] is True
    assert preflight["powerful"]["available"] is True
    assert preflight["powerful"]["blocked"] is True
    assert names["deepseek_r1_distill_qwen_14b"]["backend"] == "deepseek_unsloth"
