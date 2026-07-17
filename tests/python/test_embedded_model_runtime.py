from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from agentic_network.runtime_engine.backend_registry import get_backend, list_available_backends
from agentic_network.runtime_engine.backends.embedded_backend import EmbeddedBackend
from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend
from agentic_network.runtime_engine.backends.qwen_local_backend import QwenLocalBackend
from agentic_network.runtime_engine.executor import execute_agent_runtime
from agentic_network.runtime_engine.loader import get_runtime_metrics, reset_runtime_state
from agentic_network.runtime_engine.model_inventory import (
    load_model_inventory,
    resolve_model_record,
)
from agentic_network.runtime_engine.model_policy import load_model_policy, validate_model_load_request


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    reset_runtime_state()


def test_model_inventory_loads() -> None:
    inventory = load_model_inventory()

    assert inventory.version == 2
    assert any(record.name == "qwen3_8b_product_v9_repaired_v2_bullets" for record in inventory.models)


def test_model_inventory_validates_disabled_model() -> None:
    record = resolve_model_record("deepseek_r1_distill_qwen_14b")

    assert record is not None
    assert record.enabled is False
    assert record.validation_status == "DISABLED"
    assert "model_disabled" in (record.warnings or [])


def test_model_path_outside_allowed_roots_blocked(tmp_path: Path) -> None:
    inventory_path = _inventory_config(tmp_path, path="/tmp/ann/model.gguf")
    record = load_model_inventory(inventory_path).models[0]

    assert record.validation_status == "BLOCKED"
    assert "model_path_root_not_allowed" in (record.errors or [])


def test_c_drive_blocked_by_default(tmp_path: Path) -> None:
    inventory_path = _inventory_config(tmp_path, path="C:/ANN/models/qwen.gguf")
    record = load_model_inventory(inventory_path).models[0]

    assert record.validation_status == "BLOCKED"
    assert "model_path_c_drive_blocked" in (record.errors or [])


def test_mnt_c_blocked_by_default(tmp_path: Path) -> None:
    inventory_path = _inventory_config(tmp_path, path="/mnt/c/ANN/models/qwen.gguf")
    record = load_model_inventory(inventory_path).models[0]

    assert record.validation_status == "BLOCKED"
    assert "model_path_c_drive_blocked" in (record.errors or [])


def test_model_policy_loads() -> None:
    policy = load_model_policy()

    assert policy.allow_real_model_load is False
    assert policy.max_loaded_models == 1
    assert policy.vram_policy == "SEQUENTIAL"


def test_allow_real_model_load_false_blocks_real_load() -> None:
    decision = validate_model_load_request("deepseek_r1_distill_qwen_14b", "deepseek_unsloth", "POWERFUL")

    assert decision.allowed is False
    assert "real_model_load_blocked_by_policy" in decision.errors


def test_allow_model_download_false_blocks_downloads(tmp_path: Path) -> None:
    policy_path = _policy_config(tmp_path, allow_model_download=True)
    policy = load_model_policy(policy_path)
    decision = validate_model_load_request("deepseek_r1_distill_qwen_14b", "mock", "FAST", policy=policy)

    assert decision.allowed is False
    assert "model_downloads_must_remain_disabled" in decision.errors


def test_allow_training_false_blocks_training(tmp_path: Path) -> None:
    policy_path = _policy_config(tmp_path, allow_training=True)
    policy = load_model_policy(policy_path)
    decision = validate_model_load_request("deepseek_r1_distill_qwen_14b", "mock", "FAST", policy=policy)

    assert decision.allowed is False
    assert "training_must_remain_disabled" in decision.errors


def test_llama_cpp_backend_exists() -> None:
    assert "llama_cpp" in list_available_backends()
    assert get_backend("llama_cpp").name == "llama_cpp"


def test_llama_cpp_backend_blocks_when_policy_false() -> None:
    result = LlamaCppBackend({"allow_real_model_load": False}).load_model("deepseek_r1_distill_qwen_14b")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_qwen_local_backend_exists() -> None:
    assert "qwen_local" in list_available_backends()
    assert get_backend("qwen_local").name == "qwen_local"


def test_qwen_local_backend_blocks_when_policy_false() -> None:
    result = QwenLocalBackend({"allow_real_model_load": False}).load_model("qwen3_product_finetuned")

    assert result.status == "BLOCKED"
    assert result.loaded is False


def test_embedded_backend_exists() -> None:
    assert "embedded" in list_available_backends()
    assert EmbeddedBackend({"allow_real_model_load": False}).health_check().status == "BLOCKED_BY_POLICY"


