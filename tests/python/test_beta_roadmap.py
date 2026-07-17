from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_beta_roadmap, write_beta_roadmap_artifacts


def test_beta_roadmap_contains_blocked_release_path() -> None:
    roadmap = build_beta_roadmap()
    ids = {item["id"] for item in roadmap["items"]}

    assert roadmap["status"] == "BETA_BLOCKED"
    assert "embedded_python" in ids
    assert "offline_wheelhouse" in ids
    assert "real_qwen25" in ids
    assert "real_qwen3" in ids
    assert "deepseek_powerful" in ids
    assert "installer_final" in ids
    assert "signed_installer" in ids
    assert "clean_machine_validation" in ids
    assert "public_beta" in ids
    assert "public_release" in ids
    assert all(item["status"] == "BLOCKED" for item in roadmap["items"])


def test_beta_roadmap_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_roadmap_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"164_beta_roadmap.json", "165_beta_roadmap.md"}
    payload = json.loads((tmp_path / "164_beta_roadmap.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.2"
