from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_external_runtime_matrix,
    write_external_runtime_matrix_artifacts,
)


def test_external_runtime_matrix_handles_incomplete_environment() -> None:
    matrix = build_external_runtime_matrix()

    assert matrix["status"] in {"ENVIRONMENT_INCOMPLETE", "READY_FOR_REAL_INFERENCE"}
    assert matrix["current_python_executable"]
    assert "torch" in matrix["package_status"]
    assert "llama_cpp" in matrix["package_status"]
    assert matrix["supports"]["qwen3_hf_safetensors"] in {True, False}
    assert matrix["qwen3"]["loaded"] is False
    assert matrix["deepseek"]["powerful_activated"] is False
    assert matrix["active_models"] == 0
    assert matrix["parallel_llm_loads"] == 0


def test_external_runtime_matrix_writes_artifacts(tmp_path: Path) -> None:
    artifacts = write_external_runtime_matrix_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"130_external_runtime_matrix.json", "131_external_runtime_matrix.md"}
    payload = json.loads((tmp_path / "130_external_runtime_matrix.json").read_text(encoding="utf-8"))
    assert payload["version"] == "13.9"
