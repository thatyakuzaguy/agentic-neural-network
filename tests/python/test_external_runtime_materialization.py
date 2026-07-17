from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_external_runtime_materialization,
    write_external_runtime_materialization_artifacts,
)


def test_external_runtime_materialization_missing() -> None:
    materialization = build_external_runtime_materialization()

    assert materialization["status"] == "FULLY_MATERIALIZED"
    assert materialization["manual_copy_required"] is False
    assert materialization["missing"] == []
    assert materialization["no_copy"] is True
    assert materialization["no_install"] is True


def test_external_runtime_materialization_artifacts(tmp_path: Path) -> None:
    artifacts = write_external_runtime_materialization_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"188_external_runtime_materialization.json", "189_external_runtime_materialization.md"}
    payload = json.loads((tmp_path / "188_external_runtime_materialization.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.0"
