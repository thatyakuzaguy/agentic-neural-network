from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_runtime_collection_manifest,
    write_runtime_collection_manifest_artifacts,
)


def test_runtime_collection_manifest_required() -> None:
    manifest = build_runtime_collection_manifest()
    names = {entry["name"] for entry in manifest["entries"]}

    assert manifest["status"] == "COLLECTION_READY"
    assert manifest["manual_collection_required"] is False
    assert "embedded_python" in names
    assert "runtime_wheels" in names
    assert "requirements_lock" in names
    assert manifest["no_install"] is True
    assert manifest["no_download"] is True


def test_runtime_collection_manifest_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_collection_manifest_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"176_runtime_collection_manifest.json", "177_runtime_collection_manifest.md"}
    payload = json.loads((tmp_path / "176_runtime_collection_manifest.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.7"
