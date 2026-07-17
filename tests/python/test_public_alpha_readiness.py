from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_public_alpha_readiness,
    write_public_alpha_readiness_artifacts,
)


def test_public_alpha_readiness_reports_limitations_and_blocks_public_release() -> None:
    readiness = build_public_alpha_readiness()

    assert readiness["status"] == "ALPHA_READY_WITH_LIMITATIONS"
    assert readiness["alpha"] == "ALPHA_READY_WITH_LIMITATIONS"
    assert readiness["beta"] == "BETA_BLOCKED"
    assert readiness["public_release"] == "PUBLIC_RELEASE_BLOCKED"
    assert readiness["qwen2_5"]["blocked"] is True
    assert readiness["qwen3"]["blocked"] is True
    assert readiness["deepseek"]["blocked"] is True
    assert readiness["powerful"]["blocked"] is True
    assert readiness["needs_wheelhouse"] is True
    assert readiness["needs_embedded_runtime"] is True


def test_public_alpha_readiness_artifacts(tmp_path: Path) -> None:
    artifacts = write_public_alpha_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"160_public_alpha_readiness.json", "161_public_alpha_readiness.md"}
    payload = json.loads((tmp_path / "160_public_alpha_readiness.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.0"
