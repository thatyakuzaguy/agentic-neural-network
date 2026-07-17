from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_alpha_manual_validation_checklist,
    write_alpha_manual_validation_checklist_artifacts,
)


def test_alpha_manual_validation_checklist_contains_safety_items() -> None:
    checklist = build_alpha_manual_validation_checklist()
    ids = {item["id"] for item in checklist["checks"]}

    assert checklist["status"] == "MANUAL_VALIDATION_REQUIRED"
    assert "desktop_starts" in ids
    assert "runtime_checks" in ids
    assert "installer_dry_run" in ids
    assert "safe_mode" in ids
    assert "no_internet" in ids
    assert "no_downloads" in ids
    assert "no_model_modification" in ids
    assert "no_training" in ids
    assert "no_git_modifications" in ids
    assert "no_c_access" in ids
    assert "sequential_runtime" in ids
    assert "launch_guard" in ids
    assert "model_inventory" in ids
    assert "project_builder" in ids
    assert "consensus" in ids
    assert checklist["qwen2_5_blocked"] is True
    assert checklist["powerful_blocked"] is True


def test_alpha_manual_validation_checklist_artifacts(tmp_path: Path) -> None:
    artifacts = write_alpha_manual_validation_checklist_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "166_alpha_manual_validation_checklist.json",
        "167_alpha_manual_validation_checklist.md",
    }
    payload = json.loads((tmp_path / "166_alpha_manual_validation_checklist.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.3"
