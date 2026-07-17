from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics
from agentic_network.runtime_engine.local_model_activation import (
    build_beta_runtime_payload_readiness,
    write_beta_runtime_payload_readiness_artifacts,
)


def test_beta_runtime_payload_readiness_blocked_until_backend_and_first_inference() -> None:
    before = get_loaded_models()
    payload = build_beta_runtime_payload_readiness()
    blocker_ids = {item["id"] for item in payload["blockers"]}

    assert payload["status"] == "PAYLOAD_BLOCKED"
    assert payload["can_beta_payload_be_built"] is False
    assert not blocker_ids.intersection({"embedded_runtime_ready", "runtime_verified", "wheelhouse_ready"})
    assert "qwen25_backend_ready" in blocker_ids
    assert "first_inference_executed" in blocker_ids
    assert get_loaded_models() == before == []
    assert get_runtime_metrics().get("parallel_llm_loads", 0) == 0


def test_beta_runtime_payload_readiness_artifacts(tmp_path: Path) -> None:
    artifacts = write_beta_runtime_payload_readiness_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"184_beta_runtime_payload_readiness.json", "185_beta_runtime_payload_readiness.md"}
    payload = json.loads((tmp_path / "184_beta_runtime_payload_readiness.json").read_text(encoding="utf-8"))
    assert payload["version"] == "15.9"
