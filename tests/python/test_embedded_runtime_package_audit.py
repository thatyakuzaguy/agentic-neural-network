from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_embedded_runtime_package_audit_blocks_without_python(tmp_path: Path) -> None:
    audit = activation.build_embedded_runtime_package_audit(tmp_path, execute_imports=False)

    assert audit["status"] == "PACKAGE_AUDIT_BLOCKED"
    assert audit["python_found"] is False
    assert audit["model_load_attempted"] is False
    assert audit["real_inference_attempted"] is False
    assert audit["no_install"] is True
    assert audit["no_download"] is True


def test_embedded_runtime_package_audit_uses_subprocess_without_shell(monkeypatch, tmp_path: Path) -> None:
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    python_exe = python_dir / "python.exe"
    python_exe.write_text("", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        payload = {
            "packages": {
                "PySide6": {"importable": True, "version": "6.0", "error": ""},
                "torch": {"importable": True, "version": "2.0", "error": ""},
                "llama_cpp": {"importable": False, "version": "", "error": "missing"},
                "transformers": {"importable": True, "version": "4.0", "error": ""},
            }
        }
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(activation.subprocess, "run", fake_run)
    activation._EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE.clear()

    audit = activation.build_embedded_runtime_package_audit(tmp_path)

    assert audit["status"] == "PACKAGE_AUDIT_INCOMPLETE"
    assert audit["missing_packages"] == ["llama_cpp"]
    assert calls
    assert calls[0]["args"][0][0] == str(python_exe)
    assert calls[0]["kwargs"].get("shell") is None
    assert calls[0]["kwargs"]["check"] is False


def test_embedded_runtime_package_audit_does_not_cache_failed_probe(monkeypatch, tmp_path: Path) -> None:
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    (python_dir / "python.exe").write_text("", encoding="utf-8")
    activation._EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE.clear()
    calls = 0

    def fail_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError("temporary probe failure")

    monkeypatch.setattr(activation.subprocess, "run", fail_run)
    failed = activation.build_embedded_runtime_package_audit(tmp_path)

    def pass_run(*args, **_kwargs):
        nonlocal calls
        calls += 1
        payload = {
            "packages": {
                "PySide6": {"importable": True, "version": "6.0", "error": ""},
                "torch": {"importable": True, "version": "2.0", "error": ""},
                "llama_cpp": {"importable": True, "version": "0.3", "error": ""},
                "transformers": {"importable": True, "version": "4.0", "error": ""},
            }
        }
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(activation.subprocess, "run", pass_run)
    passed = activation.build_embedded_runtime_package_audit(tmp_path)

    assert failed["status"] == "PACKAGE_AUDIT_INCOMPLETE"
    assert passed["status"] == "PACKAGE_AUDIT_READY"
    assert calls == 2


def test_embedded_runtime_package_audit_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_embedded_runtime_package_audit",
        lambda *_args, **_kwargs: {"status": "PACKAGE_AUDIT_INCOMPLETE"},
    )

    artifacts = activation.write_embedded_runtime_package_audit_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "352_embedded_runtime_package_audit.json",
        "353_embedded_runtime_package_audit.md",
    }
