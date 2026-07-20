"""Verify that ANN's llama.cpp runtime cannot install or import DiskCache."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DISKCACHE_NAMES = {"diskcache", "python-diskcache"}


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r ")):
            continue
        name = re.split(r"[<>=!~\[\s]", line, maxsplit=1)[0]
        names.add(canonical_name(name))
    return names


def named_entries(payload: dict[str, Any], key: str) -> set[str]:
    entries = payload.get(key, [])
    if not isinstance(entries, list):
        return set()
    return {
        canonical_name(str(entry.get("name", "")))
        for entry in entries
        if isinstance(entry, dict)
    }


def verify_policy(root: Path = ROOT) -> dict[str, object]:
    failures: list[str] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pyproject.get("project", {}).get("optional-dependencies", {})
    local_models = extras.get("local-models", []) if isinstance(extras, dict) else []
    extra_text = "\n".join(str(item).lower() for item in local_models)
    if "llama-cpp-python" in extra_text or "diskcache" in extra_text:
        failures.append("pyproject local-models extra must not resolve llama-cpp-python or diskcache")

    model_requirements = root / "apps" / "api" / "requirements-models.txt"
    binding_requirements = root / "apps" / "api" / "requirements-llama-cpp.txt"
    model_names = requirement_names(model_requirements)
    binding_lines = [
        line.strip()
        for line in binding_requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if model_names & (DISKCACHE_NAMES | {"llama-cpp-python"}):
        failures.append("safe model dependency closure contains a prohibited package")
    if binding_lines != ["llama-cpp-python==0.3.32"]:
        failures.append("llama.cpp binding contract must contain one exact pin")

    dockerfile = (root / "docker" / "api.gpu.Dockerfile").read_text(encoding="utf-8")
    if "--no-deps" not in dockerfile or "requirements-llama-cpp.txt" not in dockerfile:
        failures.append("GPU image must install the isolated binding with --no-deps")
    if "pip uninstall" in dockerfile.lower():
        failures.append("GPU image must never rely on post-install vulnerable-package removal")

    workflow = (root / ".github" / "workflows" / "security-scan.yml").read_text(
        encoding="utf-8"
    )
    if "PYSEC-2026-2447" in workflow or "CVE-2025-69872" in workflow:
        failures.append("security workflow still suppresses the DiskCache advisory")
    if "requirements-llama-cpp.txt" not in workflow or "--no-deps" not in workflow:
        failures.append("security workflow does not audit the isolated binding contract")

    lock = json.loads(
        (root / "config" / "ann_runtime_lock.example.json").read_text(encoding="utf-8")
    )
    if named_entries(lock, "packages") & DISKCACHE_NAMES:
        failures.append("runtime lock package inventory contains DiskCache")
    if named_entries(lock, "wheels") & DISKCACHE_NAMES:
        failures.append("runtime wheelhouse lock contains DiskCache")

    runtime_requirements = requirement_names(
        root / "config" / "ann_runtime_requirements.windows-cp311.txt"
    )
    if runtime_requirements & DISKCACHE_NAMES:
        failures.append("embedded runtime requirements contain DiskCache")

    unsafe_imports: list[str] = []
    for base in (root / "agentic_network", root / "packages", root / "scripts" / "runtime"):
        for path in base.rglob("*.py"):
            if path.name == "llama_cpp_security.py":
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"^\s*(?:import llama_cpp|from llama_cpp import)", line):
                    unsafe_imports.append(f"{path.relative_to(root)}:{line_number}")
    if unsafe_imports:
        failures.append("direct insecure llama_cpp imports: " + ", ".join(unsafe_imports))

    if failures:
        raise RuntimeError("; ".join(failures))
    return {
        "status": "PASS",
        "advisory": "CVE-2025-69872",
        "diskcache_in_dependency_contract": False,
        "llama_cpp_install_mode": "no-deps",
        "persistent_disk_cache": "disabled",
        "unsafe_imports": [],
    }


def main() -> int:
    print(json.dumps(verify_policy(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
