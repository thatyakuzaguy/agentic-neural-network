from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_desktop_developer_team_status_shows_powerful_deferred(monkeypatch, tmp_path: Path) -> None:
    pipeline = {
        "status": "TEAM_PIPELINE_PASSED_WITH_POWERFUL_DEFERRED",
        "qwen3_status": "QWEN3_REAL_PASSED",
        "qwen25_status": "PASSED",
        "deepseek_status": "DEEPSEEK_POWERFUL_DEFERRED",
        "powerful_deferred_reason": activation.POWERFUL_DEFERRED_REASON,
        "powerful_fallback_status": "POWERFUL_BRIDGE_REVIEW_ALLOWED",
        "sequential_runtime": "ACTIVE",
        "peak_vram_mb": 7792.0,
        "model_switch_time_seconds": 0.0,
        "total_runtime_seconds": 10.0,
        "safe_rollback": "PASSED",
    }
    (tmp_path / "288_full_team_pipeline.json").write_text(json.dumps(pipeline), encoding="utf-8")
    (tmp_path / "296_full_team_action_plan.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path)

    result = activation.build_developer_team_desktop_status()

    assert result["status"] == "TEAM_PIPELINE_PASSED_WITH_POWERFUL_DEFERRED"
    assert result["qwen3"] == "PASSED"
    assert result["qwen2_5"] == "PASSED"
    assert result["deepseek"] == "DEFERRED"
    assert result["deepseek_reason"] == activation.POWERFUL_DEFERRED_REASON
    assert result["powerful_fallback"] == "POWERFUL_BRIDGE_REVIEW_ALLOWED"
