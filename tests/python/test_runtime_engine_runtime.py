from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.runtime_engine.executor import execute_agent_runtime
from agentic_network.runtime_engine.loader import (
    get_loaded_models,
    get_runtime_metrics,
    load_model,
    reset_runtime_state,
    unload_model,
)
from agentic_network.runtime_engine.scheduler import run_pipeline_sequential


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    reset_runtime_state()


def test_load_model() -> None:
    result = load_model("qwen3_product_finetuned")

    assert result["status"] == "LOADED"
    assert get_loaded_models() == ["qwen3_product_finetuned"]


def test_unload_model() -> None:
    load_model("qwen3_product_finetuned")
    result = unload_model("qwen3_product_finetuned")

    assert result["status"] == "UNLOADED"
    assert get_loaded_models() == []


def test_only_one_active_model() -> None:
    load_model("qwen3_product_finetuned")
    load_model("qwen3_architect_finetuned")

    assert get_loaded_models() == ["qwen3_architect_finetuned"]
    assert get_runtime_metrics()["active_models"] == 1
    assert get_runtime_metrics()["peak_active_models"] == 1


def test_parallel_llm_loads_zero() -> None:
    load_model("qwen3_product_finetuned")
    load_model("deepseek_r1_distill_qwen_14b")

    assert get_runtime_metrics()["parallel_llm_loads"] == 0


def test_fast_uses_qwen3_route(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build a CRM", execution_mode="FAST", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert result.selected_model == "qwen3_product_finetuned"
    assert result.active_models == 0


def test_powerful_uses_deepseek14b_route(tmp_path: Path) -> None:
    result = execute_agent_runtime("architect", "Design architecture", execution_mode="POWERFUL", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert result.selected_model == "deepseek_r1_distill_qwen_14b"
    assert result.active_models == 0


def test_sequential_pipeline_executes(tmp_path: Path) -> None:
    result = run_pipeline_sequential(["product", "architect", "code"], "FAST", task="Build app", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert [item["agent_name"] for item in result.results] == ["product", "architect", "code"]
    assert result.active_models == 0
    assert result.parallel_llm_loads == 0


def test_metrics_generated(tmp_path: Path) -> None:
    execute_agent_runtime("product", "Build", run_dir=tmp_path)

    metrics = get_runtime_metrics()
    assert metrics["load_count"] == 1
    assert metrics["unload_count"] == 1
    assert metrics["peak_vram_mb"] >= 1


def test_74_artifacts_generated(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build", run_dir=tmp_path)

    assert any(path.endswith("74_runtime_execution.md") for path in result.artifact_paths)
    assert any(path.endswith("74_runtime_execution.json") for path in result.artifact_paths)
    assert all(Path(path).is_file() for path in result.artifact_paths)


def test_75_metrics_generated(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build", run_dir=tmp_path)

    assert any(path.endswith("75_runtime_metrics.json") for path in result.artifact_paths)
    assert (tmp_path / "75_runtime_metrics.json").is_file()


def test_76_trace_generated(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build", run_dir=tmp_path)

    trace = tmp_path / "76_runtime_trace.md"
    assert str(trace) in result.artifact_paths
    assert "active_models <= 1" in trace.read_text(encoding="utf-8")


def test_78_79_inventory_policy_artifacts_generated(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build", run_dir=tmp_path)

    assert any(path.endswith("78_model_inventory_snapshot.json") for path in result.artifact_paths)
    assert any(path.endswith("79_model_policy_decision.json") for path in result.artifact_paths)
    assert (tmp_path / "78_model_inventory_snapshot.json").is_file()
    assert (tmp_path / "79_model_policy_decision.json").is_file()


def test_desktop_runtime_loads() -> None:
    from agentic_network.desktop_app.views.runtime_engine_view import (
        RUNTIME_ENGINE_MESSAGE,
        runtime_engine_snapshot,
    )

    assert "does not download models" in RUNTIME_ENGINE_MESSAGE
    assert "Runtime Engine" in runtime_engine_snapshot()


def test_no_model_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Runtime engine must not download models.")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert execute_agent_runtime("product", "Build", run_dir=tmp_path).status == "SUCCESS"


def test_no_dataset_modifications(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets"))

    execute_agent_runtime("product", "Build", run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets")) == before


def test_no_adapter_modifications(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters"))

    execute_agent_runtime("architect", "Build", run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters")) == before


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Runtime engine must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)

    assert execute_agent_runtime("security", "Review", run_dir=tmp_path).status == "SUCCESS"


def test_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Runtime engine must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert execute_agent_runtime("reviewer", "Review", run_dir=tmp_path).status == "SUCCESS"


def _directory_metadata(path: Path) -> tuple[bool, int, tuple[str, ...]]:
    if not path.exists():
        return (False, 0, ())
    return (True, path.stat().st_mtime_ns, tuple(sorted(item.name for item in path.iterdir())))
