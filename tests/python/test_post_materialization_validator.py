from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_post_materialization_validator,
    write_post_materialization_validator_artifacts,
)


def test_post_materialization_validator_validated_after_hashes_and_runtime_ready() -> None:
    validator = build_post_materialization_validator()

    assert validator["status"] == "VALIDATED"
    assert "embedded_python" not in validator["missing"]
    assert validator["layout_valid"] is True
    assert validator["hashes_checked"] is True
    assert validator["runtime_compatible"] is True
    assert validator["no_python_execution"] is True
    assert validator["no_wheel_import"] is True
    assert validator["no_runtime_execution"] is True


def test_post_materialization_validator_artifacts(tmp_path: Path) -> None:
    artifacts = write_post_materialization_validator_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"204_post_materialization_validator.json", "205_post_materialization_validator.md"}
    payload = json.loads((tmp_path / "204_post_materialization_validator.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.6"
