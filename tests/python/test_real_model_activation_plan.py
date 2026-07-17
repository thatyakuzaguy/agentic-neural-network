from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_real_model_activation_plan,
    write_model_activation_artifacts,
)


def test_real_model_activation_plan_is_non_executing() -> None:
    plan = build_real_model_activation_plan()

    assert plan["status"] == "PLAN_ONLY"
    assert [step["order"] for step in plan["steps"]] == [1, 2, 3, 4, 5, 6]
    assert all(step["executes_now"] is False for step in plan["steps"])
    assert plan["steps"][0]["model"] == "qwen2_5_coder_7b_v5"
    assert plan["steps"][1]["model"] == "qwen3_8b_product_v9_repaired_v2_bullets"
    assert plan["steps"][2]["model"] == "deepseek_r1_distill_qwen_14b"
    assert "no_model_load" in plan["must_not_do_now"]


def test_model_activation_artifacts_98_to_103(tmp_path: Path) -> None:
    artifacts = write_model_activation_artifacts(tmp_path / "outputs" / "model_activation" / "run_001")
    names = {Path(path).name for path in artifacts}

    assert names == {
        "98_model_identity_correction.json",
        "99_model_identity_correction.md",
        "100_local_model_preflight.json",
        "101_local_model_preflight.md",
        "102_real_model_activation_plan.json",
        "103_real_model_activation_plan.md",
    }
    payload = json.loads((tmp_path / "outputs" / "model_activation" / "run_001" / "100_local_model_preflight.json").read_text())
    assert payload["policy"]["allow_real_model_load"] is False
