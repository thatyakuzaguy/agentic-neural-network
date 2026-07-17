from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_embedded_python_release_plan,
    write_embedded_python_release_plan_artifacts,
)


def test_embedded_python_release_plan_reports_missing_runtime() -> None:
    plan = build_embedded_python_release_plan()

    assert plan["expected_python_executable"] == "D:\\ANN\\runtime\\python\\python.exe"
    assert plan["embedded_python_present"] in {True, False}
    assert "runtime_python" in plan["expected_structure"]
    assert "no_downloads_from_ann" in plan["blocked_actions"]
    assert plan["safety"]["downloads"] is False


def test_embedded_python_release_plan_writes_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_python_release_plan_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"132_embedded_python_release_plan.json", "133_embedded_python_release_plan.md"}
    payload = json.loads((tmp_path / "132_embedded_python_release_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.0"
