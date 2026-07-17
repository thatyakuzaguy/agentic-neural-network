from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    prepare_qwen3_controlled_activation,
    write_qwen3_controlled_activation_artifacts,
)


def test_qwen3_controlled_activation_is_preparation_only() -> None:
    result = prepare_qwen3_controlled_activation()

    assert result["model_name"] == "qwen3_8b_product_v9_repaired_v2_bullets"
    assert result["status"] in {"PREPARED_BUT_BLOCKED_BY_POLICY", "MISSING_REQUIREMENTS"}
    assert result["qwen3_loaded"] is False
    assert result["deepseek_touched"] is False
    assert result["powerful_activated"] is False


def test_qwen3_controlled_activation_artifacts(tmp_path: Path) -> None:
    artifacts = write_qwen3_controlled_activation_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"126_qwen3_controlled_activation.json", "127_qwen3_controlled_activation.md"}
    payload = json.loads((tmp_path / "126_qwen3_controlled_activation.json").read_text(encoding="utf-8"))
    assert payload["version"] == "13.7"
