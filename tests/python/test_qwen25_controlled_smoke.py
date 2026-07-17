from __future__ import annotations

import subprocess
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import LOCAL_TEST_TOKEN, run_controlled_qwen25_smoke


def test_qwen25_smoke_blocks_without_token(tmp_path: Path) -> None:
    result = run_controlled_qwen25_smoke(confirm=True, approval_token=None, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert result["mock_fallback"] is True
    assert result["safe_mode_final"] is True


def test_qwen25_smoke_blocks_without_confirmation(tmp_path: Path) -> None:
    result = run_controlled_qwen25_smoke(confirm=False, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["real_load_attempted"] is False
    assert "confirmation_required" in result["errors"]


def test_qwen25_smoke_valid_token_attempts_only_qwen25(tmp_path: Path, monkeypatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Controlled Qwen2.5 smoke must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    result = run_controlled_qwen25_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)

    assert result["model_name"] == "qwen2_5_coder_7b_v5"
    assert result["backend"] == "llama_cpp"
    assert result["real_load_attempted"] is True
    assert result["safe_mode_final"] is True
    assert result["loaded_models_after"] == []
    assert result["status"] in {"UNAVAILABLE", "LOAD_FAILED", "LOAD_BLOCKED"}


def test_qwen25_smoke_generates_artifacts_104_to_109(tmp_path: Path) -> None:
    result = run_controlled_qwen25_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=tmp_path)
    names = {Path(path).name for path in result["artifacts"]}

    assert names == {
        "104_qwen25_activation_gate.json",
        "105_qwen25_activation_gate.md",
        "106_qwen25_backend_smoke.json",
        "107_qwen25_backend_smoke.md",
        "108_qwen25_runtime_trace.json",
        "109_qwen25_runtime_trace.md",
    }
    assert not any(LOCAL_TEST_TOKEN in Path(path).read_text(encoding="utf-8") for path in result["artifacts"])