def test_runtime_records_inventory_snapshot(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Embedded inventory", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert (tmp_path / "78_model_inventory_snapshot.json").is_file()
    payload = json.loads((tmp_path / "78_model_inventory_snapshot.json").read_text(encoding="utf-8"))
    assert payload["models"]


def test_runtime_records_policy_decision(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Embedded policy", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert (tmp_path / "79_model_policy_decision.json").is_file()
    payload = json.loads((tmp_path / "79_model_policy_decision.json").read_text(encoding="utf-8"))
    assert payload["backend"] == "mock"
    assert payload["allowed"] is True


def test_runtime_falls_back_to_mock_safely(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Mock fallback", run_dir=tmp_path)

    assert result.status == "SUCCESS"
    assert result.backend_name == "mock"
    assert result.generate_status == "SUCCESS"


def test_active_models_less_than_or_equal_one_preserved(tmp_path: Path) -> None:
    result = execute_agent_runtime("architect", "Sequential policy", run_dir=tmp_path)

    assert result.active_models <= 1
    assert get_runtime_metrics()["peak_active_models"] <= 1


def test_parallel_llm_loads_zero_preserved(tmp_path: Path) -> None:
    result = execute_agent_runtime("code", "Sequential policy", run_dir=tmp_path)

    assert result.parallel_llm_loads == 0
    assert get_runtime_metrics()["parallel_llm_loads"] == 0


def test_no_models_modified(tmp_path: Path) -> None:
    path = Path("D:/AgenticEngineeringNetwork/models")
    before = _directory_metadata(path)

    execute_agent_runtime("product", "No model mutation", run_dir=tmp_path, backend_name="qwen_local")

    assert _directory_metadata(path) == before


def test_no_adapters_modified(tmp_path: Path) -> None:
    path = Path("D:/AgenticEngineeringNetwork/training/adapters")
    before = _directory_metadata(path)

    execute_agent_runtime("product", "No adapter mutation", run_dir=tmp_path, backend_name="qwen_local")

    assert _directory_metadata(path) == before


def test_no_datasets_modified(tmp_path: Path) -> None:
    path = Path("D:/AgenticEngineeringNetwork/training/datasets")
    before = _directory_metadata(path)

    execute_agent_runtime("product", "No dataset mutation", run_dir=tmp_path, backend_name="qwen_local")

    assert _directory_metadata(path) == before


def test_no_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Embedded runtime must not use internet.")

    monkeypatch.setattr(socket, "socket", fail_socket)

    assert execute_agent_runtime("product", "No internet", run_dir=tmp_path).status == "SUCCESS"


def test_no_terminal_or_dependency_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Embedded runtime must not execute terminal commands or installers.")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert execute_agent_runtime("product", "No terminal", run_dir=tmp_path).status == "SUCCESS"


def test_qwen_local_runtime_blocked_by_policy_generates_78_79(tmp_path: Path) -> None:
    result = execute_agent_runtime("product", "Blocked qwen local", run_dir=tmp_path, backend_name="qwen_local")

    assert result.status == "BLOCKED"
    assert result.backend_name == "qwen_local"
    assert result.load_status == "BLOCKED"
    assert (tmp_path / "78_model_inventory_snapshot.json").is_file()
    assert (tmp_path / "79_model_policy_decision.json").is_file()


def test_desktop_model_inventory_view_loads() -> None:
    from agentic_network.desktop_app.views.model_inventory_view import (
        MODEL_INVENTORY_MESSAGE,
        model_inventory_snapshot,
    )

    assert "does not load models" in MODEL_INVENTORY_MESSAGE
    snapshot = model_inventory_snapshot()
    assert "Model Inventory" in snapshot
    assert "deepseek_r1_distill_qwen_14b" in snapshot
    assert "allow_real_model_load=False" in snapshot


def _inventory_config(tmp_path: Path, *, path: str) -> Path:
    config = tmp_path / "inventory.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "models": [
                    {
                        "name": "test_model",
                        "family": "qwen",
                        "mode": "FAST",
                        "backend": "llama_cpp",
                        "path": path,
                        "adapter_path": None,
                        "quantization": "Q4_K_M",
                        "estimated_vram_mb": 100,
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


def _policy_config(
    tmp_path: Path,
    *,
    allow_model_download: bool = False,
    allow_training: bool = False,
) -> Path:
    config = tmp_path / "policy.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "allow_real_model_load": False,
                "allow_model_download": allow_model_download,
                "allow_training": allow_training,
                "allow_adapter_write": False,
                "allow_dataset_write": False,
                "max_loaded_models": 1,
                "vram_policy": "SEQUENTIAL",
                "default_backend": "mock",
                "allowed_backends": ["mock", "embedded", "llama_cpp", "qwen_local"],
            }
        ),
        encoding="utf-8",
    )
    return config


def _directory_metadata(path: Path) -> tuple[bool, int, tuple[str, ...]]:
    if not path.exists():
        return (False, 0, ())
    return (True, path.stat().st_mtime_ns, tuple(sorted(item.name for item in path.iterdir())))
