from __future__ import annotations

import shutil
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_embedded_python_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_test_root(name: str) -> Path:
    root = REPO_ROOT / "outputs" / "test_embedded_python_evidence" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_embedded_python_evidence_reports_safe_default_state() -> None:
    evidence = build_embedded_python_evidence()

    assert evidence["status"] in {"MISSING", "PARTIAL", "READY"}
    assert evidence["python_execution_attempted"] is False
    assert evidence["no_python_execution"] is True
    assert evidence["no_install"] is True
    assert evidence["model_load_attempted"] is False
    assert evidence["real_inference_attempted"] is False
    assert evidence["safety"]["model_load"] is False
    assert evidence["safety"]["inference"] is False


def test_embedded_python_evidence_ready_with_existing_python_exe(tmp_path: Path) -> None:
    root = _repo_test_root(tmp_path.name) / "runtime"
    (root / "python").mkdir(parents=True)
    (root / "python" / "python.exe").write_text("", encoding="utf-8")

    evidence = build_embedded_python_evidence(root)

    assert evidence["status"] == "READY"
    assert evidence["ready"] is True
    assert evidence["embedded_python_version"] == "not_executed"
