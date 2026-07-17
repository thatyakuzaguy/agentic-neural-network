from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    build_beta_candidate_final_gate,
    write_beta_candidate_final_gate_artifacts,
    write_manual_materialization_macro_artifacts,
)


def test_beta_candidate_final_gate_blocked_and_safe() -> None:
    before = get_loaded_models()
    gate = build_beta_candidate_final_gate()
    blockers = {item["id"] for item in gate["blockers"]}

    assert gate["status"] == "BETA_FINAL_BLOCKED"
    assert "first_inference_ready" in blockers
    assert "integrity_verified" not in blockers
    assert "wheelhouse_verified" not in blockers
    assert gate["safe_mode"] is True
    assert gate["qwen2_5_blocked"] is True
    assert gate["qwen3_blocked"] is True
    assert gate["deepseek_blocked"] is True
    assert gate["powerful_blocked"] is True
    assert gate["model_load_attempted"] is False
    assert gate["real_inference_attempted"] is False
    assert get_loaded_models() == before == []
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_beta_candidate_final_gate_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_candidate_final_gate_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"202_beta_candidate_final_gate.json", "203_beta_candidate_final_gate.md"}
    payload = json.loads((tmp_path / "202_beta_candidate_final_gate.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.5"


def test_manual_materialization_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_manual_materialization_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "196_manual_external_runtime_checklist.json",
        "197_manual_external_runtime_checklist.md",
        "198_runtime_integrity_verification.json",
        "199_runtime_integrity_verification.md",
        "200_wheelhouse_external_validation.json",
        "201_wheelhouse_external_validation.md",
        "202_beta_candidate_final_gate.json",
        "203_beta_candidate_final_gate.md",
    } == names
