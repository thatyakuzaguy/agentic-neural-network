from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import build_runtime_materialization_watcher


def _make_runtime(root: Path) -> Path:
    runtime = root / "mnt" / "d" / "ANN" / "runtime"
    for name in ("python", "wheels", "checks", "audit", "site-packages", "requirements-lock"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    return runtime


def test_windows_runtime_path_resolves_to_wsl_mount(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "_is_wsl", lambda: True)
    monkeypatch.setenv("ANN_WSL_MOUNT_ROOT", str(tmp_path / "mnt"))

    info = activation._runtime_path_info("D:/ANN/runtime")

    assert info["display"] == "D:/ANN/runtime"
    assert info["path"] == tmp_path / "mnt" / "d" / "ANN" / "runtime"
    assert info["blocked"] is False


def test_wsl_runtime_path_keeps_wsl_form(monkeypatch) -> None:
    monkeypatch.setattr(activation, "_is_wsl", lambda: True)

    info = activation._runtime_path_info("/mnt/d/ANN/runtime")

    assert info["display"] == "D:/ANN/runtime"
    assert info["path"] == Path("/mnt/d/ANN/runtime")
    assert info["blocked"] is False


def test_c_drive_runtime_path_stays_blocked(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "_is_wsl", lambda: True)
    monkeypatch.setenv("ANN_WSL_MOUNT_ROOT", str(tmp_path / "mnt"))

    watcher = build_runtime_materialization_watcher("C:/ANN/runtime")

    assert watcher["status"] == "INVALID"
    assert "runtime_path_c_drive_blocked" in watcher["errors"]
    assert watcher["no_python_execution"] is True
    assert watcher["no_install"] is True


def test_watcher_detects_existing_wsl_runtime_from_windows_path(monkeypatch, tmp_path: Path) -> None:
    _make_runtime(tmp_path)
    monkeypatch.setattr(activation, "_is_wsl", lambda: True)
    monkeypatch.setenv("ANN_WSL_MOUNT_ROOT", str(tmp_path / "mnt"))

    before = get_loaded_models()
    watcher = build_runtime_materialization_watcher("D:/ANN/runtime")

    assert watcher["status"] == "PARTIAL"
    assert watcher["runtime_root"] == "D:/ANN/runtime"
    assert watcher["resolved_runtime_root"] == str(tmp_path / "mnt" / "d" / "ANN" / "runtime")
    assert watcher["missing_folders"] == []
    assert watcher["python_found"] is False
    assert watcher["wheelhouse_count"] == 0
    assert watcher["no_python_execution"] is True
    assert watcher["no_install"] is True
    assert watcher["safety"]["model_load"] is False
    assert watcher["safety"]["inference"] is False
    assert get_loaded_models() == before == []
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0
