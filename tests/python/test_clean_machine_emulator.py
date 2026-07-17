from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_clean_machine_emulator,
    write_clean_machine_emulator_artifacts,
)


def test_clean_machine_emulator_reports_blockers() -> None:
    emulator = build_clean_machine_emulator()

    assert emulator["status"] in {"CLEAN_MACHINE_BLOCKED", "CLEAN_MACHINE_EMULATED_WITH_WARNINGS"}
    if emulator["status"] == "CLEAN_MACHINE_BLOCKED":
        assert emulator["blockers"]
    else:
        assert emulator["warnings"]
    assert emulator["dry_run"] is True
    assert emulator["no_install"] is True
    assert emulator["no_model_load"] is True
    assert emulator["no_inference"] is True


def test_clean_machine_emulator_artifacts(tmp_path: Path) -> None:
    artifacts = write_clean_machine_emulator_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"172_clean_machine_emulator.json", "173_clean_machine_emulator.md"}
    payload = json.loads((tmp_path / "172_clean_machine_emulator.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.6"
