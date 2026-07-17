"""Read-only Final Release Verification view for ANN Desktop."""

from __future__ import annotations

from typing import Any

from agentic_network.runtime_engine.local_model_activation import build_final_release_closure_pack
from scripts.runtime.verify_final_release import build_cli_final_release_report

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QLabel = None
    QPlainTextEdit = None
    QPushButton = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


FINAL_RELEASE_MESSAGE = (
    "Final Release Verification is read-only. It does not sign binaries, install packages, "
    "download files, load models, run inference, or modify clean-machine evidence."
)

RELEASE_OPERATOR_PREFLIGHT_COMMAND = (
    "PYTHONPATH=. python scripts/runtime/verify_release_operator_environment.py "
    '--installer-root installer --certificate-thumbprint "<CERT_THUMBPRINT>" '
    "--output-dir outputs/runtime_finalization_20260707"
)

FINAL_RELEASE_VERIFIER_COMMAND = (
    "PYTHONPATH=. python scripts/runtime/verify_final_release.py "
    "--install-root D:\\ANN --installer-root installer "
    "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF "
    "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
    "--signing-evidence installer\\release_signing_evidence.json "
    '--certificate-thumbprint "<CERT_THUMBPRINT>" '
    "--output-dir outputs/runtime_finalization_20260707"
)


def final_release_snapshot() -> str:
    """Render the aggregate final release verifier for Desktop."""

    report = build_cli_final_release_report(
        install_root="D:\\ANN",
        installer_root="installer",
        bundle_root="outputs/release_candidates/ANN_RC_HANDOFF",
        clean_machine_marker="D:\\ANN\\clean_machine_external_validation.json",
        signing_evidence="installer\\release_signing_evidence.json",
        certificate_thumbprint="<CERT_THUMBPRINT>",
    )
    external = _dict_item(report, "external_release_evidence_report")
    operator = _dict_item(report, "release_operator_environment")
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    blocker_ids = [str(item.get("id", "unknown")) for item in blockers if isinstance(item, dict)]
    external_blockers = report.get("external_release_evidence_blockers")
    if not isinstance(external_blockers, list):
        external_blockers = external.get("blockers") if isinstance(external.get("blockers"), list) else []
    external_blocker_ids = [
        str(item.get("id", "unknown")) for item in external_blockers if isinstance(item, dict)
    ]
    operator_blockers = report.get("release_operator_environment_blockers")
    if not isinstance(operator_blockers, list):
        operator_blockers = operator.get("blockers") if isinstance(operator.get("blockers"), list) else []
    operator_blocker_ids = [
        str(item.get("id", "unknown")) for item in operator_blockers if isinstance(item, dict)
    ]
    path_contract = report.get("final_release_path_contract")
    path_contract_items = path_contract if isinstance(path_contract, list) else []
    operator_command = report.get("release_operator_environment_command")
    signing_commands = report.get("release_signing_commands")
    closure = build_final_release_closure_pack()
    lines = [
        "Final Release Verification",
        "",
        FINAL_RELEASE_MESSAGE,
        "",
        f"Status: {report['status']}",
        f"Exit Code: {report['exit_code']}",
        f"Runtime Materialization: {report['runtime_materialization']}",
        f"Wheelhouse Integrity: {report['wheelhouse_integrity']}",
        f"Embedded Package Audit: {report['embedded_package_audit']}",
        f"Installer RC: {report['installer_rc']}",
        f"Installer Final: {report['installer_final']}",
        f"Final Release Bridge: {report['final_release_bridge']}",
        f"Public Release: {report['public_release']}",
        f"ANN Finalization: {report['ann_finalization']}",
        f"Final Release Path Contract: {_pass_fail(report.get('final_release_path_contract_ready') is True)}",
        f"Release Signing Plan: {report.get('release_signing_plan_status', 'UNKNOWN')}",
        f"Release Signing Plan Safety: {_pass_fail(report.get('release_signing_plan_safety_ready') is True)}",
        f"External Evidence Safety: {_pass_fail(report.get('external_release_evidence_safety_ready') is True)}",
        f"Operator Environment Safety: {_pass_fail(report.get('release_operator_environment_safety_ready') is True)}",
        f"Release Evidence Contract: {_pass_fail(report.get('release_evidence_contract_ready') is True)}",
        f"Operator/Signing Thumbprint Match: {_pass_fail(report.get('release_operator_signing_thumbprint_match') is True)}",
        f"Local Install Smoke: {report['local_install_smoke_passed']}",
        f"External Clean Machine: {report['external_clean_machine_passed']}",
        f"Signed Installer: {report['signed_installer']}",
        f"Code Signing: {report['code_signing_status']}",
        f"Blockers: {', '.join(blocker_ids) if blocker_ids else 'none'}",
        f"Next Step: {report['next_step']}",
        "",
        "Final Release Closure Pack:",
        f"- Status: {closure['status']}",
        f"- Handoff: {closure['handoff_status']}",
        f"- Signing Plan: {closure['release_signing_plan_status']}",
        f"- Manual Blockers: {', '.join(_manual_blocker_ids(closure))}",
        f"- Acceptance: {closure['acceptance_rule']}",
        "",
        "External Release Evidence:",
        f"- Status: {external['status']}",
        f"- Handoff Bundle: {external['bundle']['status']}",
        f"- Handoff Installer Hash Match: {_pass_fail(external['installer_hashes_match_handoff'])}",
        f"- Signing: {external['signing']['status']}",
        f"- Signed Installer: {_pass_fail(external['signing'].get('signed_installer') is True)}",
        f"- Authenticode Timestamp: {_timestamp_summary(external['signing'])}",
        f"- Release Signing Evidence: {_pass_fail(external['release_signing_evidence_valid'])}",
        f"- Clean-Machine Signing Evidence Hash Match: {_pass_fail(external['clean_machine_signing_evidence_hash_match'])}",
        f"- Clean-Machine Transfer Manifest Hash Match: {_pass_fail(external['clean_machine_transfer_manifest_hash_match'])}",
        f"- Clean Machine: {external['clean_machine']['status']}",
        f"- Clean-Machine Installer Hash Match: {_pass_fail(external['installer_hashes_match_clean_machine'])}",
        f"- Blockers: {', '.join(external_blocker_ids) if external_blocker_ids else 'none'}",
        f"- Next Step: {external['next_step']}",
        "",
        "Release Operator Environment:",
        f"- Status: {operator['status']}",
        f"- Code Signing Readiness: {operator['code_signing_readiness'].get('status')}",
        f"- Release Signing Plan: {report.get('release_signing_plan_status', operator.get('release_signing_plan_status', 'UNKNOWN'))}",
        f"- Certificate Thumbprint: {operator['certificate_thumbprint'] or 'missing'}",
        f"- Certificate Thumbprint SHA256: {operator.get('certificate_thumbprint_sha256') or 'missing'}",
        f"- Blockers: {', '.join(operator_blocker_ids) if operator_blocker_ids else 'none'}",
        f"- Next Step: {operator['next_step']}",
        "",
        "Final Release Path Contract:",
        *_path_contract_lines(path_contract_items),
        "",
        "Release Safety Invariants:",
        f"- Release Signing Plan Safety: {_pass_fail(report.get('release_signing_plan_safety_ready') is True)}",
        f"- External Evidence Safety: {_pass_fail(report.get('external_release_evidence_safety_ready') is True)}",
        f"- Operator Environment Safety: {_pass_fail(report.get('release_operator_environment_safety_ready') is True)}",
        "",
        "Release Commands:",
        f"- Operator Preflight: {_command_or_fallback(operator_command, RELEASE_OPERATOR_PREFLIGHT_COMMAND)}",
        f"- Final Verifier: {FINAL_RELEASE_VERIFIER_COMMAND}",
        *_release_signing_command_lines(signing_commands),
        "",
        "Safety:",
        f"- No internet: {report['no_internet']}",
        f"- No downloads: {report['no_downloads']}",
        f"- No installs: {report['no_installs']}",
        f"- No external install: {external['no_install']}",
        f"- No external signing: {external['no_signing']}",
        f"- No operator signing: {operator['no_signing']}",
        f"- No operator install: {operator['no_install']}",
        f"- No model load: {report['no_model_load']}",
        f"- No inference: {report['no_inference']}",
        f"- No training: {report['no_training']}",
    ]
    return "\n".join(lines)


