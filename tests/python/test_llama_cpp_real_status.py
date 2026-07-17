from __future__ import annotations

import json
from pathlib import Path

import agentic_network.runtime_engine.local_model_activation as activation


def test_llama_cpp_real_status_is_non_instantiating() -> None:
    result = activation.diagnose_llama_cpp_real_status()

    assert result["status"] in {
        "READY",
        "UNAVAILABLE",
        "CPU_ONLY",
        "CUDA_AVAILABLE",
        "CUDA_UNKNOWN",
        "IMPORT_ERROR",
        "GPU_SUPPORT_UNKNOWN",
        "MODEL_READY_BACKEND_BLOCKED",
    }
    assert result["safe_load_configuration"]["instantiated"] is False
    assert result["safety"]["model_load"] is False


def test_llama_cpp_real_status_handles_missing_binding(monkeypatch) -> None:
    original_find_spec = activation.importlib.util.find_spec

    def _find_spec(name: str):
        if name == "llama_cpp":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(activation.importlib.util, "find_spec", _find_spec)

    result = activation.diagnose_llama_cpp_real_status()

    assert result["status"] == "UNAVAILABLE"
    assert result["binding_importable"] is False
    assert result["can_attempt_controlled_load"] is False


def test_llama_cpp_real_status_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_llama_cpp_real_status_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"120_llama_cpp_real_status.json", "121_llama_cpp_real_status.md"}
    payload = json.loads((tmp_path / "120_llama_cpp_real_status.json").read_text(encoding="utf-8"))
    assert payload["version"] == "13.5"
