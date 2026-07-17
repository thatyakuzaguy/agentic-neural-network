from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_v1_1_installer_launcher_readiness_reports_foundation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    installer = tmp_path / "installer"
    installer.mkdir()
    for name in (
        "ann_launcher.ps1",
        "create_shortcut.ps1",
        "uninstall_ann.ps1",
        "verify_install.ps1",
        "install_ann.ps1",
        "ANN_Setup.bat",
        "ANN_Uninstall.bat",
    ):
        (installer / name).write_text("echo ok", encoding="utf-8")
    (tmp_path / "agentic_network" / "desktop_app").mkdir(parents=True)
    (tmp_path / "agentic_network" / "desktop_app" / "run.py").write_text("", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ann_runtime_engine.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "ann_model_inventory.json").write_text("{}", encoding="utf-8")

    readiness = activation.build_v1_1_installer_launcher_readiness()

    assert readiness["status"] == "INSTALLER_LAUNCHER_READY_FOUNDATION"
    assert readiness["launcher_exists"] is True
    assert readiness["shortcut_script_exists"] is True
    assert readiness["uninstaller_preserves_projects_models_outputs_data"] is True
    assert readiness["installer_excludes_protected_heavy_folders"] is True
    assert readiness["embedded_runtime_missing_documented"] is True
