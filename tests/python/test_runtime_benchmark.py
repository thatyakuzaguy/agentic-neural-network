from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_runtime_benchmark, write_runtime_benchmark_artifacts


def test_runtime_benchmark_skips_when_no_real_load() -> None:
    benchmark = build_runtime_benchmark()

    assert benchmark["status"] == "SKIPPED_NO_REAL_LOAD"
    assert benchmark["loaded_models_during"] == []
    assert benchmark["parallel_llm_loads"] == 0


def test_runtime_benchmark_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_benchmark_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"124_runtime_benchmark.json", "125_runtime_benchmark.md"}
    payload = json.loads((tmp_path / "124_runtime_benchmark.json").read_text(encoding="utf-8"))
    assert payload["status"] == "SKIPPED_NO_REAL_LOAD"
