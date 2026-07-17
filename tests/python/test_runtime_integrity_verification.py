from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_runtime_integrity_verification,
    write_runtime_integrity_verification_artifacts,
)


def test_runtime_integrity_verification_ready_after_wheelhouse_hashes_exist() -> None:
    integrity = build_runtime_integrity_verification()

    assert integrity["status"] == "INTEGRITY_VERIFIED"
    assert integrity["blockers"] == []
    assert integrity["no_python_execution"] is True
    assert integrity["no_wheel_execution"] is True


def test_runtime_integrity_verification_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_integrity_verification_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"198_runtime_integrity_verification.json", "199_runtime_integrity_verification.md"}
    payload = json.loads((tmp_path / "198_runtime_integrity_verification.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.4"
