from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_backend_manual_readiness_checklist,
    write_backend_manual_readiness_checklist_artifacts,
)


def test_backend_manual_readiness_checklist_keeps_powerful_blocked() -> None:
    checklist = build_backend_manual_readiness_checklist()

    assert checklist["status"] in {"READY", "MANUAL_STEPS_REQUIRED"}
    assert checklist["qwen3"]["loaded"] is False
    assert checklist["deepseek"]["powerful_activated"] is False
    assert checklist["policy"]["vram_policy"] == "SEQUENTIAL"
    assert "environment_missing" in checklist["sections"]
    assert "user_manual_step_needed" in checklist["sections"]


def test_backend_manual_readiness_checklist_writes_artifacts(tmp_path: Path) -> None:
    artifacts = write_backend_manual_readiness_checklist_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "134_backend_manual_readiness_checklist.json",
        "135_backend_manual_readiness_checklist.md",
    }
    payload = json.loads((tmp_path / "134_backend_manual_readiness_checklist.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.0"
