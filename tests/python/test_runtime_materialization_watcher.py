from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_runtime_materialization_watcher,
    write_runtime_materialization_watcher_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _d_drive_test_root(name: str) -> Path:
    root = REPO_ROOT / "outputs" / "test_runtime_materialization_watcher" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def test_runtime_materialization_watcher_reports_current_runtime_state() -> None:
    watcher = build_runtime_materialization_watcher()

    assert watcher["status"] == "READY"
    assert watcher["python_found"] is True
    assert watcher["wheelhouse_count"] > 0
    assert watcher["hash_verification_status"] == "VERIFIED"
    assert watcher["no_python_execution"] is True
    assert watcher["no_install"] is True


def test_runtime_materialization_watcher_partial(tmp_path: Path) -> None:
    root = _d_drive_test_root(tmp_path.name) / "runtime"
    (root / "python").mkdir(parents=True)

    watcher = build_runtime_materialization_watcher(root)

    assert watcher["status"] == "PARTIAL"
    assert watcher["missing_folders"]
    assert watcher["python_found"] is False


def test_runtime_materialization_watcher_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_materialization_watcher_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"210_runtime_materialization_watcher.json", "211_runtime_materialization_watcher.md"}
    payload = json.loads((tmp_path / "210_runtime_materialization_watcher.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.9"
