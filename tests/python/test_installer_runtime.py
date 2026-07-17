from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.installer.paths import get_default_install_root, is_c_drive
from agentic_network.installer.runtime import (
    build_install_plan,
    build_uninstall_plan,
    create_launcher,
    create_shortcut,
    write_install_manifest,
)
from agentic_network.installer.validation import validate_install_plan, validate_runtime_requirements


REPO_ROOT = Path("D:/AgenticEngineeringNetwork")


def test_build_install_plan_excludes_git(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert any(path.endswith(".git") for path in plan.excluded_paths)
    assert not any(".git" in path for path in plan.files_to_copy)


def test_build_install_plan_excludes_models(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert any(path.endswith("models") for path in plan.excluded_paths)
    assert not any("/models/" in _slash(path) for path in plan.files_to_copy)


def test_build_install_plan_excludes_training(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert any(path.endswith("training") for path in plan.excluded_paths)
    assert not any("/training/" in _slash(path) for path in plan.files_to_copy)


def test_build_install_plan_excludes_datasets_adapters(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    copied = "\n".join(_slash(path) for path in plan.files_to_copy)
    assert "/training/datasets/" not in copied
    assert "/training/adapters/" not in copied


def test_build_install_plan_excludes_historical_outputs(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert any(path.endswith("outputs") for path in plan.excluded_paths)
    assert not any("/outputs/" in _slash(path) for path in plan.files_to_copy)


def test_install_dirs_are_planned(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert str(Path("D:/ANN/app")) in plan.dirs_to_create
    assert str(Path("D:/ANN/projects")) in plan.dirs_to_create
    assert str(Path("D:/ANN/runtime")) in plan.dirs_to_create


def test_launcher_planned(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "D:/ANN")

    assert str(Path("D:/ANN/runtime")) in plan.dirs_to_create
    assert any(path.endswith("installer\\ann_launcher.ps1") for path in plan.files_to_copy)


def test_shortcut_planned(tmp_path: Path) -> None:
    install_root = _safe_install_root(tmp_path)

    result = create_shortcut(install_root)

    assert result.status == "CREATED"
    assert result.shortcut_path.endswith("ANN Desktop.lnk.cmd")


def test_uninstall_preserves_projects_by_default() -> None:
    plan = build_uninstall_plan("D:/ANN")

    assert plan.keep_projects is True
    assert str(Path("D:/ANN/projects")) in plan.paths_to_keep


def test_uninstall_preserves_models_by_default() -> None:
    plan = build_uninstall_plan("D:/ANN")

    assert plan.keep_models is True
    assert str(Path("D:/ANN/models")) in plan.paths_to_keep


def test_uninstall_preserves_outputs_by_default() -> None:
    plan = build_uninstall_plan("D:/ANN")

    assert plan.keep_outputs is True
    assert str(Path("D:/ANN/outputs")) in plan.paths_to_keep


def test_runtime_validation_handles_missing_pyside6(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "PySide6":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    result = validate_runtime_requirements("D:/ANN")

    assert result.pyside6_available is False
    assert any("PySide6" in warning for warning in result.warnings)


def test_install_manifest_generated(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    install_root = _safe_install_root(tmp_path)
    plan = build_install_plan(source, install_root)

    manifest = write_install_manifest(install_root, plan)

    assert manifest.is_file()
    assert "files_to_copy" in manifest.read_text(encoding="utf-8")


def test_install_root_path_traversal_blocked(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "../ANN")
    validation = validate_install_plan(plan)

    assert "install_root_path_traversal_blocked" in validation.errors


def test_c_drive_blocked_unless_policy_allows(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)

    plan = build_install_plan(source, "C:/ANN")
    validation = validate_install_plan(plan)

    assert "install_root_c_drive_blocked" in validation.errors


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Installer planning must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)

    assert build_install_plan(_source_tree(tmp_path), "D:/ANN").install_root == str(Path("D:/ANN").resolve())


def test_no_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Installer runtime must not download dependencies.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert build_install_plan(_source_tree(tmp_path), "D:/ANN").errors == []


def test_no_pip_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Installer runtime must not pip install automatically.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert validate_runtime_requirements("D:/ANN").python_executable


def test_launcher_creation() -> None:
    install_root = _safe_install_root(Path("installer_launcher"))

    result = create_launcher(install_root)

    assert result.status == "CREATED"
    assert Path(result.launcher_path).is_file()


def test_default_install_root_is_d_ann() -> None:
    assert get_default_install_root() == Path("D:/ANN")


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / ".git").mkdir(parents=True)
    (source / "models").mkdir()
    (source / "training" / "datasets").mkdir(parents=True)
    (source / "training" / "adapters").mkdir(parents=True)
    (source / "outputs" / "runs").mkdir(parents=True)
    (source / "agentic_network" / "desktop_app").mkdir(parents=True)
    (source / "agentic_network" / "__pycache__").mkdir(parents=True)
    (source / "config").mkdir()
    (source / "installer").mkdir()
    (source / "agentic_network" / "__init__.py").write_text("", encoding="utf-8")
    (source / "agentic_network" / "desktop_app" / "run.py").write_text("print('ANN')\n", encoding="utf-8")
    (source / "config" / "ann_runtime_engine.json").write_text("{}", encoding="utf-8")
    (source / "installer" / "ann_launcher.ps1").write_text("# launcher\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='ann'\n", encoding="utf-8")
    (source / "README.md").write_text("# ANN\n", encoding="utf-8")
    return source


def _safe_install_root(seed: Path) -> Path:
    if is_c_drive(seed) or not seed.is_absolute():
        root = REPO_ROOT / "outputs" / "installer_tests" / seed.name
    else:
        root = seed / "install"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slash(path: str) -> str:
    return path.replace("\\", "/").lower()
