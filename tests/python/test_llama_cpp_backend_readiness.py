from __future__ import annotations

import importlib.util
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    diagnose_llama_cpp_backend,
    write_llama_cpp_backend_readiness_artifacts,
)


def test_llama_cpp_import_missing_reports_unavailable(monkeypatch) -> None:
    original = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object):
        if name == "llama_cpp":
            return None
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    readiness = diagnose_llama_cpp_backend()

    assert readiness["status"] in {"UNAVAILABLE", "MODEL_MISSING"}
    assert readiness["binding_importable"] is False
    assert "llama_cpp_binding_unavailable" in readiness["blocking_reasons"]


def test_llama_cpp_readiness_artifacts_110_111(tmp_path: Path) -> None:
    artifacts = write_llama_cpp_backend_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "110_llama_cpp_backend_readiness.json",
        "111_llama_cpp_backend_readiness.md",
    }


def test_llama_cpp_readiness_reports_qwen25_model_metadata() -> None:
    readiness = diagnose_llama_cpp_backend()

    assert readiness["model_name"] == "qwen2_5_coder_7b_v5"
    assert readiness["backend"] == "llama_cpp"
    assert readiness["model_path"].replace("\\", "/").endswith("models/qwen2.5-coder-7b-q4_k_m.gguf")
    assert readiness["model_path_c_drive"] is False
