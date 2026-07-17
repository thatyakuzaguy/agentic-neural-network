from __future__ import annotations

import json
from pathlib import Path

import agentic_network.runtime_engine.local_model_activation as activation


def test_cuda_environment_reports_read_only_status() -> None:
    result = activation.diagnose_cuda_environment()

    assert result["status"] in {
        "torch_unavailable",
        "cuda_probe_error",
        "cuda_unavailable",
        "gpu_unavailable",
        "cuda_available",
    }
    assert result["active_models"] == 0
    assert result["parallel_llm_loads"] == 0
    assert result["safety"]["downloads"] is False
    assert result["safety"]["modify_models"] is False


def test_cuda_environment_handles_missing_torch(monkeypatch) -> None:
    original_find_spec = activation.importlib.util.find_spec

    def _find_spec(name: str):
        if name == "torch":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(activation.importlib.util, "find_spec", _find_spec)

    result = activation.diagnose_cuda_environment()

    assert result["status"] == "torch_unavailable"
    assert result["torch_importable"] is False
    assert result["cuda_available"] is False


def test_cuda_environment_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_cuda_environment_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"118_cuda_environment.json", "119_cuda_environment.md"}
    payload = json.loads((tmp_path / "118_cuda_environment.json").read_text(encoding="utf-8"))
    assert payload["version"] == "13.5"
