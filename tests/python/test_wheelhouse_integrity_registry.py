from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_wheelhouse_integrity_registry,
    write_wheelhouse_integrity_registry_artifacts,
)


def test_wheelhouse_integrity_registry_reports_hash_verified() -> None:
    registry = build_wheelhouse_integrity_registry()

    assert registry["status"] == "HASH_VERIFIED"
    assert registry["expected_count"] >= 1
    assert registry["missing_count"] == 0
    assert registry["verified_count"] == registry["expected_count"]
    assert all("filename" in item for item in registry["wheels"])
    assert registry["no_install"] is True
    assert registry["no_download"] is True


def test_wheelhouse_integrity_registry_artifacts(tmp_path: Path) -> None:
    artifacts = write_wheelhouse_integrity_registry_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"178_wheelhouse_integrity_registry.json", "179_wheelhouse_integrity_registry.md"}
    payload = json.loads((tmp_path / "178_wheelhouse_integrity_registry.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.7"
