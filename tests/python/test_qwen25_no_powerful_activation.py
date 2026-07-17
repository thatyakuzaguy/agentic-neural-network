from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import LOCAL_TEST_TOKEN, run_controlled_qwen25_smoke


def test_qwen25_smoke_does_not_touch_qwen3_deepseek_or_powerful(tmp_path: Path) -> None:
    result = run_controlled_qwen25_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)
    trace = json.loads((tmp_path / "108_qwen25_runtime_trace.json").read_text(encoding="utf-8"))

    assert result["model_name"] == "qwen2_5_coder_7b_v5"
    assert trace["qwen3_touched"] is False
    assert trace["deepseek_touched"] is False
    assert trace["powerful_activated"] is False
    assert "deepseek_r1_distill_qwen_14b" not in json.dumps(trace)
    assert "qwen3_8b_product_v9_repaired_v2_bullets" not in json.dumps(trace)


def test_qwen25_smoke_does_not_enable_global_policy(tmp_path: Path) -> None:
    run_controlled_qwen25_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)
    gate = json.loads((tmp_path / "104_qwen25_activation_gate.json").read_text(encoding="utf-8"))

    assert gate["policy_global_safe"] is True
    assert gate["mode"] == "FAST"
    assert gate["model_name"] == "qwen2_5_coder_7b_v5"
