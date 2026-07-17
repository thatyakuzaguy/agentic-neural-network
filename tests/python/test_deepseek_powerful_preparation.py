from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    prepare_deepseek_powerful_activation,
    write_deepseek_powerful_preparation_artifacts,
)


def test_deepseek_powerful_preparation_is_read_only_and_blocked() -> None:
    result = prepare_deepseek_powerful_activation()

    assert result["model_name"] == "deepseek_r1_distill_qwen_14b"
    assert result["mode"] == "POWERFUL"
    assert result["status"] in {"POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY", "MISSING_REQUIREMENTS"}
    assert result["model_load_attempted"] is False
    assert result["powerful_activated"] is False
    assert result["qwen3_touched"] is False


def test_deepseek_powerful_preparation_artifacts(tmp_path: Path) -> None:
    artifacts = write_deepseek_powerful_preparation_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"128_deepseek_powerful_preparation.json", "129_deepseek_powerful_preparation.md"}
    payload = json.loads((tmp_path / "128_deepseek_powerful_preparation.json").read_text(encoding="utf-8"))
    assert payload["version"] == "13.8"
