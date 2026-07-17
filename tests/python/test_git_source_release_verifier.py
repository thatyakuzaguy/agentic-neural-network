from __future__ import annotations

import json
from pathlib import Path

from scripts.runtime import verify_git_source_release


def _ready_bundle() -> dict[str, object]:
    return {
        "status": "HANDOFF_VERIFIED",
        "transfer_manifest": {
            "release_command_contract": {
                "repo_root_final_verifier_required": True,
                "command_sha256": {
                    "repo_root_final_verifier_command": "a" * 64,
                },
            },
        },
    }


def _patch_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_git_source_release,
        "build_runtime_materialization_watcher",
        lambda _root=None: {"status": "READY"},
    )
    monkeypatch.setattr(
        verify_git_source_release,
        "validate_wheelhouse_integrity",
        lambda _root=None: {"status": "HASH_VERIFIED"},
    )
    monkeypatch.setattr(
        verify_git_source_release,
        "build_embedded_runtime_package_audit",
        lambda _root=None: {"status": "PACKAGE_AUDIT_READY"},
    )
    monkeypatch.setattr(
        verify_git_source_release,
        "build_installer_rc_readiness",
        lambda: {"status": "RC_READY"},
    )
    monkeypatch.setattr(
        verify_git_source_release,
        "build_autonomous_complex_capability_gate",
        lambda: {"status": "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED"},
    )
    monkeypatch.setattr(verify_git_source_release, "verify_bundle", lambda _root: _ready_bundle())


def _source_root(tmp_path: Path) -> Path:
    for relative in verify_git_source_release.REQUIRED_SOURCE_PATHS:
        path = tmp_path / relative
        if "." in Path(relative).name:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("ok", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_git_source_release_ready_without_authenticode(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch)
    root = _source_root(tmp_path)

    report = verify_git_source_release.build_git_source_release_report(repo_root=root)

    assert report["status"] == "GIT_SOURCE_RELEASE_READY"
    assert report["exit_code"] == 0
    assert report["release_channel"] == "GIT_SOURCE"
    assert report["trusted_windows_installer_status"] == "NOT_CLAIMED"
    assert report["unsigned_installer_status"] == "USER_APPROVAL_REQUIRED"
    assert report["no_authenticode_required"] is True
    assert report["no_signing"] is True
    assert report["no_install"] is True
    assert report["no_download"] is True
    assert report["release_command_contract_ready"] is True


def test_git_source_release_blocks_missing_source_path(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch)
    root = _source_root(tmp_path)
    (root / "README.md").unlink()

    report = verify_git_source_release.build_git_source_release_report(repo_root=root)

    assert report["status"] == "GIT_SOURCE_RELEASE_BLOCKED"
    assert "source_path:README.md" in {blocker["id"] for blocker in report["blockers"]}


def test_git_source_release_blocks_missing_release_command_contract(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch)
    monkeypatch.setattr(
        verify_git_source_release,
        "verify_bundle",
        lambda _root: {"status": "HANDOFF_VERIFIED", "transfer_manifest": {}},
    )

    report = verify_git_source_release.build_git_source_release_report(repo_root=_source_root(tmp_path))

    assert report["status"] == "GIT_SOURCE_RELEASE_BLOCKED"
    assert "release_command_contract" in {blocker["id"] for blocker in report["blockers"]}
    assert report["release_command_contract_ready"] is False


def test_git_source_release_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    _patch_ready(monkeypatch)
    report = verify_git_source_release.build_git_source_release_report(repo_root=_source_root(tmp_path))
    output = tmp_path / "out"

    artifacts = verify_git_source_release.write_git_source_release_artifacts(report, output)

    assert {Path(path).name for path in artifacts} == {
        "375_git_source_release_verification.json",
        "376_git_source_release_verification.md",
    }
    payload = json.loads((output / "375_git_source_release_verification.json").read_text(encoding="utf-8"))
    markdown = (output / "376_git_source_release_verification.md").read_text(encoding="utf-8")
    assert payload["status"] == "GIT_SOURCE_RELEASE_READY"
    assert "Unsigned Installer: `USER_APPROVAL_REQUIRED`" in markdown


def test_git_source_release_cli_returns_exit_code(monkeypatch, tmp_path: Path, capsys) -> None:
    _patch_ready(monkeypatch)
    root = _source_root(tmp_path)

    exit_code = verify_git_source_release.main(["--repo-root", str(root)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "GIT_SOURCE_RELEASE_READY" in output
    assert "Trusted Windows Installer: NOT_CLAIMED" in output
