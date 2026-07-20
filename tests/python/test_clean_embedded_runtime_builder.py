from __future__ import annotations

import inspect
import zipfile
from pathlib import Path

import pytest

from scripts.runtime import build_clean_embedded_runtime as builder


def test_release_requirements_are_exact_and_complete() -> None:
    requirements = builder.parse_pinned_requirements(builder.DEFAULT_REQUIREMENTS)

    assert requirements["fastapi"] == "0.135.1"
    assert requirements["stripe"] == "15.3.1"
    assert requirements["llama-cpp-python"] == "0.3.32"
    assert "diskcache" not in requirements
    assert "torch" not in requirements
    assert "transformers" not in requirements


def test_plan_is_non_mutating_by_default() -> None:
    plan = builder.build_plan()

    assert plan["status"] == "PLAN_ONLY"
    assert plan["network_requested"] is False
    assert plan["materialize"] is False
    assert plan["source_runtime_modified"] is False
    assert plan["models_loaded"] is False
    assert plan["inference_executed"] is False


def test_release_output_must_stay_inside_repository_build_root() -> None:
    with pytest.raises(ValueError, match="Output must stay inside"):
        builder.assert_safe_output(Path("D:/ANN/runtime-candidate"))


def test_c_drive_output_is_blocked() -> None:
    with pytest.raises(ValueError, match="C: release build output is blocked"):
        builder.assert_safe_output(Path("C:/ANN/runtime"))


def test_wheel_metadata_and_hash_are_read_without_installing(tmp_path: Path) -> None:
    wheel = tmp_path / "demo-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo-1.2.3.dist-info/METADATA", "Name: Demo_Package\nVersion: 1.2.3\n")

    result = builder.inspect_wheel(wheel)

    assert result["name"] == "demo-package"
    assert result["version"] == "1.2.3"
    assert len(result["sha256"]) == 64


def test_clean_python_copy_excludes_packages_scripts_and_caches(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Lib" / "site-packages" / "polluted").mkdir(parents=True)
    (source / "Lib" / "stdlib").mkdir(parents=True)
    (source / "Scripts").mkdir()
    (source / "Doc").mkdir()
    (source / "Lib" / "__pycache__").mkdir()
    (source / "python.exe").write_text("python", encoding="utf-8")
    (source / "Lib" / "stdlib" / "module.py").write_text("", encoding="utf-8")
    (source / "Lib" / "site-packages" / "polluted" / "x.py").write_text("", encoding="utf-8")
    (source / "Scripts" / "pip.exe").write_text("", encoding="utf-8")
    destination = tmp_path / "destination"

    builder.copy_clean_python_base(source, destination)

    assert (destination / "python.exe").is_file()
    assert (destination / "Lib" / "stdlib" / "module.py").is_file()
    assert not (destination / "Lib" / "site-packages").exists()
    assert not (destination / "Scripts").exists()
    assert not (destination / "Doc").exists()
    assert not (destination / "Lib" / "__pycache__").exists()


def test_builder_never_uses_shell_true() -> None:
    source = inspect.getsource(builder)

    assert "shell=True" not in source
    assert "model.load" not in source.lower()


def test_binding_is_excluded_from_normal_dependency_resolution() -> None:
    requirements = builder.pinned_requirement_lines(
        builder.DEFAULT_REQUIREMENTS,
        exclude={builder.LLAMA_CPP_DISTRIBUTION},
    )

    assert all("llama-cpp-python" not in line for line in requirements)
    assert any(line.startswith("numpy==") for line in requirements)


def test_runtime_lock_forbids_diskcache() -> None:
    lock = builder.build_lockfile(
        [
            {
                "name": "llama-cpp-python",
                "version": "0.3.32",
                "filename": "llama_cpp_python.whl",
                "sha256": "0" * 64,
                "size_bytes": 1,
                "source": "offline_wheelhouse",
                "role": "ann_release_runtime",
                "required": True,
                "status": "hash_verified",
            }
        ]
    )

    assert lock["version"] == "18.9.20"
    assert lock["security"]["diskcache_distribution_present"] is False
