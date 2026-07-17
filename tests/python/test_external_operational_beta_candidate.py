from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_external_operational_beta_candidate_ready_from_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        activation,
        "build_v1_1_installer_launcher_readiness",
        lambda: {"status": "INSTALLER_LAUNCHER_READY_FOUNDATION"},
    )
    _write_json(
        tmp_path / "run" / "346_qwen25_wsl_external_smoke.json",
        {
            "status": "FIRST_REAL_INFERENCE_PASSED",
            "runtime_type": "external_wsl_conda",
            "safe_mode_final": True,
            "active_models_after": 0,
            "parallel_llm_loads_after": 0,
        },
    )
    _write_json(
        tmp_path / "run" / "304_final_role_pipeline.json",
        {
            "status": "FINAL_ENGINEERING_PIPELINE_PASSED",
            "active_models_after": 0,
            "parallel_llm_loads_after": 0,
        },
    )

    result = activation.build_external_operational_beta_candidate()

    assert result["status"] == "EXTERNAL_BETA_CANDIDATE_READY"
    assert result["external_operational_beta"] is True
    assert result["final_release_runtime"] is False
    assert result["is_embedded_runtime"] is False
    assert result["embedded_runtime_ready"] is False
    assert result["model_load_attempted"] is False
    assert result["real_inference_attempted"] is False


def test_external_operational_beta_candidate_blocks_without_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        activation,
        "build_v1_1_installer_launcher_readiness",
        lambda: {"status": "INSTALLER_LAUNCHER_READY_FOUNDATION"},
    )

    result = activation.build_external_operational_beta_candidate()

    assert result["status"] == "EXTERNAL_BETA_CANDIDATE_BLOCKED"
    assert {blocker["id"] for blocker in result["blockers"]} >= {
        "external_qwen25_smoke_passed",
        "final_engineering_pipeline_passed",
    }


def test_final_release_bridge_accepts_external_beta_but_not_final(monkeypatch) -> None:
    monkeypatch.setattr(
        activation,
        "build_public_alpha_readiness",
        lambda: {"alpha": "ALPHA_READY_WITH_LIMITATIONS"},
    )
    monkeypatch.setattr(
        activation,
        "build_embedded_runtime_beta_candidate",
        lambda *_args, **_kwargs: {"status": "BETA_CANDIDATE_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_external_operational_beta_candidate",
        lambda *_args, **_kwargs: {"status": "EXTERNAL_BETA_CANDIDATE_READY"},
    )
    monkeypatch.setattr(
        activation,
        "build_first_real_inference_live_status",
        lambda *_args, **_kwargs: {"status": "FIRST_REAL_INFERENCE_PASSED_EXTERNAL"},
    )
    monkeypatch.setattr(activation, "build_installer_rc_readiness", lambda: {"status": "RC_BLOCKED"})
    monkeypatch.setattr(
        activation,
        "build_clean_machine_emulator",
        lambda *_args, **_kwargs: {"status": "CLEAN_MACHINE_BLOCKED"},
    )

    result = activation.build_final_release_readiness_bridge()

    assert result["status"] == "FINAL_RELEASE_BLOCKED"
    assert result["external_beta_candidate_status"] == "EXTERNAL_BETA_CANDIDATE_READY"
    assert result["external_beta_candidate_counts_for_beta_only"] is True
    assert result["external_runtime_final_release_runtime"] is False
    assert "beta_candidate" not in result["public_release_blockers"]
    assert "installer_rc" in result["public_release_blockers"]
    assert "signed_installer" in result["public_release_blockers"]


def test_external_operational_beta_candidate_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_operational_beta_candidate",
        lambda *_args, **_kwargs: {"status": "EXTERNAL_BETA_CANDIDATE_BLOCKED"},
    )

    artifacts = activation.write_external_operational_beta_candidate_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "350_external_operational_beta_candidate.json",
        "351_external_operational_beta_candidate.md",
    }
