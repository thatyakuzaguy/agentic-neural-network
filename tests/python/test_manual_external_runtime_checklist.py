from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_manual_external_runtime_checklist,
    write_manual_external_runtime_checklist_artifacts,
)


def test_manual_external_runtime_checklist_verified_after_runtime_materialization() -> None:
    checklist = build_manual_external_runtime_checklist()

    assert checklist["status"] == "VERIFIED"
    assert len(checklist["steps"]) == 5
    assert checklist["no_auto_execute"] is True
    assert checklist["no_install"] is True
    assert checklist["no_download"] is True
    assert checklist["no_inference"] is True


def test_manual_external_runtime_checklist_artifacts(tmp_path: Path) -> None:
    artifacts = write_manual_external_runtime_checklist_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"196_manual_external_runtime_checklist.json", "197_manual_external_runtime_checklist.md"}
    payload = json.loads((tmp_path / "196_manual_external_runtime_checklist.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.3"
