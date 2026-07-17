from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_offline_runtime_lockfile,
    write_offline_runtime_lockfile_artifacts,
)


def test_offline_runtime_lockfile_example_exists_and_is_declarative() -> None:
    path = Path("D:/AgenticEngineeringNetwork/config/ann_runtime_lock.example.json")
    lockfile = build_offline_runtime_lockfile()

    assert path.is_file()
    assert lockfile["version"] == "18.9.5"
    assert lockfile["verification_status"] == "hash_verified"
    assert lockfile["expected_runtime_path"] == "D:\\ANN\\runtime"
    assert lockfile["safety"]["dependency_install"] is False
    assert lockfile["safety"]["downloads"] is False
    assert any(package["name"] == "llama-cpp-python" for package in lockfile["packages"])
    assert all(wheel["status"] == "hash_verified" for wheel in lockfile["wheels"])
    assert all(wheel["sha256"] for wheel in lockfile["wheels"])


def test_offline_runtime_lockfile_artifacts(tmp_path: Path) -> None:
    artifacts = write_offline_runtime_lockfile_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"146_offline_runtime_lockfile.json", "147_offline_runtime_lockfile.md"}
    payload = json.loads((tmp_path / "146_offline_runtime_lockfile.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.5"
