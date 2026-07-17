from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    validate_wheelhouse_integrity,
    write_wheelhouse_integrity_artifacts,
)


def test_wheelhouse_missing_reports_missing(tmp_path: Path) -> None:
    result = validate_wheelhouse_integrity(tmp_path / "missing-wheelhouse", tmp_path / "lock.json")

    assert result["status"] == "WHEELHOUSE_MISSING"
    assert "wheelhouse_directory_missing" in result["errors"]


def test_lockfile_missing_reports_missing(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()

    result = validate_wheelhouse_integrity(wheelhouse, tmp_path / "missing-lock.json")

    assert result["status"] == "LOCKFILE_MISSING"
    assert "lockfile_missing" in result["errors"]


def test_hash_mismatch_detected_with_small_fixture(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    wheel = wheelhouse / "demo-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"demo-wheel")
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "version": "14.5",
                "verification_status": "declared",
                "wheels": [
                    {
                        "name": "demo",
                        "version": "1.0.0",
                        "filename": wheel.name,
                        "sha256": "0" * 64,
                        "required": True,
                        "role": "desktop",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_wheelhouse_integrity(wheelhouse, lock)

    assert result["status"] == "HASH_MISMATCH"
    assert result["verification_results"][0]["status"] == "hash_mismatch"


def test_wheelhouse_integrity_artifacts(tmp_path: Path) -> None:
    artifacts = write_wheelhouse_integrity_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"148_wheelhouse_integrity.json", "149_wheelhouse_integrity.md"}
    payload = json.loads((tmp_path / "148_wheelhouse_integrity.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.5"
