from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_ann_v1_freeze_manifest_records_release_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(activation, "_directory_size", lambda *_args, **_kwargs: 1024)
    monkeypatch.setattr(activation, "_estimate_release_candidate_size", lambda *_args, **_kwargs: 2048)
    manifest = activation.build_ann_v1_freeze_manifest()

    assert manifest["version_label"] == "ANN v1.0 Release Candidate"
    assert manifest["status"] in {"ANN_V1_FREEZE_READY", "ANN_V1_FREEZE_BLOCKED"}
    assert manifest["model_routing"]["vram_policy"] == "SEQUENTIAL"
    assert manifest["runtime_mode"]["active_models"] == 0
    assert manifest["runtime_mode"]["parallel_llm_loads"] == 0
    assert manifest["desktop_status"]["version_label"] == "ANN v1.0"
    assert manifest["protected_paths"]
    assert "known_limitations" in manifest

    artifacts = activation.write_ann_v1_release_hardening_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}
    assert "324_ann_v1_freeze_manifest.json" in names
    assert "325_ann_v1_freeze_manifest.md" in names
    payload = json.loads((tmp_path / "324_ann_v1_freeze_manifest.json").read_text(encoding="utf-8"))
    assert payload["version"] == "1.0"
