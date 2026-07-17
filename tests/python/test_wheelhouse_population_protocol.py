from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_wheelhouse_population_protocol,
    write_wheelhouse_population_protocol_artifacts,
)


def test_wheelhouse_population_protocol_verified() -> None:
    protocol = build_wheelhouse_population_protocol()

    assert protocol["status"] == "VERIFIED"
    assert protocol["manual_copy_required"] is False
    assert protocol["install_forbidden"] is True
    assert protocol["source"] == "external_only"
    assert protocol["no_download"] is True
    assert protocol["no_pip"] is True
    assert all(item["source"] == "external_only" for item in protocol["wheels"])


def test_wheelhouse_population_protocol_artifacts(tmp_path: Path) -> None:
    artifacts = write_wheelhouse_population_protocol_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"190_wheelhouse_population_protocol.json", "191_wheelhouse_population_protocol.md"}
    payload = json.loads((tmp_path / "190_wheelhouse_population_protocol.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.1"
