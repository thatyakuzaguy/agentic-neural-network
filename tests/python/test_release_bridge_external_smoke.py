from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_final_release_bridge_accepts_external_smoke_but_stays_blocked(monkeypatch) -> None:
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
        "build_first_real_inference_live_status",
        lambda *_args, **_kwargs: {"status": "FIRST_REAL_INFERENCE_PASSED_EXTERNAL"},
    )
    monkeypatch.setattr(
        activation,
        "build_installer_rc_readiness",
        lambda: {"status": "RC_BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_clean_machine_emulator",
        lambda *_args, **_kwargs: {"status": "CLEAN_MACHINE_BLOCKED"},
    )

    result = activation.build_final_release_readiness_bridge()

    assert result["status"] == "FINAL_RELEASE_BLOCKED"
    assert result["first_inference_status"] == "FIRST_REAL_INFERENCE_PASSED_EXTERNAL"
    assert "first_inference_status" not in result["public_release_blockers"]
    assert "installer_rc" in result["public_release_blockers"]
    assert result["signed_installer"] is False
