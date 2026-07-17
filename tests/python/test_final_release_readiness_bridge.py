from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_final_release_readiness_bridge,
    write_final_release_readiness_bridge_artifacts,
    write_guided_runtime_macro_artifacts,
)


def test_final_release_readiness_bridge_blocked() -> None:
    bridge = build_final_release_readiness_bridge()

    assert bridge["status"] == "FINAL_RELEASE_BLOCKED"
    if bridge["first_inference_status"] == "FIRST_REAL_INFERENCE_PASSED_EXTERNAL":
        assert "first_inference_status" not in bridge["public_release_blockers"]
    else:
        assert "first_inference_status" in bridge["public_release_blockers"]
    assert "signed_installer" in bridge["public_release_blockers"]
    assert "clean_machine_evidence" in bridge["public_release_blockers"]
    assert bridge["signed_installer"] is False
    assert bridge["clean_machine_evidence_status"] == "LOCAL_INSTALL_SMOKE_PASSED"
    assert bridge["local_install_smoke_passed"] is True
    assert bridge["external_clean_machine_passed"] is False
    assert bridge["qwen3_blocked"] is True
    assert bridge["deepseek_blocked"] is True
    assert bridge["powerful_blocked"] is True


def test_final_release_readiness_bridge_artifacts(tmp_path: Path) -> None:
    artifacts = write_final_release_readiness_bridge_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"222_final_release_readiness_bridge.json", "223_final_release_readiness_bridge.md"}
    payload = json.loads((tmp_path / "222_final_release_readiness_bridge.json").read_text(encoding="utf-8"))
    assert payload["version"] == "17.4"


def test_guided_runtime_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_guided_runtime_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "218_guided_runtime_activation_state.json",
        "219_guided_runtime_activation_state.md",
        "220_qwen25_smoke_button_gate.json",
        "221_qwen25_smoke_button_gate.md",
        "222_final_release_readiness_bridge.json",
        "223_final_release_readiness_bridge.md",
    } == names
