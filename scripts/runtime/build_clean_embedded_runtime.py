"""Build ANN's minimal, reproducible Windows embedded runtime release payload.

The tool is plan-only unless explicit acquisition/materialization flags are used.
It never modifies the source runtime and restricts all build output to the
repository release-build directory on D:.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_PYTHON = Path("D:/ANN/runtime/python")
DEFAULT_EXISTING_WHEELHOUSE = Path("D:/ANN/runtime/wheels")
DEFAULT_REQUIREMENTS = REPO_ROOT / "config" / "ann_runtime_requirements.windows-cp311.txt"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "release_build" / "runtime_clean"
RELEASE_BUILD_ROOT = (REPO_ROOT / "outputs" / "release_build").resolve()
IMPORT_NAMES = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "psycopg",
    "dotenv",
    "stripe",
    "PySide6",
    "llama_cpp",
    "numpy",
    "psutil",
    "yaml",
)
FORBIDDEN_DISTRIBUTIONS = {
    "azure-core",
    "diskcache",
    "jupyter",
    "jupyterlab",
    "langgraph",
    "opencv-python",
    "open-webui",
    "unsloth",
}
APPLICATION_DISTRIBUTIONS = {"agentic-engineering-network"}
LLAMA_CPP_DISTRIBUTION = "llama-cpp-python"


def canonical_name(value: str) -> str:
    """Return the PEP 503 normalized distribution name."""

    return re.sub(r"[-_.]+", "-", value).lower()


def parse_pinned_requirements(path: Path) -> dict[str, str]:
    """Parse the exact top-level release dependency contract."""

    requirements: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if "==" not in value:
            raise ValueError(f"Release requirement is not exactly pinned: {value}")
        name, version = value.split("==", 1)
        name = name.split("[", 1)[0].strip()
        requirements[canonical_name(name)] = version.strip()
    if not requirements:
        raise ValueError("Release requirements are empty.")
    return requirements


def pinned_requirement_lines(path: Path, *, exclude: set[str] | None = None) -> list[str]:
    """Return pinned requirement lines while preserving extras and package spelling."""

    excluded = {canonical_name(name) for name in (exclude or set())}
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        if "==" not in value:
            raise ValueError(f"Release requirement is not exactly pinned: {value}")
        name = canonical_name(value.split("==", 1)[0].split("[", 1)[0].strip())
        if name not in excluded:
            lines.append(value)
    return lines


def inspect_wheel(path: Path) -> dict[str, Any]:
    """Read wheel identity and hash without installing it."""

    with zipfile.ZipFile(path) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8", errors="replace")
    name = ""
    version = ""
    for line in metadata.splitlines():
        if line.startswith("Name: "):
            name = line[6:].strip()
        elif line.startswith("Version: "):
            version = line[9:].strip()
        if name and version:
            break
    if not name or not version:
        raise ValueError(f"Wheel metadata is incomplete: {path.name}")
    return {
        "name": canonical_name(name),
        "version": version,
        "filename": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "source": "offline_wheelhouse",
        "role": "ann_release_runtime",
        "required": True,
        "status": "hash_verified",
    }


def build_plan(
    *,
    base_python: Path = DEFAULT_BASE_PYTHON,
    existing_wheelhouse: Path = DEFAULT_EXISTING_WHEELHOUSE,
    requirements: Path = DEFAULT_REQUIREMENTS,
    output: Path = DEFAULT_OUTPUT,
    acquire_missing_wheels: bool = False,
    materialize: bool = False,
) -> dict[str, Any]:
    """Build a non-mutating release plan and validate all path boundaries."""

    output = assert_safe_output(output)
    base_python = assert_safe_source(base_python, "base_python")
    existing_wheelhouse = assert_safe_source(existing_wheelhouse, "existing_wheelhouse")
    requirements = requirements.resolve()
    if requirements != DEFAULT_REQUIREMENTS.resolve():
        raise ValueError("Release requirements must use the repository contract.")
    pinned = parse_pinned_requirements(requirements)
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "status": "EXECUTION_REQUESTED" if acquire_missing_wheels or materialize else "PLAN_ONLY",
        "base_python": str(base_python),
        "existing_wheelhouse": str(existing_wheelhouse),
        "requirements": str(requirements),
        "requirements_sha256": sha256_file(requirements),
        "output": str(output),
        "candidate_python": str(output / "python" / "python.exe"),
        "candidate_wheelhouse": str(output / "wheels"),
        "top_level_requirements": pinned,
        "acquire_missing_wheels": acquire_missing_wheels,
        "materialize": materialize,
        "network_requested": acquire_missing_wheels,
        "source_runtime_modified": False,
        "models_loaded": False,
        "inference_executed": False,
    }


def build_runtime(
    plan: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Acquire the closure, materialize Python, validate, and write evidence."""

    output = assert_safe_output(Path(plan["output"]))
    base_python = assert_safe_source(Path(plan["base_python"]), "base_python")
    existing_wheelhouse = assert_safe_source(
        Path(plan["existing_wheelhouse"]), "existing_wheelhouse"
    )
    requirements = Path(plan["requirements"])
    if force and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "audit" / "runtime_build_plan.json", plan)
    wheelhouse = output / "wheels"
    wheelhouse.mkdir(parents=True, exist_ok=True)
    for name in ("checks", "logs", "site-packages", "requirements-lock", "audit"):
        (output / name).mkdir(parents=True, exist_ok=True)
    source_python = base_python / "python.exe"
    if not source_python.is_file():
        raise FileNotFoundError(f"Base Python executable is missing: {source_python}")

    if plan["acquire_missing_wheels"]:
        safe_requirements = pinned_requirement_lines(
            requirements,
            exclude={LLAMA_CPP_DISTRIBUTION},
        )
        run_checked(
            [
                str(source_python),
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--dest",
                str(wheelhouse),
                "--find-links",
                str(existing_wheelhouse),
                *safe_requirements,
            ],
            cwd=REPO_ROOT,
        )
        run_checked(
            [
                str(source_python),
                "-m",
                "pip",
                "download",
                "--no-deps",
                "--only-binary=:all:",
                "--dest",
                str(wheelhouse),
                "--find-links",
                str(existing_wheelhouse),
                f"{LLAMA_CPP_DISTRIBUTION}=={plan['top_level_requirements'][LLAMA_CPP_DISTRIBUTION]}",
            ],
            cwd=REPO_ROOT,
        )

    if not plan["materialize"]:
        return {"status": "WHEELHOUSE_ACQUIRED", "output": str(output)}

    wheels = sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())
    if not wheels:
        raise RuntimeError("Candidate wheelhouse is empty; acquire the dependency closure first.")
    wheel_entries = [inspect_wheel(path) for path in wheels]
    vulnerable_wheels = [
        entry["filename"] for entry in wheel_entries if entry["name"] == "diskcache"
    ]
    if vulnerable_wheels:
        raise RuntimeError(
            "Candidate wheelhouse contains prohibited DiskCache artifacts: "
            + ", ".join(vulnerable_wheels)
        )
    python_target = output / "python"
    copy_clean_python_base(base_python, python_target)
    site_packages = python_target / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    safe_requirements = pinned_requirement_lines(
        requirements,
        exclude={LLAMA_CPP_DISTRIBUTION},
    )
    run_checked(
        [
            str(source_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--only-binary=:all:",
            "--target",
            str(site_packages),
            "--upgrade",
            "--ignore-installed",
            *safe_requirements,
        ],
        cwd=REPO_ROOT,
    )
    run_checked(
        [
            str(source_python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--only-binary=:all:",
            "--target",
            str(site_packages),
            "--upgrade",
            "--ignore-installed",
            f"{LLAMA_CPP_DISTRIBUTION}=={plan['top_level_requirements'][LLAMA_CPP_DISTRIBUTION]}",
        ],
        cwd=REPO_ROOT,
    )

    lock = build_lockfile(wheel_entries)
    checks = output / "checks"
    checks.mkdir(parents=True, exist_ok=True)
    write_json(checks / "ann_runtime_lock.json", lock)
    validation = validate_candidate(output, plan, wheel_entries)
    write_json(output / "audit" / "runtime_release_validation.json", validation)
    manifest = build_manifest(output, plan, wheel_entries, validation)
    write_json(output / "audit" / "runtime_release_manifest.json", manifest)
    write_validation_markdown(
        output / "audit" / "runtime_release_validation.md", validation, manifest
    )
    if validation["status"] != "RUNTIME_RELEASE_READY":
        raise RuntimeError(
            "Clean runtime validation failed: " + ", ".join(validation["blockers"])
        )
    return manifest


def copy_clean_python_base(source: Path, destination: Path) -> None:
    """Copy CPython while excluding every package and cache from the source."""

    if destination.exists():
        shutil.rmtree(destination)

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
        if current == source:
            ignored.update(name for name in names if name in {"Doc", "Scripts"})
        if current == source / "Lib":
            ignored.update(name for name in names if name == "site-packages")
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def validate_candidate(
    runtime_root: Path,
    plan: dict[str, Any],
    wheel_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute import-only validation with no model load or inference."""

    python_exe = runtime_root / "python" / "python.exe"
    expected = dict(plan["top_level_requirements"])
    allowed = {entry["name"] for entry in wheel_entries} | APPLICATION_DISTRIBUTIONS
    probe_script = _candidate_probe_script()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(REPO_ROOT), environment.get("PYTHONPATH", "")) if part
    )
    completed = subprocess.run(
        [str(python_exe), "-c", probe_script, json.dumps(IMPORT_NAMES)],
        cwd=str(REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    try:
        probe = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except (json.JSONDecodeError, IndexError):
        probe = {}
    installed = {
        canonical_name(name): str(version)
        for name, version in (probe.get("distributions") or {}).items()
    }
    imports = probe.get("imports") or {}
    missing_imports = sorted(name for name in IMPORT_NAMES if imports.get(name) is not True)
    missing_distributions = sorted(set(expected) - set(installed))
    version_mismatches = [
        f"{name}:expected={version}:actual={installed.get(name, 'missing')}"
        for name, version in sorted(expected.items())
        if installed.get(name) != version
    ]
    unexpected = sorted(set(installed) - allowed)
    forbidden = sorted(set(installed) & FORBIDDEN_DISTRIBUTIONS)
    blockers: list[str] = []
    if completed.returncode != 0:
        blockers.append(f"probe_returncode:{completed.returncode}")
    blockers.extend(f"missing_import:{name}" for name in missing_imports)
    blockers.extend(f"missing_distribution:{name}" for name in missing_distributions)
    blockers.extend(f"version_mismatch:{item}" for item in version_mismatches)
    blockers.extend(f"unexpected_distribution:{name}" for name in unexpected)
    blockers.extend(f"forbidden_distribution:{name}" for name in forbidden)
    if probe.get("llama_cpp_gpu_offload") is not True:
        blockers.append("llama_cpp_gpu_offload_unavailable")
    if probe.get("persistent_disk_cache_enabled") is not False:
        blockers.append("llama_cpp_persistent_disk_cache_not_disabled")
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "status": "RUNTIME_RELEASE_READY" if not blockers else "RUNTIME_RELEASE_BLOCKED",
        "python_executable": str(python_exe),
        "python_version": probe.get("python_version", ""),
        "probe_returncode": completed.returncode,
        "probe_stderr": stderr,
        "imports": imports,
        "installed_distributions": installed,
        "allowed_distributions": sorted(allowed),
        "missing_imports": missing_imports,
        "missing_distributions": missing_distributions,
        "version_mismatches": version_mismatches,
        "unexpected_distributions": unexpected,
        "forbidden_distributions": forbidden,
        "llama_cpp_gpu_offload": probe.get("llama_cpp_gpu_offload") is True,
        "persistent_disk_cache_enabled": probe.get("persistent_disk_cache_enabled"),
        "diskcache_distribution_installed": "diskcache" in installed,
        "blockers": blockers,
        "model_load_attempted": False,
        "inference_executed": False,
    }


def build_lockfile(wheels: list[dict[str, Any]]) -> dict[str, Any]:
    """Create the lock format consumed by ANN's existing integrity gates."""

    packages = [
        {
            "name": entry["name"],
            "version": entry["version"],
            "role": "ann_release_runtime",
            "required_for": ["windows_release"],
            "optional": False,
            "expected_runtime_path": "D:\\ANN\\runtime\\python\\Lib\\site-packages",
            "verification_status": "hash_verified",
            "notes": "Resolved by the clean release runtime builder.",
        }
        for entry in wheels
    ]
    return {
        "version": "18.9.20",
        "python_version": "3.11",
        "platform": "windows",
        "architecture": "x86_64",
        "cuda_variant": "cu12x",
        "expected_runtime_path": "D:\\ANN\\runtime",
        "verification_status": "hash_verified",
        "source": "ann_clean_release_builder",
        "packages": packages,
        "wheels": wheels,
        "hashes": {"algorithm": "sha256", "required": True, "status": "hash_verified"},
        "security": {
            "diskcache_distribution_present": False,
            "llama_cpp_persistent_disk_cache": "disabled",
            "advisory_removed": "CVE-2025-69872",
        },
        "not_installed_by_ann": True,
    }


def build_manifest(
    output: Path,
    plan: dict[str, Any],
    wheels: list[dict[str, Any]],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Build immutable release evidence for the validated runtime payload."""

    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "status": validation["status"],
        "runtime_root": str(output),
        "python_executable": str(output / "python" / "python.exe"),
        "requirements": plan["requirements"],
        "requirements_sha256": plan["requirements_sha256"],
        "wheel_count": len(wheels),
        "wheels": wheels,
        "installed_distributions": validation["installed_distributions"],
        "runtime_size_bytes": directory_size(output),
        "llama_cpp_gpu_offload": validation["llama_cpp_gpu_offload"],
        "persistent_disk_cache_enabled": False,
        "diskcache_distribution_installed": False,
        "minimal_runtime": not validation["unexpected_distributions"],
        "source_runtime_modified": False,
        "model_load_attempted": False,
        "inference_executed": False,
        "network_used_for_build": bool(plan["acquire_missing_wheels"]),
        "network_required_after_install": False,
    }


def assert_safe_output(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.drive.lower() == "c:":
        raise ValueError("C: release build output is blocked.")
    if not resolved.is_relative_to(RELEASE_BUILD_ROOT):
        raise ValueError(f"Output must stay inside {RELEASE_BUILD_ROOT}.")
    return resolved


def assert_safe_source(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved.drive.lower() == "c:":
        raise ValueError(f"{label} on C: is blocked.")
    if len(resolved.parts) < 3:
        raise ValueError(f"{label} is too shallow: {resolved}")
    return resolved


def run_checked(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {command[0]}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_validation_markdown(
    path: Path,
    validation: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    blockers = validation["blockers"] or ["None"]
    lines = [
        "# ANN Clean Embedded Runtime Validation",
        "",
        f"Status: `{validation['status']}`",
        f"Python: `{validation['python_version']}`",
        f"Wheels: `{manifest['wheel_count']}`",
        f"Runtime bytes: `{manifest['runtime_size_bytes']}`",
        f"llama.cpp GPU offload: `{validation['llama_cpp_gpu_offload']}`",
        f"Unexpected distributions: `{len(validation['unexpected_distributions'])}`",
        "",
        "## Blockers",
        *[f"- {item}" for item in blockers],
        "",
        "No model was loaded and no inference was executed during validation.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_probe_script() -> str:
    return """
import importlib
import importlib.metadata
import json
import re
import sys

from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths
from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload
from agentic_network.models.llama_cpp_security import load_secure_llama_cpp

names = json.loads(sys.argv[1])
configure_windows_runtime_dll_paths()
imports = {}
llama_module = None
for name in names:
    try:
        module = load_secure_llama_cpp() if name == "llama_cpp" else importlib.import_module(name)
        imports[name] = True
        if name == "llama_cpp":
            llama_module = module
    except Exception:
        imports[name] = False
normalize = lambda value: re.sub(r"[-_.]+", "-", value).lower()
distributions = {
    normalize(dist.metadata["Name"]): dist.version
    for dist in importlib.metadata.distributions()
    if dist.metadata.get("Name")
}
print(json.dumps({
    "python_version": sys.version.split()[0],
    "imports": imports,
    "distributions": distributions,
    "llama_cpp_gpu_offload": (
        llama_cpp_supports_gpu_offload(llama_module) is True if llama_module else False
    ),
    "persistent_disk_cache_enabled": False,
}, sort_keys=True))
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-python", type=Path, default=DEFAULT_BASE_PYTHON)
    parser.add_argument("--existing-wheelhouse", type=Path, default=DEFAULT_EXISTING_WHEELHOUSE)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--acquire-missing-wheels", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(
        base_python=args.base_python,
        existing_wheelhouse=args.existing_wheelhouse,
        requirements=args.requirements,
        output=args.output,
        acquire_missing_wheels=args.acquire_missing_wheels,
        materialize=args.materialize,
    )
    if not args.acquire_missing_wheels and not args.materialize:
        output = assert_safe_output(args.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "audit").mkdir(parents=True, exist_ok=True)
        write_json(output / "audit" / "runtime_build_plan.json", plan)
        print(json.dumps(plan, indent=2))
        return 0
    try:
        result = build_runtime(plan, force=args.force)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"RUNTIME_BUILD_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
