from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics


def _ready_external_bridge() -> dict[str, object]:
    return {
        "status": "EXTERNAL_RUNTIME_READY",
        "runtime_type": "external_conda",
        "is_embedded_runtime": False,
        "final_release_runtime": False,
        "qwen25_gguf_exists": True,
        "qwen25_model_resolved_path": "/mnt/d/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf",
        "llama_cpp_importable": True,
        "torch_cuda_available": True,
    }


def test_external_runtime_smoke_readiness_ready(monkeypatch) -> None:
    monkeypatch.setattr(activation, "build_external_verified_runtime_bridge", _ready_external_bridge)

    readiness = activation.build_external_runtime_smoke_readiness()

    assert readiness["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    assert readiness["runtime_type"] == "external_conda"
    assert readiness["is_embedded_runtime"] is False
    assert readiness["final_release_runtime"] is False
    assert readiness["button_label"] == "External Runtime Smoke"
    assert readiness["qwen3_blocked"] is True
    assert readiness["deepseek_blocked"] is True
    assert readiness["powerful_blocked"] is True
    assert readiness["model_load_attempted"] is False
    assert readiness["real_inference_attempted"] is False
    assert get_loaded_models() == []
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_first_real_smoke_preparation_allows_external_without_finalizing_embedded(monkeypatch) -> None:
    monkeypatch.setattr(
        activation,
        "build_embedded_python_evidence",
        lambda _root=None: {"status": "PARTIAL"},
    )
    monkeypatch.setattr(
        activation,
        "build_runtime_wheelhouse_readiness",
        lambda _root=None: {"status": "EMPTY"},
    )
    monkeypatch.setattr(
        activation,
        "build_real_inference_launch_guard",
        lambda **_kwargs: {"status": "BLOCKED"},
    )
    monkeypatch.setattr(
        activation,
        "build_qwen25_smoke_button_gate",
        lambda _root=None: {"status": "EXTERNAL_RUNTIME_SMOKE_READY"},
    )
    monkeypatch.setattr(
        activation,
        "build_controlled_first_inference_gate",
        lambda *_args, **_kwargs: {"status": "NOT_READY"},
    )
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {
            "status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL",
            "external_runtime": {"status": "EXTERNAL_RUNTIME_READY"},
        },
    )
    monkeypatch.setattr(
        activation,
        "build_first_real_inference_live_status",
        lambda _root=None: {"status": "NOT_READY"},
    )

    readiness = activation.build_first_real_smoke_preparation()

    assert readiness["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    assert readiness["external_runtime_allowed_for_qwen25_smoke"] is True
    assert readiness["embedded_runtime_finalization_satisfied"] is False
    assert readiness["model_load_attempted"] is False
    assert readiness["real_inference_attempted"] is False


def test_external_runtime_bridge_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "build_external_verified_runtime_bridge", _ready_external_bridge)
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda: {"version": "18.2", "status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"},
    )

    artifacts = activation.write_external_verified_runtime_bridge_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "250_external_verified_runtime_bridge.json",
        "251_external_verified_runtime_bridge.md",
        "252_external_runtime_smoke_readiness.json",
        "253_external_runtime_smoke_readiness.md",
    }
    payload = json.loads((tmp_path / "252_external_runtime_smoke_readiness.json").read_text(encoding="utf-8"))
    assert payload["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"

