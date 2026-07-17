from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentic_network.desktop_app.views.first_run_view import build_first_run_state, first_run_snapshot
from agentic_network.installer.distribution import (
    build_alpha_release_checklist,
    build_distribution_readiness,
    build_embedded_runtime_plan,
    build_model_distribution_status,
    verify_installer_foundation,
    write_distribution_artifacts,
)


def test_distribution_readiness_reports_alpha_state() -> None:
    report = build_distribution_readiness()

    assert report["status"] in {"READY_FOR_ALPHA", "ALPHA_GAPS"}
    assert report["safety"]["local_only"] is True
    assert report["safety"]["downloads"] is False
    assert any(check["name"] == "no_c_drive_default" for check in report["checks"])


def test_embedded_runtime_plan_is_plan_only() -> None:
    plan = build_embedded_runtime_plan()

    assert plan["status"] == "PLAN_ONLY"
    assert plan["embedded_python_executable"].replace("\\", "/").endswith("/runtime/python/python.exe")
    assert "no_downloads" in plan["blocked_actions"]


def test_installer_verification_is_read_only_and_preserves_data() -> None:
    report = verify_installer_foundation()

    assert report["uninstall_plan"]["keep_projects"] is True
    assert report["uninstall_plan"]["keep_models"] is True
    assert report["script_status"]["blocked_tokens"] == []


def test_model_distribution_status_keeps_sequential_policy_and_blocks_real_load() -> None:
    status = build_model_distribution_status()
    qwen25 = next(model for model in status["models"] if model["id"] == "qwen2_5_coder_7b_v5")
    qwen3 = next(model for model in status["models"] if model["id"] == "qwen3_8b_v9_repaired_v2_bullets")

    assert status["sequential_policy"]["valid"] is True
    assert status["sequential_policy"]["max_loaded_models"] == 1
    assert status["sequential_policy"]["parallel_llm_loads"] == 0
    assert status["policy"]["allow_real_model_load"] is False
    assert status["status"] == "MODEL_LOADING_BLOCKED_BY_POLICY"
    assert qwen25["confirmed_local_asset"] is True
    assert qwen3["confirmed_local_asset"] is True
    assert qwen25["load_allowed"] is False
    assert qwen3["load_allowed"] is False


def test_deepseek14b_powerful_is_not_misrepresented_when_policy_blocks_loading() -> None:
    status = build_model_distribution_status()
    deepseek14b = next(model for model in status["models"] if model["id"] == "deepseek_r1_distill_qwen_14b_powerful")

    assert deepseek14b["mode"] == "POWERFUL"
    assert deepseek14b["load_allowed"] is False
    assert deepseek14b["status"] in {"detected_but_blocked_by_policy", "blocked_by_policy", "not_configured"}


def test_alpha_release_checklist_is_honest_about_manual_steps() -> None:
    checklist = build_alpha_release_checklist()

    assert checklist["status"] in {"ALPHA_READY_WITH_LIMITATIONS", "ALPHA_BLOCKED"}
    assert checklist["manual_steps_remaining"]
    assert "developer preview" in checklist["developer_preview_warning"].lower()


def test_distribution_artifacts_88_to_97_are_generated(tmp_path: Path) -> None:
    artifacts = write_distribution_artifacts(tmp_path / "outputs" / "distribution" / "run_001")
    names = {Path(path).name for path in artifacts}

    assert names == {
        "88_distribution_readiness.json",
        "89_distribution_readiness.md",
        "90_embedded_runtime_plan.json",
        "91_embedded_runtime_plan.md",
        "92_installer_verification.json",
        "93_installer_verification.md",
        "94_model_distribution_status.json",
        "95_model_distribution_status.md",
        "96_alpha_release_checklist.json",
        "97_alpha_release_checklist.md",
    }
    payload = json.loads((tmp_path / "outputs" / "distribution" / "run_001" / "94_model_distribution_status.json").read_text())
    assert payload["sequential_policy"]["parallel_llm_loads"] == 0


def test_first_run_state_exposes_distribution_model_status() -> None:
    state = build_first_run_state()
    snapshot = first_run_snapshot()

    assert state["distribution"]["model_policy"]["real_model_loading"] == "blocked"
    assert "DeepSeek" in snapshot
    assert "Embedded Python present" in snapshot
    assert "Developer Preview" in snapshot


def test_no_destructive_installer_behavior_is_triggered(monkeypatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Distribution readiness must not run installer commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert verify_installer_foundation()["status"] in {"VERIFIED", "NEEDS_ATTENTION"}


def test_no_c_drive_default_access() -> None:
    report = build_distribution_readiness()

    assert not report["install_root"].lower().startswith("c:")


def test_no_duplicate_runtime_systems_are_created() -> None:
    import agentic_network.installer.distribution as distribution

    assert distribution.build_embedded_runtime_plan()["status"] == "PLAN_ONLY"
    assert not hasattr(distribution, "RuntimeEngine")
    assert not hasattr(distribution, "InstallerRuntime")
