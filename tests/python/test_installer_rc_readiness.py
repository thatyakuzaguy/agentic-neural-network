from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_installer_rc_readiness,
    write_installer_rc_readiness_artifacts,
)


def test_installer_rc_readiness_blocks_when_embedded_runtime_missing() -> None:
    readiness = build_installer_rc_readiness()

    assert readiness["status"] in {
        "RC_BLOCKED",
        "RC_READY_FOUNDATION_ONLY",
        "RC_READY_FOR_MANUAL_PACKAGING",
        "RC_READY",
    }
    assert any(check["name"] == "embedded_python_exists" for check in readiness["checks"])
    assert any(check["name"] == "embedded_runtime_packages_present" for check in readiness["checks"])
    embedded_check = next(check for check in readiness["checks"] if check["name"] == "embedded_python_exists")
    if not embedded_check["passed"]:
        assert readiness["status"] == "RC_BLOCKED"
    package_check = next(check for check in readiness["checks"] if check["name"] == "embedded_runtime_packages_present")
    if not package_check["passed"]:
        assert readiness["status"] == "RC_BLOCKED"
        assert readiness["embedded_runtime_missing_packages"]
    assert readiness["embedded_runtime_package_audit"] in {"PACKAGE_AUDIT_READY", "PACKAGE_AUDIT_INCOMPLETE", "PACKAGE_AUDIT_BLOCKED"}
    assert readiness["qwen2_5_loaded"] is False
    assert readiness["qwen3_loaded"] is False
    assert readiness["deepseek_loaded"] is False
    assert readiness["powerful_activated"] is False


def test_installer_rc_readiness_artifacts(tmp_path: Path) -> None:
    artifacts = write_installer_rc_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"152_installer_rc_readiness.json", "153_installer_rc_readiness.md"}
    payload = json.loads((tmp_path / "152_installer_rc_readiness.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.7"
