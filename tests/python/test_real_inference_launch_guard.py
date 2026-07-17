from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    LOCAL_TEST_TOKEN,
    build_real_inference_launch_guard,
    write_real_inference_launch_guard_artifacts,
)


def test_launch_guard_blocks_without_token() -> None:
    guard = build_real_inference_launch_guard(confirm=True, approval_token=None, experimental=True)

    assert guard["status"] == "BLOCKED"
    assert any(check["name"] == "token_valid" for check in guard["failed_checks"])


def test_launch_guard_blocks_without_confirmation() -> None:
    guard = build_real_inference_launch_guard(confirm=False, approval_token=LOCAL_TEST_TOKEN, experimental=True)

    assert guard["status"] == "BLOCKED"
    assert any(check["name"] == "confirmation" for check in guard["failed_checks"])


def test_launch_guard_blocks_unavailable_backend_and_wrong_model() -> None:
    guard = build_real_inference_launch_guard(
        model_id="qwen3_8b_product_v9_repaired_v2_bullets",
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        experimental=True,
    )

    assert guard["status"] == "BLOCKED"
    failed_names = {check["name"] for check in guard["failed_checks"]}
    assert "model_id_exact" in failed_names
    assert "backend_ready" in failed_names
    assert guard["qwen3_loaded"] is False
    assert guard["deepseek_loaded"] is False
    assert guard["powerful_activated"] is False


def test_launch_guard_writes_artifacts(tmp_path: Path) -> None:
    artifacts = write_real_inference_launch_guard_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"136_real_inference_launch_guard.json", "137_real_inference_launch_guard.md"}
    payload = json.loads((tmp_path / "136_real_inference_launch_guard.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.1"
    assert payload["artifact_trace_path"].endswith("136_real_inference_launch_guard.json")
