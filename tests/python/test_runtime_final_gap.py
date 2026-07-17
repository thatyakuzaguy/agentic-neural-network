from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_runtime_final_gap,
    write_runtime_final_gap_artifacts,
    write_runtime_final_macro_artifacts,
)


def test_runtime_final_gap_lists_blockers() -> None:
    gap = build_runtime_final_gap()

    assert gap["status"] == "RUNTIME_FINAL_GAP_BLOCKED"
    assert "Desktop App native foundation" in gap["what_ann_already_has"]
    assert "embedded_python" in gap["what_runtime_still_misses"]
    assert "first_qwen25_smoke_not_executed" in gap["what_blocks_first_inference"]
    assert "signed_installer_missing" in gap["what_blocks_public_release"]
    assert gap["current"]["payload_readiness"] == "PAYLOAD_BLOCKED"


def test_runtime_final_gap_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_final_gap_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"186_runtime_final_gap.json", "187_runtime_final_gap.md"}
    payload = json.loads((tmp_path / "186_runtime_final_gap.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.9"


def test_runtime_final_macro_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_final_macro_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "176_runtime_collection_manifest.json",
        "177_runtime_collection_manifest.md",
        "178_wheelhouse_integrity_registry.json",
        "179_wheelhouse_integrity_registry.md",
        "180_embedded_runtime_inventory.json",
        "181_embedded_runtime_inventory.md",
        "182_embedded_runtime_verification.json",
        "183_embedded_runtime_verification.md",
        "184_beta_runtime_payload_readiness.json",
        "185_beta_runtime_payload_readiness.md",
        "186_runtime_final_gap.json",
        "187_runtime_final_gap.md",
    } == names
