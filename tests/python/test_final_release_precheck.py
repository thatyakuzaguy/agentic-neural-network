from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_final_release_precheck,
    write_real_runtime_preparation_macro_artifacts,
)


def test_final_release_precheck_default_is_non_executing() -> None:
    precheck = build_final_release_precheck()

    assert precheck["status"] in {"PRECHECK_BLOCKED", "PRECHECK_READY", "FINAL_RELEASE_READY"}
    assert precheck["model_load_attempted"] is False
    assert precheck["real_inference_attempted"] is False
    assert precheck["no_internet"] is True
    assert precheck["no_downloads"] is True
    assert precheck["no_installs"] is True
    assert precheck["models_modified"] is False
    assert precheck["datasets_modified"] is False
    assert precheck["adapters_modified"] is False


def test_final_release_precheck_ready_when_all_reused_gates_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_embedded_python_evidence",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_wheelhouse_readiness",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_first_real_smoke_preparation",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_qwen3_runtime_bridge",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_deepseek_powerful_bridge",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_guided_runtime_activation_state",
        lambda _root=None: {"status": "GUIDED_READY_FOR_SMOKE"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_installer_final_readiness",
        lambda _root=None: {"status": "INSTALLER_FINAL_READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_public_release_bridge_final",
        lambda _root=None: {"status": "FINAL_RELEASE_READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_ann_finalization_megaphase",
        lambda _root=None: {"status": "FINAL_RELEASE_READY"},
    )

    precheck = build_final_release_precheck()

    assert precheck["status"] == "FINAL_RELEASE_READY"
    assert precheck["blockers"] == []


def test_real_runtime_preparation_macro_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    for function_name, payload in {
        "build_embedded_python_evidence": {"version": "17.5", "status": "PARTIAL"},
        "build_runtime_wheelhouse_readiness": {"version": "17.6", "status": "EMPTY"},
        "build_first_real_smoke_preparation": {
            "version": "17.6",
            "status": "BLOCKED",
            "real_inference_attempted": False,
        },
        "build_qwen3_runtime_bridge": {"version": "17.7", "status": "BLOCKED"},
        "build_deepseek_powerful_bridge": {"version": "17.7", "status": "BLOCKED"},
        "build_final_release_precheck": {
            "version": "17.8",
            "status": "PRECHECK_BLOCKED",
            "real_inference_attempted": False,
        },
    }.items():
        monkeypatch.setattr(f"agentic_network.runtime_engine.local_model_activation.{function_name}", lambda _payload=payload: _payload)

    artifacts = write_real_runtime_preparation_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "232_embedded_python_evidence.json",
        "233_embedded_python_evidence.md",
        "234_runtime_wheelhouse_readiness.json",
        "235_runtime_wheelhouse_readiness.md",
        "236_first_real_smoke_preparation.json",
        "237_first_real_smoke_preparation.md",
        "238_qwen3_runtime_bridge.json",
        "239_qwen3_runtime_bridge.md",
        "240_deepseek_powerful_bridge.json",
        "241_deepseek_powerful_bridge.md",
        "242_final_release_precheck.json",
        "243_final_release_precheck.md",
    }
    payload = json.loads((tmp_path / "242_final_release_precheck.json").read_text(encoding="utf-8"))
    assert payload["version"] == "17.8"
    assert payload["real_inference_attempted"] is False
