from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_embedded_runtime_beta_candidate,
    write_beta_candidate_macro_artifacts,
    write_embedded_runtime_beta_candidate_artifacts,
)


def test_embedded_runtime_beta_candidate_ready_after_verified_runtime() -> None:
    candidate = build_embedded_runtime_beta_candidate()

    assert candidate["status"] == "BETA_CANDIDATE_READY"
    assert candidate["beta_candidate"] is True
    assert candidate["blockers"] == []
    assert candidate["embedded_python_present"] is True
    assert candidate["runtime_verified"] is True
    assert candidate["installer_compatible"] is True
    assert candidate["no_install"] is True
    assert candidate["no_model_load"] is True


def test_embedded_runtime_beta_candidate_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_runtime_beta_candidate_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"192_embedded_runtime_beta_candidate.json", "193_embedded_runtime_beta_candidate.md"}
    payload = json.loads((tmp_path / "192_embedded_runtime_beta_candidate.json").read_text(encoding="utf-8"))
    assert payload["version"] == "16.2"


def test_beta_candidate_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_candidate_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "188_external_runtime_materialization.json",
        "189_external_runtime_materialization.md",
        "190_wheelhouse_population_protocol.json",
        "191_wheelhouse_population_protocol.md",
        "192_embedded_runtime_beta_candidate.json",
        "193_embedded_runtime_beta_candidate.md",
        "194_first_real_inference_readiness.json",
        "195_first_real_inference_readiness.md",
    } == names