def _dict_item(report: dict[str, object], key: str) -> dict[str, Any]:
    value = report.get(key)
    return value if isinstance(value, dict) else {}


def _pass_fail(value: bool) -> str:
    return "PASS" if value else "BLOCKED"


def _manual_blocker_ids(closure: dict[str, Any]) -> list[str]:
    blockers = closure.get("manual_blockers")
    if not isinstance(blockers, list):
        return ["none"]
    ids = [
        str(item.get("id", "unknown"))
        for item in blockers
        if isinstance(item, dict) and item.get("status") != "PASSED"
    ]
    return ids or ["none"]


def _path_contract_lines(items: list[object]) -> list[str]:
    if not items:
        return ["- none: UNKNOWN expected=none actual=none"]
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- "
            f"{item.get('id', 'unknown')}: "
            f"{_pass_fail(item.get('passed') is True)} "
            f"expected={item.get('expected', 'unknown')} "
            f"actual={item.get('actual', 'unknown')}"
        )
    return lines or ["- none: UNKNOWN expected=none actual=none"]


def _command_or_fallback(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _release_signing_command_lines(commands: object) -> list[str]:
    if not isinstance(commands, list) or not commands:
        return ["- Release Signing Plan Commands: none"]
    lines = ["- Release Signing Plan Commands:"]
    for command in commands:
        if isinstance(command, str) and command:
            lines.append(f"  - {command}")
    return lines if len(lines) > 1 else ["- Release Signing Plan Commands: none"]


def _timestamp_summary(signing: dict[str, Any]) -> str:
    missing = signing.get("untimestamped_binaries")
    if isinstance(missing, list) and missing:
        return "BLOCKED_MISSING_TIMESTAMP"
    if signing.get("signed_installer") is True:
        return "PASS"
    return "BLOCKED"


if PYSIDE6_AVAILABLE:

    class FinalReleaseView(QWidget):  # type: ignore[misc]
        """Read-only final release verification view."""

        def __init__(self) -> None:
            super().__init__()
            layout = QVBoxLayout(self)
            title = QLabel("Final Release Verification")
            title.setAccessibleName("Final Release Verification view title")
            self.body = QPlainTextEdit(final_release_snapshot())
            self.body.setReadOnly(True)
            self.body.setAccessibleName("Final Release Verification read only status")
            refresh = QPushButton("Refresh")
            refresh.setAccessibleName("Refresh Final Release Verification")
            refresh.clicked.connect(self._refresh)
            layout.addWidget(title)
            layout.addWidget(self.body, 1)
            layout.addWidget(refresh)

        def set_bundle(self, _bundle: Any, _snapshot: dict[str, Any]) -> None:
            self._refresh()

        def _refresh(self) -> None:
            self.body.setPlainText(final_release_snapshot())

else:

    class FinalReleaseView:  # type: ignore[no-redef]
        pass
