from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.local_model_activation import (
    build_deepseek_powerful_release_evidence,
    build_qwen25_release_evidence,
    build_qwen3_release_evidence,
)


def test_qwen25_release_evidence_reads_real_inference_without_loading_model() -> None:
    evidence = build_qwen25_release_evidence()

    assert evidence["passed"] is True
    assert evidence["status"] == "REAL_EVIDENCE_PASSED"
    assert evidence["raw_status"] == "FIRST_REAL_INFERENCE_PASSED"
    assert evidence["real_inference_success"] is True
    assert evidence["safe_rollback_passed"] is True
    assert evidence["no_model_load_now"] is True
    assert evidence["no_inference_now"] is True


def test_qwen3_release_evidence_reads_real_inference_without_requiring_live_gate() -> None:
    evidence = build_qwen3_release_evidence()

    assert evidence["passed"] is True
    assert evidence["status"] == "REAL_EVIDENCE_PASSED"
    assert evidence["raw_status"] == "QWEN3_REAL_PASSED"
    assert evidence["real_inference_success"] is True
    assert evidence["safe_rollback_passed"] is True
    assert evidence["no_model_load_now"] is True
    assert evidence["no_inference_now"] is True


def test_deepseek_powerful_release_evidence_reads_real_gguf_review() -> None:
    evidence = build_deepseek_powerful_release_evidence()

    assert evidence["passed"] is True
    assert evidence["status"] == "REAL_EVIDENCE_PASSED"
    assert evidence["raw_status"] == "DEEPSEEK_REAL_PASSED"
    assert evidence["real_inference_success"] is True
    assert evidence["safe_rollback_passed"] is True
    assert evidence["no_model_load_now"] is True
    assert evidence["no_inference_now"] is True


def test_deepseek_powerful_release_evidence_does_not_promote_deferred_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "deferred"
    run_dir.mkdir()
    (run_dir / "282_deepseek_real_review.json").write_text(
        json.dumps(
            {
                "status": "DEEPSEEK_POWERFUL_DEFERRED",
                "real_inference_success": False,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "286_deepseek_safe_rollback.json").write_text(
        json.dumps(
            {
                "status": "SAFE_ROLLBACK_PASSED",
                "active_models_after": 0,
                "parallel_llm_loads_after": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path)

    evidence = activation.build_deepseek_powerful_release_evidence()

    assert evidence["passed"] is False
    assert evidence["raw_status"] == "DEEPSEEK_POWERFUL_DEFERRED"
