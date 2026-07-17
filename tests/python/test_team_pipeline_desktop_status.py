from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_team_pipeline_desktop_status_reads_latest_artifacts(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "model_activation"
    run = root / "run"
    run.mkdir(parents=True)
    (run / "262_product_architect_output.json").write_text(json.dumps({"status": "QWEN3_BRIDGE_MODE"}), encoding="utf-8")
    (run / "264_coder_output.json").write_text(
        json.dumps({"status": "PASSED", "peak_vram_mb": 1200, "safe_mode_final": True}),
        encoding="utf-8",
    )
    (run / "266_powerful_review.json").write_text(json.dumps({"status": "DEEPSEEK_BRIDGE_MODE"}), encoding="utf-8")
    (run / "271_action_plan.json").write_text(json.dumps({"status": "ACTION_PLAN_READY_FOR_HUMAN_REVIEW"}), encoding="utf-8")
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", root)

    status = activation.build_developer_team_desktop_status()

    assert status["status"] == "TEAM_PIPELINE_ARTIFACTS_FOUND"
    assert status["qwen3"] == "BRIDGE"
    assert status["qwen2_5"] == "PASSED"
    assert status["deepseek"] == "BRIDGE"
    assert status["sequential_runtime"] == "ACTIVE"
    assert status["safe_rollback"] == "PASSED"

