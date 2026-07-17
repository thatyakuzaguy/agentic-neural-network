from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_embedded_runtime_installer_readiness,
    write_embedded_runtime_installer_readiness_artifacts,
)


def test_embedded_runtime_installer_readiness_detects_missing_embedded_python() -> None:
    readiness = build_embedded_runtime_installer_readiness()

    assert readiness["status"] in {"READY", "EMBEDDED_RUNTIME_MISSING"}
    assert readiness["expected_paths"]["embedded_python"] == "D:\\ANN\\runtime\\python\\python.exe"
    assert readiness["no_dependency_download_in_installer"] is True
    assert readiness["no_model_movement"] is True
    assert "projects" in readiness["preserve"]
    assert any(check["id"] == "embedded_python" for check in readiness["checks"])


def test_embedded_runtime_installer_readiness_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_runtime_installer_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "142_embedded_runtime_installer_readiness.json",
        "143_embedded_runtime_installer_readiness.md",
    }
    payload = json.loads((tmp_path / "142_embedded_runtime_installer_readiness.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.3"
