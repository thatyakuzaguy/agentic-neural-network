from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_network.config import PipelineConfig
from agentic_network.model_routing.router import DEFAULT_CONFIG_PATH, load_routing_config, resolve_model_route
from agentic_network.model_routing.runtime import build_pipeline_routing_plan
from agentic_network.pipeline.runner import PipelineRunner
from agentic_network.project_builder_orchestrator.runtime import run_end_to_end_project


def test_loads_default_routing_config() -> None:
    config = load_routing_config()

    assert config["default_mode"] == "FAST"
    assert config["vram_policy"] == "SEQUENTIAL"
    assert Path(DEFAULT_CONFIG_PATH).is_file()


def test_fast_product_routes_to_qwen3_product_finetuned() -> None:
    decision = resolve_model_route("product", "FAST")

    assert decision.status == "VALID"
    assert decision.selected_model == "qwen3_product_finetuned"


def test_powerful_product_routes_to_deepseek14b() -> None:
    decision = resolve_model_route("product", "POWERFUL")

    assert decision.status == "VALID"
    assert decision.selected_model == "deepseek_r1_distill_qwen_14b"


def test_unknown_agent_uses_fallback() -> None:
    decision = resolve_model_route("unknown_agent", "FAST")

    assert decision.status == "FALLBACK"
    assert decision.selected_model == "qwen3_base"


def test_invalid_mode_returns_invalid() -> None:
    decision = resolve_model_route("product", "TURBO")

    assert decision.status == "INVALID"
    assert decision.errors == ["invalid_mode:TURBO"]


def test_vram_policy_is_sequential() -> None:
    decision = resolve_model_route("architect", "POWERFUL")

    assert decision.vram_policy == "SEQUENTIAL"


def test_sequential_required_is_true() -> None:
    decision = resolve_model_route("code", "FAST")

    assert decision.sequential_required is True


def test_build_pipeline_routing_plan_creates_decisions_for_all_stages(tmp_path: Path) -> None:
    plan = build_pipeline_routing_plan(["product", "architect", "code"], run_dir=tmp_path)

    assert plan.status == "VALID"
    assert [item["agent_name"] for item in plan.decisions] == ["product", "architect", "code"]


def test_generates_72_model_routing_plan_md_json(tmp_path: Path) -> None:
    plan = build_pipeline_routing_plan(["product"], run_dir=tmp_path)

    assert any(path.endswith("72_model_routing_plan.md") for path in plan.artifacts)
    assert any(path.endswith("72_model_routing_plan.json") for path in plan.artifacts)
    assert all(Path(path).is_file() for path in plan.artifacts)


def test_generates_73_model_routing_trace_md(tmp_path: Path) -> None:
    plan = build_pipeline_routing_plan(["product"], run_dir=tmp_path)

    trace = [path for path in plan.artifacts if path.endswith("73_model_routing_trace.md")]
    assert len(trace) == 1
    assert "one routed stage at a time" in Path(trace[0]).read_text(encoding="utf-8")


def test_does_not_touch_models_directory(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/models"))

    build_pipeline_routing_plan(["product"], run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/models")) == before


def test_does_not_touch_adapters(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters"))

    build_pipeline_routing_plan(["architect"], run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters")) == before


def test_does_not_touch_datasets(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets"))

    build_pipeline_routing_plan(["code"], run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets")) == before


def test_pipeline_default_mode_remains_fast(tmp_path: Path) -> None:
    runner = PipelineRunner(_pipeline_config(tmp_path), mock=True)
    result = runner.run("Create a mock-only routing run", stages=["product"])
    summary = json.loads((Path(result.output_dir) / "summary.json").read_text(encoding="utf-8"))

    assert summary["execution_mode"] == "FAST"
    assert summary["model_routing_vram_policy"] == "SEQUENTIAL"
    assert summary["model_routing_decisions"][0]["selected_model"] == "qwen3_product_finetuned"


def test_project_builder_accepts_execution_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_CREATION_TARGETS", "1")
    monkeypatch.setenv("ANN_ALLOW_TEMP_PROJECT_SCAFFOLD_TARGETS", "1")
    monkeypatch.setenv("ANN_E2E_ORCHESTRATOR_ARTIFACTS_ROOT", str(tmp_path / "e2e"))

    result = run_end_to_end_project(
        "Build a SaaS CRM",
        tmp_path / "projects",
        execution_mode="POWERFUL",
    )

    assert result.execution_mode == "POWERFUL"
    assert result.model_routing_status == "VALID"
    assert result.model_routing_decisions[0]["selected_model"] == "deepseek_r1_distill_qwen_14b"


def test_desktop_model_routing_view_loads() -> None:
    from agentic_network.desktop_app.views.model_routing_view import (
        MODEL_ROUTING_MESSAGE,
        model_routing_snapshot,
    )

    assert "does not download models" in MODEL_ROUTING_MESSAGE
    assert "Default mode: FAST" in model_routing_snapshot()


def test_cli_smoke_generates_artifacts(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "python",
            "-m",
            "agentic_network.model_routing.run",
            "--mode",
            "FAST",
            "--stages",
            "product",
            "architect",
            "--run-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "VALID"
    assert (tmp_path / "72_model_routing_plan.json").is_file()


def _directory_metadata(path: Path) -> tuple[bool, int, tuple[str, ...]]:
    if not path.exists():
        return (False, 0, ())
    return (True, path.stat().st_mtime_ns, tuple(sorted(item.name for item in path.iterdir())))


def _pipeline_config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        deepseek_gguf_path=None,
        qwen_base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        qwen_adapter_path=Path("training/adapters/qwen-7b-python-expert-v5"),
        output_dir=tmp_path / "runs",
        max_new_tokens=128,
        temperature=0.2,
        top_p=0.85,
        context_length=2048,
        use_4bit=True,
        stage_isolation="inprocess",
    )
