from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import probe_runtime_memory, write_runtime_memory_probe_artifacts


def test_runtime_memory_probe_does_not_require_cuda() -> None:
    probe = probe_runtime_memory()

    assert probe["status"] in {"AVAILABLE", "cuda_unavailable", "torch_unavailable"}
    assert probe["no_model_loaded"] is True
    assert probe["active_models"] == 0
    assert probe["parallel_llm_loads"] == 0


def test_runtime_memory_probe_artifacts_114_115(tmp_path: Path) -> None:
    artifacts = write_runtime_memory_probe_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "114_runtime_memory_probe.json",
        "115_runtime_memory_probe.md",
    }
