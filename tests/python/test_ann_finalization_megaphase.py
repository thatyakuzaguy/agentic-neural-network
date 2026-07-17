from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentic_network.desktop_app.views.chat_view import chat_runtime_snapshot
from agentic_network.desktop_app.views.first_run_view import first_run_snapshot
from agentic_network.desktop_app.views.model_inventory_view import model_inventory_snapshot
from agentic_network.runtime_engine.local_model_activation import (
    build_ann_finalization_megaphase,
    build_deepseek_powerful_runtime_gate,
    build_installer_final_readiness,
    build_public_release_bridge_final,
    build_qwen3_runtime_activation_gate,
    materialize_runtime_finalization_foundation,
    write_ann_finalization_megaphase_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _d_drive_test_root(name: str) -> Path:
    root = REPO_ROOT / "outputs" / "test_ann_finalization" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def test_runtime_finalization_materializes_only_safe_layout(tmp_path: Path) -> None:
    root = _d_drive_test_root(tmp_path.name)
    runtime_root = root / "ANN" / "runtime"
    output_dir = root / "artifacts"

    result = materialize_runtime_finalization_foundation(runtime_root, output_dir)

    assert result["status"] == "RUNTIME_FINALIZATION_PARTIAL"
    assert result["no_install"] is True
    assert result["no_download"] is True
    assert result["no_python_execution"] is True
    assert (runtime_root / "audit" / "runtime_finalization_manifest.json").is_file()
    assert (runtime_root / "audit" / "runtime_finalization_audit.json").is_file()
    assert (runtime_root / "checks" / "runtime_finalization_checks.json").is_file()
    assert not (runtime_root / "python" / "python.exe").exists()


def test_qwen3_runtime_gate_is_sequential_and_blocked_without_policy() -> None:
    gate = build_qwen3_runtime_activation_gate(approval_token="LOCAL_TEST_TOKEN", manual_confirmation=True)

    assert gate["status"] == "QWEN3_ACTIVATION_BLOCKED"
    assert gate["mode"] == "FAST"
    assert gate["adapter"] == "qwen3-8b-product-agent-v9-repaired-v2-bullets"
    assert gate["load_run_unload_allowed"] is False
    assert gate["model_load_attempted"] is False
    assert gate["real_inference_attempted"] is False
    assert gate["active_models"] == 0
    assert gate["parallel_llm_loads"] == 0


def test_deepseek_powerful_gate_is_sequential_and_blocked_without_policy() -> None:
    gate = build_deepseek_powerful_runtime_gate(approval_token="LOCAL_TEST_TOKEN", manual_confirmation=True)

    assert gate["status"] == "DEEPSEEK_POWERFUL_BLOCKED"
    assert gate["mode"] == "POWERFUL"
    assert gate["load_run_unload_allowed"] is False
    assert gate["model_load_attempted"] is False
    assert gate["real_inference_attempted"] is False
    assert gate["deepseek_loaded"] is False
    assert gate["powerful_activated"] is False
    assert gate["active_models"] == 0
    assert gate["parallel_llm_loads"] == 0


def test_installer_and_public_release_final_remain_blocked_until_real_evidence() -> None:
    installer = build_installer_final_readiness()
    release = build_public_release_bridge_final()
    finalization = build_ann_finalization_megaphase()

    assert installer["status"] == "INSTALLER_FINAL_BLOCKED"
    assert installer["clean_machine_evidence_status"] == "LOCAL_INSTALL_SMOKE_PASSED"
    assert installer["local_install_smoke_passed"] is True
    assert installer["external_clean_machine_passed"] is False
    assert installer["signed_installer_readiness"] is False
    assert installer["code_signing_status"] == "SIGNING_BLOCKED_UNSIGNED"
    assert {blocker["id"] for blocker in installer["blockers"]} >= {
        "clean_machine_evidence",
        "signed_installer",
    }
    assert release["status"] == "FINAL_RELEASE_BLOCKED"
    assert finalization["status"] == "FINAL_RELEASE_BLOCKED"
    assert finalization["active_models"] == 0
    assert finalization["parallel_llm_loads"] == 0
    assert finalization["no_downloads"] is True
    assert finalization["models_modified"] is False
    assert finalization["datasets_modified"] is False
    assert finalization["adapters_modified"] is False


def test_ann_finalization_artifacts(tmp_path: Path) -> None:
    artifacts = write_ann_finalization_megaphase_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert {
        "224_runtime_finalization.json",
        "225_runtime_finalization.md",
        "226_qwen3_runtime_activation_gate.json",
        "227_qwen3_runtime_activation_gate.md",
        "228_deepseek_powerful_runtime_gate.json",
        "229_deepseek_powerful_runtime_gate.md",
        "230_installer_public_release_finalization.json",
        "231_installer_public_release_finalization.md",
    } == names
    payload = json.loads((tmp_path / "230_installer_public_release_finalization.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.0"
    assert payload["status"] == "FINAL_RELEASE_BLOCKED"


def test_desktop_surfaces_finalization_status() -> None:
    snapshots = (first_run_snapshot(), model_inventory_snapshot(), chat_runtime_snapshot())

    for snapshot in snapshots:
        assert "Installer Final: INSTALLER_FINAL_BLOCKED" in snapshot
        assert "Public Release Final: FINAL_RELEASE_BLOCKED" in snapshot
        assert "ANN Finalization Megaphase: FINAL_RELEASE_BLOCKED" in snapshot
