from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_ann_v1_installer_final_readiness_reports_foundation_state() -> None:
    readiness = activation.build_ann_v1_installer_final_readiness()

    assert readiness["status"] in {
        "INSTALLER_V1_READY_FOUNDATION",
        "INSTALLER_V1_BLOCKED",
        "INSTALLER_V1_READY",
    }
    assert readiness["external_runtime_mode"] == "SUPPORTED"
    assert readiness["no_build_performed"] is True
    assert readiness["no_install_performed"] is True
    assert any(check["id"] == "launcher" for check in readiness["checks"])
    assert any(check["id"] == "verify_install" for check in readiness["checks"])
    assert "signed_installer_blockers" in readiness
