from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_full_uninstall_covers_generated_projects_and_validation_markers() -> None:
    script = (REPO_ROOT / "installer" / "uninstall_ann.ps1").read_text(encoding="utf-8")

    assert 'if ($RemoveProjects) { $remove += @("projects", "generated-projects") }' in script
    assert '"local_smoke_validation.json", "clean_machine_external_validation.json"' in script


def test_native_uninstaller_defers_self_cleanup_until_launcher_exits() -> None:
    launcher = (REPO_ROOT / "installer" / "AnnPowerShellLauncher.cs").read_text(
        encoding="utf-8"
    )
    script = (REPO_ROOT / "installer" / "uninstall_ann.ps1").read_text(encoding="utf-8")

    assert 'EnvironmentVariables["ANN_LAUNCHER_PID"]' in launcher
    assert "Wait-Process -Id $launcherPid" in script
    assert 'Start-Process -FilePath "powershell.exe" -WindowStyle Hidden' in script
    assert '"config", "installer", "desktop"' not in script


def test_install_manifest_declares_generated_projects_preserved_by_default() -> None:
    script = (REPO_ROOT / "installer" / "install_ann.ps1").read_text(encoding="utf-8")

    assert (
        'preserved_by_default = @("projects", "generated-projects", "models", "outputs", "data", "logs")'
        in script
    )


def test_installer_copies_native_uninstaller_into_install_root() -> None:
    script = (REPO_ROOT / "installer" / "install_ann.ps1").read_text(encoding="utf-8")

    assert '"ANN_Uninstall.exe", "uninstall_ann.ps1"' in script
