from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_powerful_fallback_gate_defers_instead_of_attempting_unsafe_load(tmp_path: Path) -> None:
    preflight = {
        "status": "POWERFUL_REQUIRES_QUANTIZED_MODEL",
        "reason": activation.POWERFUL_DEFERRED_REASON,
    }

    result = activation.build_powerful_fallback_gate(
        output_dir=tmp_path,
        preflight=preflight,
        qwen3={"status": "QWEN3_REAL_PASSED"},
        qwen25={"status": "PASSED"},
    )

    assert result["status"] == "POWERFUL_BRIDGE_REVIEW_ALLOWED"
    assert result["attempt_real_deepseek_load"] is False
    assert result["defer_powerful"] is True
    assert result["use_bridge_review"] is True
    assert result["deepseek_stage_status"] == "DEEPSEEK_POWERFUL_DEFERRED"
    assert (tmp_path / "300_powerful_fallback_gate.json").is_file()
    assert (tmp_path / "301_powerful_fallback_gate.md").is_file()
