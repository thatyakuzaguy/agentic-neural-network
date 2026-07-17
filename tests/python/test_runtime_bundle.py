from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from agentic_network.desktop_app.views.confirmation_dialog import (
    build_cancelled_decision,
    build_confirmation_request,
    record_confirmation_trace,
)
from agentic_network.desktop_app.views.token_dialog import build_token_request
from agentic_network.runtime_bundle.runtime import (
    build_runtime_manifest,
    estimate_runtime_size,
    list_runtime_dependencies,
    write_runtime_bundle_artifacts,
)
from agentic_network.runtime_bundle.validation import validate_runtime_bundle


def test_runtime_manifest_detects_local_dependencies() -> None:
    manifest = build_runtime_manifest()

    assert manifest.python_version
    assert manifest.python_executable
    assert manifest.python_runtime.kind in {"embedded", "venv", "conda", "system"}
    assert "mock" in manifest.available_backends


def test_embedded_python_detection_from_config(tmp_path: Path) -> None:
    embedded = tmp_path / "embedded" / "python.exe"
    embedded.parent.mkdir(parents=True)
    embedded.write_text("", encoding="utf-8")
    config = tmp_path / "ann_runtime_bundle.json"
    config.write_text(
        json.dumps({"embedded_python_executable": str(embedded), "dependencies": ["python"]}),
        encoding="utf-8",
    )

    manifest = build_runtime_manifest(config)

    assert manifest.python_candidates[0].kind == "embedded"
    assert manifest.python_candidates[0].executable == str(embedded.resolve())


def test_runtime_validation() -> None:
    validation = validate_runtime_bundle()

    assert validation.status in {"VALID", "INVALID"}
    assert "mock" in validation.available_backends


def test_runtime_dependencies_and_size_are_read_only(monkeypatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Runtime Bundle must not execute installers or shells.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert list_runtime_dependencies()
    assert estimate_runtime_size() >= 0


def test_runtime_bundle_no_internet(monkeypatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Runtime Bundle must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)

    assert build_runtime_manifest().python_executable


def test_confirmation_request_and_token_metadata() -> None:
    request = build_confirmation_request(
        action="Apply Patch",
        project="crm-small-businesses",
        patch="patch_001.diff",
        risk="medium",
        files=5,
    )
    token = build_token_request("Apply Patch", token="secret-token")

    assert request.action == "Apply Patch"
    assert request.risk == "MEDIUM"
    assert request.files == 5
    assert token.token_provided is True


def test_confirmation_trace_artifact(tmp_path: Path) -> None:
    request = build_confirmation_request(action="Retry", project="crm")
    decision = build_cancelled_decision("Retry")

    path = record_confirmation_trace(tmp_path / "outputs" / "runs" / "run_001", request, decision)

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert Path(path).name == "85_confirmation_trace.json"
    assert payload["request"]["action"] == "Retry"
    assert payload["decision"]["cancelled"] is True
    assert payload["safety"]["auto_approval"] is False


def test_runtime_bundle_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_bundle_artifacts(tmp_path / "outputs" / "runs" / "run_001")

    assert any(path.endswith("84_runtime_bundle_manifest.json") for path in artifacts)
    assert any(path.endswith("87_runtime_validation.md") for path in artifacts)
    for artifact in artifacts:
        assert Path(artifact).is_file()
