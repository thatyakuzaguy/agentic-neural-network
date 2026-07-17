from __future__ import annotations

import json
from pathlib import Path

from agentic_network.desktop_app.views.final_release_view import final_release_snapshot
from agentic_network.runtime_engine.local_model_activation import (
    build_final_release_closure_pack,
    write_final_release_closure_pack_artifacts,
)


def test_final_release_closure_pack_preserves_existing_gates() -> None:
    pack = build_final_release_closure_pack()

    assert pack["version"] == "18.9.18"
    assert pack["status"] in {"FINAL_RELEASE_READY", "FINAL_RELEASE_CLOSURE_BLOCKED"}
    if pack["verification_status"] != "FINAL_RELEASE_READY":
        assert pack["status"] == "FINAL_RELEASE_CLOSURE_BLOCKED"
        assert pack["final_release_ready"] is False
    assert pack["no_gate_downgrade"] is True
    assert pack["no_release_promotion_without_external_evidence"] is True
    assert pack["no_model_load"] is True
    assert pack["no_inference"] is True
    assert pack["no_training"] is True
    assert pack["models_modified"] is False
    assert pack["datasets_modified"] is False
    assert pack["adapters_modified"] is False


def test_final_release_closure_pack_lists_manual_release_evidence() -> None:
    pack = build_final_release_closure_pack()

    required_ids = {item["id"] for item in pack["manual_blockers"]}
    assert required_ids == {"trusted_code_signing", "external_clean_machine_validation"}
    assert "installer/release_signing_evidence.json" in pack["manual_blockers"][0]["required_evidence"]
    assert "clean_machine_external_validation.json" in pack["manual_blockers"][1]["required_evidence"]
    assert "<CERT_THUMBPRINT>" in pack["release_sign_command"]
    assert "validate_clean_machine.ps1" in pack["clean_machine_command"]
    assert "verify_final_release.py" in pack["final_verifier_command"]


def test_final_release_closure_pack_artifacts(tmp_path: Path) -> None:
    artifacts = write_final_release_closure_pack_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"376_final_release_closure_pack.json", "377_final_release_closure_pack.md"}
    payload = json.loads((tmp_path / "376_final_release_closure_pack.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.18"
    assert payload["no_downloads"] is True
    assert (tmp_path / "377_final_release_closure_pack.md").is_file()


def test_final_release_view_surfaces_closure_pack() -> None:
    snapshot = final_release_snapshot()

    assert "Final Release Closure Pack:" in snapshot
    assert "- Status:" in snapshot
    assert "- Acceptance:" in snapshot
