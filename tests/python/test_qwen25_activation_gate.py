from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    LOCAL_TEST_TOKEN,
    evaluate_qwen25_activation_gate,
)


def test_qwen25_gate_blocks_without_token() -> None:
    gate = evaluate_qwen25_activation_gate(confirm=True, approval_token=None)

    assert gate["status"] == "BLOCKED"
    assert gate["token_accepted"] is False
    assert "approval_token_invalid_or_missing" in gate["errors"]
    assert gate["model_name"] == "qwen2_5_coder_7b_v5"


def test_qwen25_gate_blocks_without_confirmation() -> None:
    gate = evaluate_qwen25_activation_gate(confirm=False, approval_token=LOCAL_TEST_TOKEN)

    assert gate["status"] == "BLOCKED"
    assert gate["confirmation"] is False
    assert "confirmation_required" in gate["errors"]


def test_qwen25_gate_reports_missing_model_unavailable(tmp_path: Path) -> None:
    missing = tmp_path / "missing.gguf"

    gate = evaluate_qwen25_activation_gate(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        model_path=missing,
    )

    assert gate["status"] == "UNAVAILABLE"
    assert gate["model_exists"] is False
    assert "qwen25_model_path_missing" in gate["errors"]


def test_qwen25_gate_passes_only_for_confirmed_qwen25() -> None:
    gate = evaluate_qwen25_activation_gate(confirm=True, approval_token=LOCAL_TEST_TOKEN)

    assert gate["status"] == "PASSED"
    assert gate["mode"] == "FAST"
    assert gate["backend"] == "llama_cpp"
    assert gate["qwen3_touched"] is False
    assert gate["deepseek_touched"] is False
    assert gate["powerful_activated"] is False
    assert gate["token_stored"] is False
