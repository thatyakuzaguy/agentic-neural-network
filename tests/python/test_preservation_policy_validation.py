from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_preservation_policy_validation,
    write_preservation_policy_validation_artifacts,
)


def test_preservation_policy_keeps_user_data_and_removes_temp() -> None:
    policy = build_preservation_policy_validation()
    preserve = {item["name"]: item for item in policy["preserve"]}
    remove = {item["name"]: item for item in policy["remove"]}

    assert policy["status"] == "VALIDATED_WITH_WARNINGS" or policy["status"] == "VALIDATED"
    for name in ("models", "projects", "outputs", "data", "logs"):
        assert preserve[name]["status"] == "PASS"
    for name in ("cache", "wheelhouse_temp", "smoke_temp", "installer_temp"):
        assert remove[name]["status"] == "PASS"


def test_preservation_policy_artifacts(tmp_path: Path) -> None:
    artifacts = write_preservation_policy_validation_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "158_preservation_policy_validation.json",
        "159_preservation_policy_validation.md",
    }
    payload = json.loads((tmp_path / "158_preservation_policy_validation.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.9"
