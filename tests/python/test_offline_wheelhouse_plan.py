from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_offline_wheelhouse_plan,
    write_offline_wheelhouse_plan_artifacts,
)


def test_offline_wheelhouse_plan_is_declarative_and_non_installing() -> None:
    plan = build_offline_wheelhouse_plan()

    assert plan["status"] in {"WHEELHOUSE_REQUIRED", "WHEELHOUSE_READY"}
    assert plan["not_installed_by_ann"] is True
    assert plan["safety"]["downloads"] is False
    assert plan["safety"]["dependency_install"] is False
    assert "required_for_desktop" in plan["categories"]
    assert "required_for_qwen25_gguf" in plan["categories"]
    assert "required_for_qwen3_hf" in plan["categories"]
    assert "required_for_deepseek_hf" in plan["categories"]
    assert any(package["package"] == "llama-cpp-python" for package in plan["packages"])


def test_offline_wheelhouse_plan_artifacts(tmp_path: Path) -> None:
    artifacts = write_offline_wheelhouse_plan_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"138_offline_wheelhouse_plan.json", "139_offline_wheelhouse_plan.md"}
    payload = json.loads((tmp_path / "138_offline_wheelhouse_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.2"
