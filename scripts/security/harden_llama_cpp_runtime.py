"""Transactionally remove DiskCache from an existing ANN embedded runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path("D:/ANN/runtime")
DEFAULT_OUTPUT = ROOT / "outputs" / "security" / "llama_cpp_diskcache_removal"
JSON_EVIDENCE = (
    Path("checks/ann_runtime_lock.json"),
    Path("audit/runtime_release_manifest.json"),
    Path("audit/runtime_release_validation.json"),
)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_runtime_root(path: Path, *, allow_test_root: bool = False) -> Path:
    resolved = path.resolve()
    if allow_test_root:
        return resolved
    if resolved != DEFAULT_RUNTIME.resolve():
        raise ValueError(f"Runtime hardening is restricted to {DEFAULT_RUNTIME}.")
    if resolved.drive.lower() != "d:":
        raise ValueError("Runtime hardening is restricted to drive D:.")
    return resolved


def vulnerable_paths(runtime_root: Path) -> list[Path]:
    site_packages = runtime_root / "python" / "Lib" / "site-packages"
    paths = [site_packages / "diskcache"]
    paths.extend(site_packages.glob("diskcache-*.dist-info"))
    paths.extend((runtime_root / "wheels").glob("diskcache*.whl"))
    return sorted({path.resolve() for path in paths if path.exists()}, key=str)


def _remove_named_entries(payload: dict[str, Any], key: str) -> None:
    entries = payload.get(key)
    if not isinstance(entries, list):
        return
    payload[key] = [
        entry
        for entry in entries
        if not (
            isinstance(entry, dict)
            and canonical_name(str(entry.get("name", ""))) == "diskcache"
        )
    ]


def harden_evidence(payload: dict[str, Any], relative_path: Path) -> dict[str, Any]:
    updated = json.loads(json.dumps(payload))
    _remove_named_entries(updated, "packages")
    _remove_named_entries(updated, "wheels")
    installed = updated.get("installed_distributions")
    if isinstance(installed, dict):
        for key in list(installed):
            if canonical_name(str(key)) == "diskcache":
                installed.pop(key)
    allowed = updated.get("allowed_distributions")
    if isinstance(allowed, list):
        updated["allowed_distributions"] = [
            value for value in allowed if canonical_name(str(value)) != "diskcache"
        ]
    if relative_path.name == "ann_runtime_lock.json":
        updated["version"] = "18.9.20"
    if isinstance(updated.get("wheels"), list):
        updated["wheel_count"] = len(updated["wheels"])
    updated["generated_at"] = now()
    updated["persistent_disk_cache_enabled"] = False
    updated["diskcache_distribution_installed"] = False
    updated["security"] = {
        "status": "HARDENED",
        "advisory_removed": "CVE-2025-69872",
        "diskcache_distribution_present": False,
        "llama_cpp_persistent_disk_cache": "disabled",
        "model_load_attempted": False,
        "inference_attempted": False,
    }
    return updated


def build_plan(runtime_root: Path = DEFAULT_RUNTIME, *, allow_test_root: bool = False) -> dict[str, Any]:
    root = assert_runtime_root(runtime_root, allow_test_root=allow_test_root)
    python_exe = root / "python" / "python.exe"
    evidence = [root / relative for relative in JSON_EVIDENCE]
    blockers = []
    if not python_exe.is_file():
        blockers.append(f"missing_python:{python_exe}")
    blockers.extend(f"missing_evidence:{path}" for path in evidence if not path.is_file())
    return {
        "status": "READY" if not blockers else "BLOCKED",
        "runtime_root": str(root),
        "vulnerable_paths": [str(path) for path in vulnerable_paths(root)],
        "evidence_paths": [str(path) for path in evidence],
        "blockers": blockers,
        "model_load_attempted": False,
        "inference_attempted": False,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".ann-security.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _validate_runtime(runtime_root: Path) -> dict[str, Any]:
    python_exe = runtime_root / "python" / "python.exe"
    script = """
import importlib
import importlib.metadata
import json

