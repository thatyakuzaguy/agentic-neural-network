from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import run_controlled_first_real_inference


def test_runtime_real_benchmark_artifact_blocked(tmp_path: Path) -> None:
    run_controlled_first_real_inference(output_dir=tmp_path)
    benchmark = json.loads((tmp_path / "216_runtime_benchmark_real.json").read_text(encoding="utf-8"))

    assert benchmark["version"] == "17.1"
    assert benchmark["status"] == "SKIPPED_NO_REAL_LOAD"
    assert benchmark["loaded_models_after"] == []
    assert benchmark["parallel_llm_loads"] == 0
