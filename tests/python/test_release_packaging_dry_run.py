from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_release_packaging_dry_run,
    write_release_packaging_dry_run_artifacts,
)


def test_release_packaging_dry_run_does_not_copy_models() -> None:
    dry_run = build_release_packaging_dry_run()

    assert dry_run["status"] == "DRY_RUN_READY"
    assert dry_run["builds_exe"] is False
    assert dry_run["copies_models"] is False
    assert dry_run["copies_datasets"] is False
    assert dry_run["copies_adapters"] is False
    assert dry_run["planned_protected_copies"] == []
    assert "D:\\ANN\\models" in dry_run["target_dirs"]


def test_release_packaging_dry_run_artifacts(tmp_path: Path) -> None:
    artifacts = write_release_packaging_dry_run_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"156_release_packaging_dry_run.json", "157_release_packaging_dry_run.md"}
    payload = json.loads((tmp_path / "156_release_packaging_dry_run.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.8"
