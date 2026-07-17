from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    build_beta_readiness_gate,
    write_beta_foundation_macro_artifacts,
    write_beta_readiness_gate_artifacts,
)


def test_beta_readiness_gate_blocks_on_backend_and_first_inference_after_wheelhouse_ready() -> None:
    gate = build_beta_readiness_gate()
    blockers = {item["id"] for item in gate["blockers"]}

    assert gate["status"] == "BETA_BLOCKED"
    assert "wheelhouse_integrity" not in blockers
    assert "installer_rc_status" not in blockers
    assert {"qwen25_backend_readiness", "first_real_inference_status"}.issubset(blockers)
    assert gate["qwen2_5_backend_blocked"] is True
    assert gate["qwen3_blocked"] is True
    assert gate["deepseek_blocked"] is True
    assert gate["powerful_blocked"] is True


def test_beta_readiness_gate_does_not_load_models() -> None:
    before = get_loaded_models()
    gate = build_beta_readiness_gate()
    metrics = get_runtime_metrics()

    assert get_loaded_models() == before == []
    assert gate["active_models"] <= 1
    assert metrics.get("parallel_llm_loads", 0) == 0
    assert gate["vram_policy"] == "SEQUENTIAL"


def test_beta_readiness_gate_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_readiness_gate_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"174_beta_readiness_gate.json", "175_beta_readiness_gate.md"}
    payload = json.loads((tmp_path / "174_beta_readiness_gate.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.6"


def test_beta_foundation_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_foundation_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "168_embedded_runtime_layout.json",
        "169_embedded_runtime_layout.md",
        "170_wheelhouse_materialization_plan.json",
        "171_wheelhouse_materialization_plan.md",
        "172_clean_machine_emulator.json",
        "173_clean_machine_emulator.md",
        "174_beta_readiness_gate.json",
        "175_beta_readiness_gate.md",
    } == names
