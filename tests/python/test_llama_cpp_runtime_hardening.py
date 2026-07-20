from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.security import harden_llama_cpp_runtime as hardener


def _fake_runtime(root: Path) -> None:
    (root / "python" / "Lib" / "site-packages" / "diskcache").mkdir(parents=True)
    (root / "python" / "Lib" / "site-packages" / "diskcache-5.6.3.dist-info").mkdir()
    (root / "python" / "python.exe").write_text("python", encoding="utf-8")
    (root / "wheels").mkdir()
    (root / "wheels" / "diskcache-5.6.3-py3-none-any.whl").write_bytes(b"wheel")
    for relative in hardener.JSON_EVIDENCE:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": "18.9.19",
                    "packages": [{"name": "diskcache"}, {"name": "llama-cpp-python"}],
                    "wheels": [{"name": "diskcache"}, {"name": "llama-cpp-python"}],
                    "wheel_count": 2,
                    "installed_distributions": {"diskcache": "5.6.3"},
                    "allowed_distributions": ["diskcache", "llama-cpp-python"],
                }
            ),
            encoding="utf-8",
        )


def test_hardening_removes_distribution_wheel_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    _fake_runtime(runtime)
    monkeypatch.setattr(hardener, "_validate_runtime", lambda _root: {"status": "PASSED"})

    report = hardener.apply_hardening(
        runtime,
        output_dir=tmp_path / "evidence",
        allow_test_root=True,
    )

    assert report["status"] == "HARDENED"
    assert hardener.vulnerable_paths(runtime) == []
    lock = json.loads((runtime / hardener.JSON_EVIDENCE[0]).read_text(encoding="utf-8"))
    assert lock["version"] == "18.9.20"
    assert [entry["name"] for entry in lock["packages"]] == ["llama-cpp-python"]
    assert lock["wheel_count"] == 1
    assert lock["security"]["diskcache_distribution_present"] is False
    assert (tmp_path / "evidence" / "diskcache_removal_report.json").is_file()


def test_hardening_rolls_back_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    _fake_runtime(runtime)
    original = (runtime / hardener.JSON_EVIDENCE[0]).read_bytes()
    monkeypatch.setattr(hardener, "_validate_runtime", lambda _root: {"status": "FAILED"})

    with pytest.raises(RuntimeError, match="validation failed"):
        hardener.apply_hardening(
            runtime,
            output_dir=tmp_path / "evidence",
            allow_test_root=True,
        )

    assert hardener.vulnerable_paths(runtime)
    assert (runtime / hardener.JSON_EVIDENCE[0]).read_bytes() == original


def test_production_hardener_rejects_arbitrary_runtime_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="restricted"):
        hardener.build_plan(tmp_path)
