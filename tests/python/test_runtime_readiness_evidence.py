from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_runtime_readiness_evidence,
    write_runtime_readiness_evidence_artifacts,
)


def test_runtime_readiness_evidence_blocked() -> None:
    evidence = build_runtime_readiness_evidence()
    blockers = {item["id"] for item in evidence["blockers"]}

    assert evidence["status"] in {"NOT_READY", "PARTIAL"}
    assert "runtime_ready" not in blockers
    assert "wheelhouse_verified" not in blockers
    assert "launch_guard_ready" in blockers
    assert "embedded_python_detected" not in blockers
    assert evidence["safe_rollback_ready"] is True
    assert evidence["warnings"]
    assert evidence["next_manual_step"]


def test_runtime_readiness_evidence_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_readiness_evidence_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"206_runtime_readiness_evidence.json", "207_runtime_readiness_evidence.md"}
    payload = json.loads((tmp_path / "206_runtime_readiness_evidence.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.7"
