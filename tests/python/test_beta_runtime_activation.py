from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_beta_runtime_activation,
    write_beta_runtime_activation_artifacts,
)


def test_beta_runtime_activation_blocked() -> None:
    activation = build_beta_runtime_activation()

    assert activation["status"] == "BETA_BLOCKED"
    assert activation["qwen2_5_only"] is True
    assert activation["fast_only"] is True
    assert activation["qwen3_blocked"] is True
    assert activation["deepseek_blocked"] is True
    assert activation["powerful_blocked"] is True
    assert activation["parallel_llm_loads"] == 0


def test_beta_runtime_activation_ready(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    (root / "python").mkdir(parents=True)
    (root / "python" / "python.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY", "hash_verification_status": "VERIFIED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_integrity_verification",
        lambda _root=None: {"status": "INTEGRITY_VERIFIED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_installer_rc_readiness",
        lambda: {"status": "RC_READY"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_real_inference_launch_guard",
        lambda **_kwargs: {"status": "PASSED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_controlled_first_inference_gate",
        lambda *_args, **_kwargs: {"status": "READY_FOR_CONTROLLED_SMOKE"},
    )

    activation = build_beta_runtime_activation(root)

    assert activation["status"] == "BETA_READY"
    assert activation["blockers"] == []


def test_beta_runtime_activation_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_runtime_activation_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"212_beta_runtime_activation.json", "213_beta_runtime_activation.md"}
    payload = json.loads((tmp_path / "212_beta_runtime_activation.json").read_text(encoding="utf-8"))
    assert payload["version"] == "17.0"
