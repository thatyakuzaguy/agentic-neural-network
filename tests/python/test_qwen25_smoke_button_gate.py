from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_qwen25_smoke_button_gate,
    write_qwen25_smoke_button_gate_artifacts,
)


def test_smoke_button_disabled_on_backend_after_runtime_ready() -> None:
    gate = build_qwen25_smoke_button_gate()
    blockers = {item["id"] for item in gate["blockers"]}

    assert gate["status"] in {"BUTTON_DISABLED", "EXTERNAL_RUNTIME_SMOKE_READY"}
    assert gate["button_enabled"] == (gate["status"] == "EXTERNAL_RUNTIME_SMOKE_READY")
    assert "runtime_materialized" not in blockers
    assert "wheelhouse_verified" not in blockers
    assert blockers.intersection({"llama_cpp_ready", "qwen25_backend_ready"})
    assert gate["qwen3_blocked"] is True
    assert gate["deepseek_blocked"] is True
    assert gate["powerful_blocked"] is True
    assert gate["model_load_attempted"] is False
    assert gate["real_inference_attempted"] is False


def test_smoke_button_ready_only_when_all_gates_pass(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    (root / "python").mkdir(parents=True)
    (root / "python" / "python.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_wheelhouse_external_validation",
        lambda _path=None: {"status": "VERIFIED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.diagnose_llama_cpp_real_status",
        lambda: {"status": "READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_controlled_first_inference_gate",
        lambda *_args, **_kwargs: {"status": "READY_FOR_CONTROLLED_SMOKE"},
    )

    gate = build_qwen25_smoke_button_gate(root)

    assert gate["status"] == "BUTTON_READY"
    assert gate["button_enabled"] is True
    assert gate["blockers"] == []


def test_smoke_button_gate_artifacts(tmp_path: Path) -> None:
    artifacts = write_qwen25_smoke_button_gate_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"220_qwen25_smoke_button_gate.json", "221_qwen25_smoke_button_gate.md"}
    payload = json.loads((tmp_path / "220_qwen25_smoke_button_gate.json").read_text(encoding="utf-8"))
    assert payload["version"] == "17.3"
