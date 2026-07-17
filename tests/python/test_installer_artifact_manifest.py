from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_installer_artifact_manifest,
    write_installer_artifact_manifest_artifacts,
)


def test_installer_artifact_manifest_includes_and_excludes_expected_paths() -> None:
    manifest = build_installer_artifact_manifest()
    excluded_paths = {Path(item["path"]).name.lower() for item in manifest["excluded"]}
    groups = {item["name"] for item in manifest["include_groups"]}

    assert manifest["status"] == "MANIFEST_READY"
    assert {"app", "desktop_app", "runtime_bundle", "runtime_engine", "installer", "config", "checks"}.issubset(groups)
    assert ".git" in excluded_paths
    assert "models" in excluded_paths
    assert "training" in excluded_paths
    assert "outputs" in excluded_paths
    assert "unsloth_compiled_cache" in excluded_paths
    assert any("D:\\ANN\\models" == item for item in manifest["preserve_on_uninstall"])
    assert manifest["safety"]["model_load"] is False


def test_installer_artifact_manifest_artifacts(tmp_path: Path) -> None:
    artifacts = write_installer_artifact_manifest_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"154_installer_artifact_manifest.json", "155_installer_artifact_manifest.md"}
    payload = json.loads((tmp_path / "154_installer_artifact_manifest.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.8"