from agentic_network.models.llama_cpp_security import (
    PersistentLlamaCacheDisabledError,
    load_secure_llama_cpp,
    llama_cpp_disk_cache_disabled,
)
from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths

configure_windows_runtime_dll_paths()
binding = load_secure_llama_cpp()
cache_module = importlib.import_module("llama_cpp.llama_cache")
try:
    cache_module.LlamaDiskCache()
except PersistentLlamaCacheDisabledError:
    fail_closed = True
else:
    fail_closed = False
try:
    importlib.metadata.version("diskcache")
except importlib.metadata.PackageNotFoundError:
    distribution_absent = True
else:
    distribution_absent = False
print(json.dumps({
    "binding_importable": hasattr(binding, "Llama"),
    "disk_cache_disabled": llama_cpp_disk_cache_disabled(cache_module),
    "disk_cache_fail_closed": fail_closed,
    "diskcache_distribution_absent": distribution_absent,
    "model_load_attempted": False,
    "inference_attempted": False,
}))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT), environment.get("PYTHONPATH", "")) if part
    )
    completed = subprocess.run(
        [str(python_exe), "-c", script],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    try:
        payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload = {}
    passed = completed.returncode == 0 and all(
        payload.get(key) is True
        for key in (
            "binding_importable",
            "disk_cache_disabled",
            "disk_cache_fail_closed",
            "diskcache_distribution_absent",
        )
    )
    return {
        "status": "PASSED" if passed else "FAILED",
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[-4000:],
        "stderr": (completed.stderr or "")[-4000:],
        **payload,
    }


def apply_hardening(
    runtime_root: Path = DEFAULT_RUNTIME,
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    allow_test_root: bool = False,
) -> dict[str, Any]:
    root = assert_runtime_root(runtime_root, allow_test_root=allow_test_root)
    plan = build_plan(root, allow_test_root=allow_test_root)
    if plan["status"] != "READY":
        raise RuntimeError("Runtime hardening blocked: " + ", ".join(plan["blockers"]))
    output = output_dir.resolve()
    if not allow_test_root and not output.is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("Security evidence must stay inside repository outputs.")
    output.mkdir(parents=True, exist_ok=True)
    quarantine = root / "tmp" / f"diskcache-quarantine-{uuid.uuid4().hex}"
    quarantine.mkdir(parents=True, exist_ok=False)
    originals: dict[Path, bytes] = {}
    moved: list[tuple[Path, Path]] = []
    try:
        for relative in JSON_EVIDENCE:
            path = root / relative
            originals[path] = path.read_bytes()
            payload = json.loads(originals[path].decode("utf-8"))
            _write_json_atomic(path, harden_evidence(payload, relative))
        for source in vulnerable_paths(root):
            relative = source.relative_to(root)
            destination = quarantine / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
        validation = _validate_runtime(root)
        if validation["status"] != "PASSED":
            raise RuntimeError("Hardened runtime validation failed.")
        shutil.rmtree(quarantine)
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        for destination, source in reversed(moved):
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.move(str(source), str(destination))
        if quarantine.exists():
            shutil.rmtree(quarantine)
        raise
    report = {
        "status": "HARDENED",
        "runtime_root": str(root),
        "removed_paths": [str(path) for path, _ in moved],
        "validation": validation,
        "diskcache_distribution_installed": False,
        "persistent_disk_cache_enabled": False,
        "model_load_attempted": False,
        "inference_attempted": False,
        "generated_at": now(),
    }
    _write_json_atomic(output / "diskcache_removal_report.json", report)
    (output / "diskcache_removal_report.md").write_text(
        "# ANN llama.cpp Runtime Security\n\n"
        "Status: `HARDENED`\n\n"
        "DiskCache distribution: `REMOVED`\n\n"
        "Persistent llama.cpp disk cache: `DISABLED`\n\n"
        "No model was loaded and no inference was executed.\n",
        encoding="utf-8",
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply:
        result = apply_hardening(args.runtime_root, output_dir=args.output_dir)
    else:
        result = build_plan(args.runtime_root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"READY", "HARDENED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
