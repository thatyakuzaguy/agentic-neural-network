from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_clean_machine_validation_plan,
    write_clean_machine_validation_plan_artifacts,
)


def test_clean_machine_validation_plan_includes_release_safety_checks() -> None:
    plan = build_clean_machine_validation_plan()
    ids = {item["id"] for item in plan["checklist"]}

    assert plan["status"] == "PLAN_ONLY"
    assert plan["target_install_root"] == "D:\\ANN"
    assert "no_c_root" in ids
    assert "uninstaller_preserves_data" in ids
    assert "no_real_model_load_by_default" in ids
    assert plan["acceptance"]["no_internet"] is True


def test_clean_machine_validation_plan_artifacts(tmp_path: Path) -> None:
    artifacts = write_clean_machine_validation_plan_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"150_clean_machine_validation_plan.json", "151_clean_machine_validation_plan.md"}
    payload = json.loads((tmp_path / "150_clean_machine_validation_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.6"
