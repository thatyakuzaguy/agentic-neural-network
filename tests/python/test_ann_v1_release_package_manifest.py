from __future__ import annotations

import json
import tomllib
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_ann_v1_release_package_manifest_declares_include_exclude_sets() -> None:
    manifest = activation.build_ann_v1_release_package_manifest()

    assert manifest["status"] == "ANN_V1_RELEASE_PACKAGE_MANIFEST_READY"
    assert "agentic_network" in manifest["include"]
    assert "agentic_network/desktop_app" in manifest["include"]
    assert "agentic_network/runtime_engine" in manifest["include"]
    assert "installer" in manifest["include"]
    assert "scripts/runtime" in manifest["include"]
    assert ".git" in manifest["exclude"]
    assert "training/datasets" in manifest["exclude"]
    assert "training/adapters" in manifest["exclude"]
    assert "models" in manifest["exclude"]
    assert manifest["models_packaged_separately"] is True
    assert manifest["local_first"] is True


def test_python_distribution_uses_explicit_monorepo_package_discovery() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    setuptools_config = config["tool"]["setuptools"]
    assert "email-validator>=2.2.0" in config["project"]["optional-dependencies"]["dev"]
    assert setuptools_config["packages"]["find"]["include"] == ["agentic_network*"]
    assert set(setuptools_config["package-data"]["*"]) >= {
        "*.md",
        "*.yaml",
        "*.html",
        "*.css",
        "*.js",
    }


def test_github_tests_use_ann_safe_drive_for_temporary_projects() -> None:
    project_root = Path(__file__).resolve().parents[2]
    workflow = (project_root / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8"
    )

    assert "TEMP: D:\\ANN-CI-Tmp" in workflow
    assert "TMP: D:\\ANN-CI-Tmp" in workflow
    assert "--basetemp 'D:\\ANN-CI-Tmp\\pytest'" in workflow
    assert "npm audit --audit-level=moderate" in workflow
    assert "npm audit --omit=dev" not in workflow


def test_windows_service_scripts_are_root_portable() -> None:
    project_root = Path(__file__).resolve().parents[2]

    start = (project_root / "start.ps1").read_text(encoding="utf-8")
    stop = (project_root / "stop.ps1").read_text(encoding="utf-8")

    for script in (start, stop):
        assert "$Root = [System.IO.Path]::GetFullPath($PSScriptRoot)" in script
        assert '$Root = "D:\\AgenticEngineeringNetwork"' not in script
    assert "Launch desktop\\ANN.exe instead." in start
    assert "docker compose -f $composeFile up" in start
    assert "docker compose -f $composeFile down" in stop


def test_javascript_security_overrides_pin_patched_transitive_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[2]
    package = json.loads((project_root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads(
        (project_root / "package-lock.json").read_text(encoding="utf-8")
    )
    web_package = json.loads(
        (project_root / "apps" / "web" / "package.json").read_text(encoding="utf-8")
    )

    assert web_package["dependencies"]["sharp"] == "0.35.3"
    assert package["overrides"]["postcss"] == "8.5.20"
    assert package["overrides"]["sharp"] == "0.35.3"
    assert package["overrides"]["next"]["postcss"] == "8.5.20"
    assert package["overrides"]["next"]["sharp"] == "0.35.3"
    assert package_lock["packages"]["node_modules/postcss"]["version"] == "8.5.20"
    assert package_lock["packages"]["node_modules/sharp"]["version"] == "0.35.3"
    assert "node_modules/next/node_modules/postcss" not in package_lock["packages"]
    assert "node_modules/next/node_modules/sharp" not in package_lock["packages"]
