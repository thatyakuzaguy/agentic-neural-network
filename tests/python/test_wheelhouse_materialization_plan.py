from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_wheelhouse_materialization_plan,
    write_wheelhouse_materialization_plan_artifacts,
)


def test_wheelhouse_materialization_plan_ready_after_wheels_and_hashes() -> None:
    plan = build_wheelhouse_materialization_plan()

    assert plan["status"] == "WHEELHOUSE_READY_FOR_BETA"
    assert plan["missing_wheels"] == []
    assert plan["missing_hashes"] == []
    assert plan["hash_pending"] is False
    assert plan["no_install_guarantee"] is True


def test_wheelhouse_materialization_plan_artifacts(tmp_path: Path) -> None:
    artifacts = write_wheelhouse_materialization_plan_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"170_wheelhouse_materialization_plan.json", "171_wheelhouse_materialization_plan.md"}
    payload = json.loads((tmp_path / "170_wheelhouse_materialization_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.5"
