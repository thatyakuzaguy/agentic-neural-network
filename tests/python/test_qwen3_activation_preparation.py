from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    prepare_qwen3_activation,
    write_qwen3_activation_preparation_artifacts,
)


def test_qwen3_preparation_is_read_only_and_blocked_by_policy() -> None:
    prep = prepare_qwen3_activation()

    assert prep["status"] in {"PREPARED_BUT_BLOCKED_BY_POLICY", "MISSING_REQUIREMENTS"}
    assert prep["model_name"] == "qwen3_8b_product_v9_repaired_v2_bullets"
    assert prep["mode"] == "FAST"
    assert prep["qwen3_loaded"] is False
    assert prep["deepseek_touched"] is False
    assert prep["powerful_activated"] is False
    assert prep["policy"]["allow_real_model_load"] is False


def test_qwen3_preparation_artifacts_116_117(tmp_path: Path) -> None:
    artifacts = write_qwen3_activation_preparation_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "116_qwen3_activation_preparation.json",
        "117_qwen3_activation_preparation.md",
    }
