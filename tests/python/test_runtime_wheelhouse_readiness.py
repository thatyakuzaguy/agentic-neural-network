from __future__ import annotations

import shutil
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_runtime_wheelhouse_readiness


REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_test_root(name: str) -> Path:
    root = REPO_ROOT / "outputs" / "test_runtime_wheelhouse_readiness" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_runtime_wheelhouse_readiness_empty_default() -> None:
    readiness = build_runtime_wheelhouse_readiness()

    assert readiness["status"] in {"EMPTY", "PARTIAL", "READY"}
    assert readiness["no_wheel_execution"] is True
    assert readiness["no_install"] is True
    assert readiness["no_download"] is True
    assert readiness["model_load_attempted"] is False
    assert readiness["real_inference_attempted"] is False


def test_runtime_wheelhouse_readiness_ready_when_wheelhouse_verified(monkeypatch, tmp_path: Path) -> None:
    root = _repo_test_root(tmp_path.name) / "runtime"
    (root / "wheels").mkdir(parents=True)
    (root / "wheels" / "pkg-1.0-py3-none-any.whl").write_text("wheel", encoding="utf-8")

    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY", "wheelhouse_count": 1},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_wheelhouse_external_validation",
        lambda _path=None: {"status": "VERIFIED", "wheels": []},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_wheelhouse_integrity_registry",
        lambda _path=None: {"status": "HASH_VERIFIED"},
    )
    monkeypatch.setattr(
        "agentic_network.runtime_engine.local_model_activation.build_runtime_integrity_verification",
        lambda _root=None: {"status": "INTEGRITY_VERIFIED"},
    )

    readiness = build_runtime_wheelhouse_readiness(root)

    assert readiness["status"] == "READY"
    assert readiness["ready"] is True
    assert readiness["wheelhouse_count"] == 1
