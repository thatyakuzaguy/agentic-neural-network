from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_wheelhouse_external_validation,
    write_wheelhouse_external_validation_artifacts,
)


def test_wheelhouse_external_validation_verified() -> None:
    validation = build_wheelhouse_external_validation()

    assert validation["status"] == "VERIFIED"
    assert validation["missing"] == []
    assert validation["mismatch"] == []
    assert validation["verified"]
    assert validation["no_install"] is True
    assert validation["no_download"] is True


def test_wheelhouse_external_validation_artifacts(tmp_path: Path) -> None:
    artifacts = write_wheelhouse_external_validation_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"200_wheelhouse_external_validation.json", "201_wheelhouse_external_validation.md"}
    payload = json.loads((tmp_path / "200_wheelhouse_external_validation.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.4"
