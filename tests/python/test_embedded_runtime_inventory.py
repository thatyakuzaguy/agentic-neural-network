from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_embedded_runtime_inventory,
    write_embedded_runtime_inventory_artifacts,
)


def test_embedded_runtime_inventory_reports_materialized_layout() -> None:
    inventory = build_embedded_runtime_inventory()

    assert inventory["status"] in {"INVENTORY_PARTIAL", "INVENTORY_READY"}
    assert inventory["present_count"] > 0
    if inventory["status"] == "INVENTORY_PARTIAL":
        assert inventory["missing_required"]
    assert inventory["no_model_load"] is True


def test_embedded_runtime_inventory_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_runtime_inventory_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"180_embedded_runtime_inventory.json", "181_embedded_runtime_inventory.md"}
    payload = json.loads((tmp_path / "180_embedded_runtime_inventory.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.8"
