from __future__ import annotations

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
