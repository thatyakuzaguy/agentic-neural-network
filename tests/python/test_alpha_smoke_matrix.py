from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_alpha_smoke_matrix, write_alpha_smoke_matrix_artifacts


def test_alpha_smoke_matrix_contains_required_alpha_checks() -> None:
    matrix = build_alpha_smoke_matrix()
    ids = {item["id"] for item in matrix["tests"]}

    assert matrix["status"] == "ALPHA_READY_WITH_LIMITATIONS"
    assert matrix["beta"] == "BETA_BLOCKED"
    assert matrix["public_release"] == "PUBLIC_RELEASE_BLOCKED"
    assert "desktop_launch" in ids
    assert "first_run" in ids
    assert "project_builder" in ids
    assert "qwen25_detection" in ids
    assert "qwen3_preparation" in ids
    assert "deepseek_preparation" in ids
    assert "safe_mode" in ids
    assert "sequential_runtime" in ids
    assert matrix["qwen2_5_blocked"] is True
    assert matrix["powerful_blocked"] is True


def test_alpha_smoke_matrix_artifacts(tmp_path: Path) -> None:
    artifacts = write_alpha_smoke_matrix_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"162_alpha_smoke_matrix.json", "163_alpha_smoke_matrix.md"}
    payload = json.loads((tmp_path / "162_alpha_smoke_matrix.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.1"
