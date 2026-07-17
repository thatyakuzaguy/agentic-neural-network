from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.runtime_engine.backend_registry import get_backend, list_available_backends
from agentic_network.runtime_engine.backends.gguf_backend import GGUFBackend
from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend
from agentic_network.runtime_engine.backends.ollama_backend import OllamaBackend
from agentic_network.runtime_engine.backends.qwen_local_backend import QwenLocalBackend
from agentic_network.runtime_engine.backends.unsloth_qwen_backend import UnslothQwenBackend
from agentic_network.runtime_engine.executor import execute_agent_runtime
from agentic_network.runtime_engine.loader import get_runtime_metrics, reset_runtime_state


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    reset_runtime_state()


def test_mock_backend_load_works() -> None:
    backend = get_backend("mock")
    result = backend.load_model("qwen3_product_finetuned")

    assert result.status == "LOADED"
    assert result.loaded is True
    assert result.backend == "mock"


def test_mock_backend_generate_works() -> None:
    backend = get_backend("mock")
    result = backend.generate("qwen3_product_finetuned", "Build a CRM")

    assert result.status == "SUCCESS"
    assert "Sequential backend generation completed" in result.text
    assert result.tokens_in > 0
    assert result.tokens_out > 0


def test_mock_backend_unload_works() -> None:
    backend = get_backend("mock")
    result = backend.unload_model("qwen3_product_finetuned")

    assert result.status == "UNLOADED"
    assert result.unloaded is True


def test_ollama_backend_blocks_real_load_by_default() -> None:
    result = OllamaBackend({"allow_real_model_load": False}).load_model("qwen14b")

    assert result.status == "BLOCKED"
    assert result.loaded is False
    assert "blocked_by_policy" in result.errors[0]


def test_gguf_backend_blocks_real_load_by_default() -> None:
    result = GGUFBackend({"allow_real_model_load": False}).load_model("qwen14b.gguf")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_unsloth_backend_blocks_real_load_by_default() -> None:
    result = UnslothQwenBackend({"allow_real_model_load": False}).load_model("qwen3_adapter")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_backend_registry_lists_available_backends() -> None:
    assert list_available_backends() == [
        "mock",
        "embedded",
        "llama_cpp",
        "qwen_local",
        "ollama",
        "gguf",
        "unsloth_qwen",
    ]


def test_llama_cpp_backend_blocks_real_load_by_default() -> None:
    result = LlamaCppBackend({"allow_real_model_load": False}).load_model("qwen14b")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_qwen_local_backend_blocks_real_load_by_default() -> None:
    result = QwenLocalBackend({"allow_real_model_load": False}).load_model("qwen3_adapter")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_invalid_backend_returns_error() -> None:
    with pytest.raises(ValueError, match="invalid_runtime_backend"):
        get_backend("bad_backend")


def test_runtime_uses_mock_backend_by_default(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build a CRM", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert result.backend_name == "mock"
    assert result.generate_status == "SUCCESS"


def test_runtime_records_backend_in_artifacts(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Build a CRM", run_dir=tmp_path)

    assert any(path.endswith("77_backend_execution.md") for path in result.artifact_paths)
    assert any(path.endswith("77_backend_execution.json") for path in result.artifact_paths)
    assert any(path.endswith("78_model_inventory_snapshot.json") for path in result.artifact_paths)
    assert any(path.endswith("79_model_policy_decision.json") for path in result.artifact_paths)
    assert "Backend: mock" in (tmp_path / "77_backend_execution.md").read_text(encoding="utf-8")


def test_runtime_preserves_active_models_policy(tmp_path: Path) -> None:
    result = execute_agent_runtime("architect", "Design", run_dir=tmp_path)

    assert result.active_models <= 1
    assert get_runtime_metrics()["peak_active_models"] <= 1


def test_runtime_preserves_parallel_llm_loads_zero(tmp_path: Path) -> None:
    result = execute_agent_runtime("code", "Implement", run_dir=tmp_path)

    assert result.parallel_llm_loads == 0
    assert get_runtime_metrics()["parallel_llm_loads"] == 0


def test_no_models_directory_touched(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/models"))

    execute_agent_runtime("product", "Build", run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/models")) == before


def test_no_adapters_touched(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters"))

    execute_agent_runtime("architect", "Design", run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/adapters")) == before


def test_no_datasets_touched(tmp_path: Path) -> None:
    before = _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets"))

    execute_agent_runtime("test", "Plan tests", run_dir=tmp_path)

    assert _directory_metadata(Path("D:/AgenticEngineeringNetwork/training/datasets")) == before


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Backend adapters must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)

    assert execute_agent_runtime("security", "Review", run_dir=tmp_path).status == "SUCCESS"


def test_no_training(tmp_path: Path) -> None:
    result = execute_agent_runtime("reviewer", "Review", run_dir=tmp_path, backend_name="unsloth_qwen")

    assert result.status == "BLOCKED"
    assert any("blocked" in error for error in result.errors)


def test_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Backend adapters must not execute terminal commands.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert execute_agent_runtime("product", "Build", run_dir=tmp_path).status == "SUCCESS"


def test_desktop_runtime_still_loads() -> None:
    from agentic_network.desktop_app.views.runtime_engine_view import runtime_engine_snapshot

    snapshot = runtime_engine_snapshot()
    assert "Backend:" in snapshot
    assert "Real Model Load Allowed: False" in snapshot


def test_ollama_runtime_blocks_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Ollama blocked smoke must not use network.")

    monkeypatch.setattr(socket, "create_connection", fail_socket)
    result = execute_agent_runtime("product", "Build", run_dir=tmp_path, backend_name="ollama")

    assert result.status == "BLOCKED"
    assert result.backend_name == "ollama"
    assert result.load_status == "BLOCKED"


def _directory_metadata(path: Path) -> tuple[bool, int, tuple[str, ...]]:
    if not path.exists():
        return (False, 0, ())
    return (True, path.stat().st_mtime_ns, tuple(sorted(item.name for item in path.iterdir())))
