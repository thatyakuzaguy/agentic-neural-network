from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import build_runtime_gap_report, write_runtime_gap_report_artifacts


def test_runtime_gap_report_separates_ann_and_environment_gaps() -> None:
    report = build_runtime_gap_report()

    assert report["status"] in {"ANN_READY_ENVIRONMENT_NOT_READY", "READY"}
    assert report["ANN_READY"]["gates"] is True
    assert "torch_cuda" in report["ENVIRONMENT_MISSING"]
    assert "llama_cpp_binding" in report["ENVIRONMENT_MISSING"]
    assert "packaged_embedded_runtime" in report["INSTALLER_MISSING"]
    assert report["qwen2_5"]["blocked_by_backend"] is True
    assert report["qwen3"]["loaded"] is False
    assert report["deepseek"]["powerful_activated"] is False


def test_runtime_gap_report_artifacts(tmp_path: Path) -> None:
    artifacts = write_runtime_gap_report_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"144_runtime_gap_report.json", "145_runtime_gap_report.md"}
    payload = json.loads((tmp_path / "144_runtime_gap_report.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.4"
