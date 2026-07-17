from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_embedded_runtime_verification,
    write_embedded_runtime_verification_artifacts,
)


def test_embedded_runtime_verification_ready_after_wheelhouse_materialization() -> None:
    verification = build_embedded_runtime_verification()

    assert verification["status"] == "VERIFICATION_READY"
    assert verification["blockers"] == []
    assert verification["no_execution"] is True
    assert verification["no_pip"] is True
    assert verification["no_model_load"] is True


def test_embedded_runtime_verification_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_runtime_verification_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"182_embedded_runtime_verification.json", "183_embedded_runtime_verification.md"}
    payload = json.loads((tmp_path / "182_embedded_runtime_verification.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.8"
