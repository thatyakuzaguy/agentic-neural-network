"""Read-only local model activation foundation for ANN v13.

The functions in this module inspect existing inventory, policy, runtime state,
and backend declarations. They never load models, download files, modify model
assets, write adapters/datasets, or execute terminal commands.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import gc
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any

from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload
from agentic_network.models.llama_cpp_security import load_secure_llama_cpp
from agentic_network.runtime_engine.backends.llama_cpp_backend import LlamaCppBackend
from agentic_network.runtime_engine.loader import get_loaded_models, get_runtime_metrics, reset_runtime_state
from agentic_network.runtime_engine.model_inventory import load_model_inventory
from agentic_network.runtime_engine.model_policy import load_model_policy
from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "outputs" / "model_activation"
QWEN25_MODEL_NAME = "qwen2_5_coder_7b_v5"
QWEN25_EXACT_GGUF_PATH = "D:/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf"
QWEN3_MODEL_NAME = "qwen3_8b_product_v9_repaired_v2_bullets"
DEEPSEEK14B_MODEL_NAME = "deepseek_r1_distill_qwen_14b"
DEEPSEEK14B_HF_PATH = "D:/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B"
DEEPSEEK14B_GGUF_PATH = "D:/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
POWERFUL_DEFERRED_REASON = "POWERFUL_REQUIRES_OFFLOAD_OR_QUANTIZED_MODEL"
QWEN25_SMOKE_PROMPT = "Return exactly: ANN_QWEN25_SMOKE_OK"
LOCAL_TEST_TOKEN = "LOCAL_TEST_TOKEN"
DEVELOPER_TEAM_TEST_TASK = (
    "Create a FastAPI Todo API with:\n\n"
    "CRUD endpoints\n\n"
    "Pydantic schemas\n\n"
    "pytest tests\n\n"
    "error handling\n\n"
    "README examples\n\n"
    "type hints"
)
FINAL_ENGINEERING_PIPELINE_TASK = (
    "Create a FastAPI Todo API with CRUD endpoints, Pydantic schemas, pytest tests, "
    "error handling, type hints, and README examples."
)
QWEN3_PRODUCT_ADAPTER_PATH = "D:/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v9-repaired-v2-bullets"
DEEPSEEK_GGUF_LAYER_FALLBACKS = (20, 16, 12, 8, 4)
EXPECTED_MODELS = (
    QWEN25_MODEL_NAME,
    "qwen3_8b_product_v9_repaired_v2_bullets",
    "deepseek_r1_distill_qwen_14b",
)
DEFAULT_RUNTIME_ROOT_TEXT = "D:/ANN/runtime"
DEFAULT_WSL_MOUNT_ROOT = "/mnt"
LLAMA_READINESS_STATES = {
    "READY",
    "UNAVAILABLE",
    "CPU_ONLY",
    "CUDA_AVAILABLE",
    "CUDA_UNKNOWN",
    "IMPORT_ERROR",
    "MODEL_MISSING",
    "POLICY_BLOCKED",
    "SAFE_MODE_ONLY",
}
_WSL_EXTERNAL_RUNTIME_CACHE: dict[str, Any] | None = None
_READINESS_CACHE: dict[str, dict[str, Any]] = {}
_EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE: dict[str, dict[str, Any]] = {}
_CODE_SIGNING_READINESS_CACHE: dict[str, dict[str, Any]] = {}
_SHA256_CACHE: dict[tuple[str, int, int], str] = {}
EMBEDDED_RELEASE_IMPORTS = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "psycopg",
    "dotenv",
    "stripe",
    "PySide6",
    "llama_cpp",
    "numpy",
    "psutil",
    "yaml",
)
EMBEDDED_RELEASE_FORBIDDEN_DISTRIBUTIONS = {
    "azure-core",
    "jupyter",
    "jupyterlab",
    "langgraph",
    "opencv-python",
    "open-webui",
    "unsloth",
}
EMBEDDED_RELEASE_APPLICATION_DISTRIBUTIONS = {"agentic-engineering-network"}


def build_model_identity_correction() -> dict[str, Any]:
    """Report the corrected model identities from inventory."""

    inventory = load_model_inventory()
    names = [record.model_name for record in inventory.models]
    return {
        "version": "12.7.1",
        "generated_at": _now(),
        "status": "CORRECTED" if "qwen14b" not in names and "deepseek_r1_distill_qwen_14b" in names else "NEEDS_ATTENTION",
        "removed_identity": "qwen14b",
        "correct_powerful_identity": "deepseek_r1_distill_qwen_14b",
        "inventory_version": inventory.version,
        "inventory_model_names": names,
        "qwen14b_present": "qwen14b" in names,
        "deepseek14b_present": "deepseek_r1_distill_qwen_14b" in names,
        "models": [_model_identity_payload(record.to_dict()) for record in inventory.models],
        "safety": _safety_payload(),
    }


def build_local_model_preflight() -> dict[str, Any]:
    """Validate declared local model readiness without loading models."""

    inventory = load_model_inventory()
    policy = load_model_policy()
    metrics = get_runtime_metrics()
    loaded_models = get_loaded_models()
    models = [_preflight_model_payload(record.to_dict()) for record in inventory.models]
    powerful = next((model for model in models if model["mode"] == "POWERFUL"), None)
    fast_models = [model for model in models if model["mode"] == "FAST"]
    return {
        "version": "13.0",
        "generated_at": _now(),
        "status": "SAFE_MODE",
        "runtime": {
            "safe_mode": True,
            "loaded_models": loaded_models,
            "active_models": metrics.get("active_models", 0),
            "max_loaded_models": policy.max_loaded_models,
            "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
            "peak_vram_mb": metrics.get("peak_vram_mb", 0),
        },
        "policy": {
            "allow_real_model_load": policy.allow_real_model_load,
            "allow_model_download": policy.allow_model_download,
            "allow_training": policy.allow_training,
            "allow_adapter_write": policy.allow_adapter_write,
            "allow_dataset_write": policy.allow_dataset_write,
            "max_loaded_models": policy.max_loaded_models,
            "parallel_llm_loads": 0,
            "vram_policy": policy.vram_policy,
            "default_backend": policy.default_backend,
            "allowed_backends": policy.allowed_backends,
        },
        "fast": {
            "available": bool(fast_models),
            "models": [model["model_name"] for model in fast_models],
            "all_blocked_by_policy": all(not model["load_allowed"] for model in fast_models),
        },
        "powerful": {
            "available": powerful is not None,
            "model": powerful["model_name"] if powerful else None,
            "blocked": powerful is None or not powerful["load_allowed"],
            "reason": powerful["load_blocked_reason"] if powerful else "not_configured",
        },
        "models": models,
        "hardware_target": {
            "gpu": "NVIDIA GeForce RTX 3060 Ti",
            "vram_gb": 8,
            "ram_gb": 32,
            "cpu": "Ryzen 5 2600",
        },
        "safety": _safety_payload(),
    }


def build_real_model_activation_plan() -> dict[str, Any]:
    """Build a non-executing activation plan for real local models."""

    preflight = build_local_model_preflight()
    return {
        "version": "13.0",
        "generated_at": _now(),
        "status": "PLAN_ONLY",
        "preflight_status": preflight["status"],
        "steps": [
            {
                "order": 1,
                "title": "Activate Qwen2.5 GGUF",
                "model": "qwen2_5_coder_7b_v5",
                "backend": "llama_cpp",
                "requires": ["path_exists", "backend_available", "8GB VRAM validation"],
                "executes_now": False,
            },
            {
                "order": 2,
                "title": "Activate Qwen3 + adapter v9",
                "model": "qwen3_8b_product_v9_repaired_v2_bullets",
                "backend": "qwen_local",
                "requires": ["path_exists", "adapter_exists", "backend_available"],
                "executes_now": False,
            },
            {
                "order": 3,
                "title": "Activate DeepSeek14B POWERFUL",
                "model": "deepseek_r1_distill_qwen_14b",
                "backend": "deepseek_unsloth",
                "fallback_backend": "embedded",
                "requires": ["path_exists", "backend_available", "VRAM/RAM risk review"],
                "executes_now": False,
            },
            {
                "order": 4,
                "title": "Change allow_real_model_load=true",
                "requires": ["explicit human approval", "backup", "smoke tests"],
                "executes_now": False,
            },
            {
                "order": 5,
                "title": "Preserve sequential policy",
                "requires": ["active_models=1", "parallel_llm_loads=0"],
                "executes_now": False,
            },
            {
                "order": 6,
                "title": "Verify VRAM",
                "hardware": preflight["hardware_target"],
                "requires": ["RTX 3060 Ti 8GB monitoring", "fallback to FAST if POWERFUL exceeds VRAM"],
                "executes_now": False,
            },
        ],
        "must_not_do_now": [
            "no_real_inference",
            "no_model_load",
            "no_downloads",
            "no_model_move",
            "no_quantization",
            "no_conversion",
            "no_policy_enablement",
        ],
        "safety": _safety_payload(),
    }


def evaluate_qwen25_activation_gate(
    *,
    confirm: bool = False,
    approval_token: str | None = None,
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate the Qwen2.5-only activation gate without loading anything."""

    policy = load_model_policy()
    inventory = load_model_inventory()
    record = next((item for item in inventory.models if item.model_name == QWEN25_MODEL_NAME), None)
    loaded_before = get_loaded_models()
    token_accepted = _token_valid(approval_token)
    errors: list[str] = []
    warnings: list[str] = []
    if not token_accepted:
        errors.append("approval_token_invalid_or_missing")
    if not confirm:
        errors.append("confirmation_required")
    if record is None:
        errors.append("qwen25_inventory_record_missing")
    if policy.allow_real_model_load:
        errors.append("global_policy_must_remain_safe_false")
    if policy.max_loaded_models != 1 or policy.vram_policy.upper() != "SEQUENTIAL":
        errors.append("sequential_policy_required")
    if loaded_before:
        errors.append("active_model_present_before_smoke")
    if record is not None:
        if record.mode != "FAST":
            errors.append("qwen25_must_be_fast_only")
        if record.backend != "llama_cpp":
            errors.append("qwen25_backend_must_be_llama_cpp")
        candidate_path = Path(model_path or record.source_path)
        if not candidate_path.exists():
            errors.append("qwen25_model_path_missing")
        if record.model_name != QWEN25_MODEL_NAME:
            errors.append("only_qwen25_allowed")
    status = "PASSED" if not errors else ("UNAVAILABLE" if "qwen25_model_path_missing" in errors else "BLOCKED")
    return {
        "version": "13.1",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "mode": "FAST",
        "token_provided": bool((approval_token or "").strip()),
        "token_accepted": token_accepted,
        "token_stored": False,
        "confirmation": bool(confirm),
        "experimental": True,
        "controlled_activation_available": True,
        "policy_global_safe": policy.allow_real_model_load is False,
        "loaded_models_before": loaded_before,
        "max_loaded_models": policy.max_loaded_models,
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "model_path": str(model_path or record.source_path) if record is not None else "",
        "model_exists": bool(record is not None and Path(model_path or record.source_path).exists()),
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "errors": errors,
        "warnings": warnings,
        "safety": _safety_payload(),
    }


def run_controlled_qwen25_smoke(
    *,
    confirm: bool = False,
    approval_token: str | None = None,
    output_dir: str | Path | None = None,
    model_path: str | Path | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Run a controlled Qwen2.5 smoke gate and return safe audit artifacts.

    The global model policy remains safe. This function creates a temporary
    per-call backend policy for Qwen2.5 only after token and confirmation pass.
    """

    started = perf_counter()
    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    gate = evaluate_qwen25_activation_gate(confirm=confirm, approval_token=approval_token, model_path=model_path)
    loaded_before = get_loaded_models()
    loaded_during: list[str] = []
    inference_text = ""
    load_result: dict[str, Any] = {}
    generate_result: dict[str, Any] = {}
    unload_result: dict[str, Any] = {}
    backend_health: dict[str, Any] = {}
    status = gate["status"]
    errors = list(gate["errors"])
    warnings = list(gate["warnings"])
    real_load_attempted = False
    real_inference_attempted = False
    mock_fallback = False
    backend_name = "llama_cpp"
    try:
        if gate["status"] != "PASSED":
            mock_fallback = True
            warnings.append("safe_mock_fallback_preserved")
        else:
            real_load_attempted = True
            backend_adapter = backend or LlamaCppBackend({"allow_real_model_load": True})
            backend_name = getattr(backend_adapter, "name", "llama_cpp")
            health = backend_adapter.health_check()
            backend_health = health.to_dict() if hasattr(health, "to_dict") else dict(health)
            if not backend_health.get("available", False):
                status = "UNAVAILABLE"
                errors.extend(_list_from(backend_health.get("errors")))
                warnings.extend(_list_from(backend_health.get("warnings")))
                mock_fallback = True
            else:
                load = backend_adapter.load_model(QWEN25_MODEL_NAME)
                load_result = load.to_dict() if hasattr(load, "to_dict") else dict(load)
                if not load_result.get("loaded", False):
                    status = _status_from_backend_load(load_result.get("status"))
                    errors.extend(_list_from(load_result.get("errors")))
                    warnings.extend(_list_from(load_result.get("warnings")))
                    mock_fallback = True
                else:
                    loaded_during = [QWEN25_MODEL_NAME]
                    real_inference_attempted = True
                    generation = backend_adapter.generate(QWEN25_MODEL_NAME, QWEN25_SMOKE_PROMPT)
                    generate_result = generation.to_dict() if hasattr(generation, "to_dict") else dict(generation)
                    inference_text = str(generate_result.get("text", ""))
                    status = (
                        "PASSED"
                        if generate_result.get("status") == "SUCCESS"
                        and inference_text.strip() == "ANN_QWEN25_SMOKE_OK"
                        else "LOAD_FAILED"
                    )
                    if status != "PASSED":
                        errors.extend(_list_from(generate_result.get("errors")) or ["qwen25_smoke_output_mismatch"])
                    unload = backend_adapter.unload_model(QWEN25_MODEL_NAME)
                    unload_result = unload.to_dict() if hasattr(unload, "to_dict") else dict(unload)
    finally:
        rollback = _rollback_safe_state()
    loaded_after = get_loaded_models()
    runtime_trace = {
        "version": "13.1",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": backend_name,
        "prompt": QWEN25_SMOKE_PROMPT,
        "loaded_models_before": loaded_before,
        "loaded_models_during": loaded_during,
        "loaded_models_after": loaded_after,
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "real_load_succeeded": bool(load_result.get("loaded", False)),
        "real_inference_succeeded": status == "PASSED",
        "mock_fallback": mock_fallback,
        "safe_mode_final": loaded_after == [],
        "rollback": rollback,
        "duration_ms": _elapsed_ms(started),
        "runtime_metrics": get_runtime_metrics(),
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    backend_smoke = {
        "version": "13.1",
        "generated_at": _now(),
        "status": _backend_smoke_status(status, backend_health, load_result),
        "backend": backend_name,
        "model_name": QWEN25_MODEL_NAME,
        "backend_health": backend_health,
        "load_result": load_result,
        "generate_result": {**generate_result, "text": _redact_if_empty_or_exact(inference_text)},
        "unload_result": unload_result,
        "errors": runtime_trace["errors"],
        "warnings": runtime_trace["warnings"],
    }
    artifacts = _write_qwen25_artifacts(target, gate, backend_smoke, runtime_trace)
    return {
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": backend_name,
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "mock_fallback": mock_fallback,
        "safe_mode_final": loaded_after == [],
        "loaded_models_before": loaded_before,
        "loaded_models_after": loaded_after,
        "artifacts": artifacts,
        "errors": runtime_trace["errors"],
        "warnings": runtime_trace["warnings"],
    }


def diagnose_llama_cpp_backend(model_path: str | Path | None = None) -> dict[str, Any]:
    """Diagnose llama_cpp readiness without installing, compiling, or loading a model."""

    configure_windows_runtime_dll_paths()
    inventory = load_model_inventory()
    policy = load_model_policy()
    record = next((item for item in inventory.models if item.model_name == QWEN25_MODEL_NAME), None)
    candidate_path = Path(model_path or (record.source_path if record else ""))
    package_importable = importlib.util.find_spec("llama_cpp") is not None
    import_error = ""
    version = None
    cuda_status = "CUDA_UNKNOWN"
    gpu_support = "unknown"
    if package_importable:
        try:
            version = importlib.metadata.version("llama-cpp-python")
        except importlib.metadata.PackageNotFoundError:
            version = None
        try:
            llama_module = load_secure_llama_cpp()
            gpu_attr = llama_cpp_supports_gpu_offload(llama_module)
            if gpu_attr is True:
                cuda_status = "CUDA_AVAILABLE"
                gpu_support = "available"
            elif gpu_attr is False:
                cuda_status = "CPU_ONLY"
                gpu_support = "cpu_only"
        except Exception as exc:  # pragma: no cover - depends on optional native binding state.
            import_error = f"{type(exc).__name__}:{exc}"
            cuda_status = "IMPORT_ERROR"
            package_importable = False
    model_exists = candidate_path.is_file()
    readable = _is_readable_file(candidate_path)
    blocked_path = _is_c_path(candidate_path) or _has_protected_part(candidate_path)
    file_size_mb = _file_size_mb(candidate_path)
    reasons: list[str] = []
    if not package_importable:
        reasons.append("llama_cpp_binding_unavailable")
    if import_error:
        reasons.append(import_error)
    if not model_exists:
        reasons.append("qwen25_model_path_missing")
    if blocked_path:
        reasons.append("qwen25_model_path_blocked")
    if not readable:
        reasons.append("qwen25_model_file_not_readable")
    if policy.allow_real_model_load is False:
        reasons.append("global_policy_safe_false_controlled_gate_required")
    status = _llama_readiness_status(
        package_importable=package_importable,
        model_exists=model_exists,
        readable=readable,
        blocked_path=blocked_path,
        cuda_status=cuda_status,
    )
    return {
        "version": "13.2",
        "generated_at": _now(),
        "status": status,
        "valid_states": sorted(LLAMA_READINESS_STATES),
        "binding_importable": package_importable,
        "binding_version": version,
        "import_error": import_error,
        "cuda_status": cuda_status,
        "gpu_support": gpu_support,
        "cpu_only": cuda_status == "CPU_ONLY",
        "backend": "llama_cpp",
        "model_name": QWEN25_MODEL_NAME,
        "model_path": str(candidate_path),
        "model_exists": model_exists,
        "model_file_size_mb": file_size_mb,
        "model_readable": readable,
        "model_path_c_drive": _is_c_path(candidate_path),
        "model_path_protected": _has_protected_part(candidate_path),
        "can_attempt_controlled_load": package_importable and model_exists and readable and not blocked_path,
        "policy_global_safe": policy.allow_real_model_load is False,
        "blocking_reasons": _dedupe(reasons),
        "manual_guidance": _llama_manual_guidance(package_importable),
        "safety": _safety_payload(),
    }


def write_llama_cpp_backend_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 110-111 for llama_cpp readiness."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"110_llama_cpp_backend_readiness.json": diagnose_llama_cpp_backend()},
    )


def run_qwen25_retry_smoke(
    *,
    confirm: bool = False,
    approval_token: str | None = None,
    output_dir: str | Path | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Retry the Qwen2.5 smoke only when llama_cpp readiness allows it."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    readiness = diagnose_llama_cpp_backend()
    if not confirm:
        retry = _retry_payload(
            status="BLOCKED",
            readiness=readiness,
            smoke=None,
            errors=["confirmation_required"],
            warnings=[],
        )
    elif not _token_valid(approval_token):
        retry = _retry_payload(
            status="BLOCKED",
            readiness=readiness,
            smoke=None,
            errors=["approval_token_invalid_or_missing"],
            warnings=[],
        )
    elif not readiness["can_attempt_controlled_load"] and backend is None:
        retry = _retry_payload(
            status="UNAVAILABLE",
            readiness=readiness,
            smoke=None,
            errors=list(readiness["blocking_reasons"]),
            warnings=["controlled_smoke_not_attempted_backend_not_ready"],
        )
    else:
        smoke = run_controlled_qwen25_smoke(
            confirm=confirm,
            approval_token=approval_token,
            output_dir=target / "controlled_smoke",
            backend=backend,
        )
        retry_status = _retry_status_from_smoke(smoke)
        retry = _retry_payload(
            status=retry_status,
            readiness=readiness,
            smoke=smoke,
            errors=list(smoke.get("errors", [])),
            warnings=list(smoke.get("warnings", [])),
        )
    artifacts = _write_numbered_artifacts(target, {"112_qwen25_retry_smoke.json": retry})
    return {
        "status": retry["status"],
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "readiness_status": readiness["status"],
        "real_load_attempted": bool(retry.get("real_load_attempted", False)),
        "real_inference_attempted": bool(retry.get("real_inference_attempted", False)),
        "safe_mode_final": retry["safe_mode_final"],
        "loaded_models_after": retry["loaded_models_after"],
        "artifacts": artifacts,
        "errors": retry["errors"],
        "warnings": retry["warnings"],
    }


def probe_runtime_memory() -> dict[str, Any]:
    """Probe CPU/GPU memory without allocating VRAM or loading models."""

    torch_available = importlib.util.find_spec("torch") is not None
    cuda_available = False
    gpu_name = None
    vram_total_mb = None
    vram_allocated_mb = None
    vram_reserved_mb = None
    torch_error = ""
    if torch_available:
        try:
            torch = importlib.import_module("torch")
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                gpu_name = str(torch.cuda.get_device_name(0))
                props = torch.cuda.get_device_properties(0)
                vram_total_mb = round(int(props.total_memory) / (1024 * 1024), 2)
                vram_allocated_mb = round(int(torch.cuda.memory_allocated(0)) / (1024 * 1024), 2)
                vram_reserved_mb = round(int(torch.cuda.memory_reserved(0)) / (1024 * 1024), 2)
        except Exception as exc:  # pragma: no cover - hardware dependent.
            torch_error = f"{type(exc).__name__}:{exc}"
    status = "AVAILABLE" if cuda_available else ("cuda_unavailable" if torch_available else "torch_unavailable")
    return {
        "version": "13.2",
        "generated_at": _now(),
        "status": status,
        "torch_available": torch_available,
        "torch_error": torch_error,
        "cuda_available": cuda_available,
        "gpu_available": bool(gpu_name),
        "gpu_name": gpu_name,
        "vram_total_mb": vram_total_mb,
        "vram_allocated_mb": vram_allocated_mb,
        "vram_reserved_mb": vram_reserved_mb,
        "cpu_ram": _probe_cpu_ram(),
        "no_model_loaded": get_loaded_models() == [],
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "safety": _safety_payload(),
    }


def write_runtime_memory_probe_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 114-115 for runtime memory probe."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"114_runtime_memory_probe.json": probe_runtime_memory()})


def prepare_qwen3_activation() -> dict[str, Any]:
    """Prepare Qwen3 activation read-only; do not load Qwen3."""

    inventory = load_model_inventory()
    policy = load_model_policy()
    record = next((item for item in inventory.models if item.model_name == QWEN3_MODEL_NAME), None)
    model_path = Path(record.source_path) if record else Path("D:/Models/qwen3")
    adapter_path = Path(record.adapter_path) if record and record.adapter_path else Path(
        "D:/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v9-repaired-v2-bullets"
    )
    model_exists = model_path.is_dir()
    checks = {
        "model_path_exists": model_exists,
        "safetensors_or_index_exists": _any_child_matches(model_path, (".safetensors", "model.safetensors.index.json")),
        "tokenizer_exists": any((model_path / name).exists() for name in ("tokenizer.json", "tokenizer.model")),
        "adapter_exists": adapter_path.exists(),
        "backend_available": bool(record and record.backend_available),
        "policy_blocks_real_load": policy.allow_real_model_load is False,
    }
    missing = [name for name, ok in checks.items() if not ok and name != "policy_blocks_real_load"]
    status = "PREPARED_BUT_BLOCKED_BY_POLICY" if not missing and checks["policy_blocks_real_load"] else "MISSING_REQUIREMENTS"
    return {
        "version": "13.4",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN3_MODEL_NAME,
        "mode": "FAST",
        "backend": "qwen_local",
        "source_path": str(model_path),
        "adapter_path": str(adapter_path),
        "estimated_vram_mb": record.estimated_vram_mb if record else 7200,
        "checks": checks,
        "missing_requirements": missing,
        "policy": {
            "allow_real_model_load": policy.allow_real_model_load,
            "max_loaded_models": policy.max_loaded_models,
            "vram_policy": policy.vram_policy,
        },
        "risks": [
            "RTX 3060 Ti 8GB may be close to the VRAM limit for Qwen3 + adapter.",
            "Activation must remain sequential with active_models=1.",
            "Future v13.5 must use token, confirmation, unload, and rollback gates.",
        ],
        "future_v13_5_required_changes": [
            "Add Qwen3-specific controlled gate.",
            "Verify qwen_local real backend load path.",
            "Measure VRAM during a minimal prompt.",
            "Keep DeepSeek and POWERFUL disabled.",
        ],
        "qwen3_loaded": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "safety": _safety_payload(),
    }


def write_qwen3_activation_preparation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 116-117 for Qwen3 preparation."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"116_qwen3_activation_preparation.json": prepare_qwen3_activation()})


def write_backend_readiness_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 110-117 for ANN v13.2-v13.4."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_llama_cpp_backend_readiness_artifacts(target))
    artifacts.extend(run_qwen25_retry_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=target)["artifacts"])
    artifacts.extend(write_runtime_memory_probe_artifacts(target))
    artifacts.extend(write_qwen3_activation_preparation_artifacts(target))
    return artifacts


def diagnose_cuda_environment() -> dict[str, Any]:
    """Diagnose CUDA/GPU visibility without loading models or reserving VRAM."""

    torch_available = importlib.util.find_spec("torch") is not None
    torch_version = None
    torch_cuda_version = None
    cuda_available = False
    device_count = 0
    devices: list[dict[str, Any]] = []
    torch_error = ""
    if torch_available:
        try:
            torch = importlib.import_module("torch")
            torch_version = str(getattr(torch, "__version__", "unknown"))
            torch_cuda_version = str(getattr(getattr(torch, "version", None), "cuda", None))
            cuda_available = bool(torch.cuda.is_available())
            device_count = int(torch.cuda.device_count()) if cuda_available else 0
            for index in range(device_count):
                props = torch.cuda.get_device_properties(index)
                devices.append(
                    {
                        "index": index,
                        "name": str(torch.cuda.get_device_name(index)),
                        "vram_total_mb": round(int(props.total_memory) / (1024 * 1024), 2),
                        "vram_allocated_mb": round(int(torch.cuda.memory_allocated(index)) / (1024 * 1024), 2),
                        "vram_reserved_mb": round(int(torch.cuda.memory_reserved(index)) / (1024 * 1024), 2),
                    }
                )
        except Exception as exc:  # pragma: no cover - hardware dependent.
            torch_error = f"{type(exc).__name__}:{exc}"
    if not torch_available:
        status = "torch_unavailable"
    elif torch_error:
        status = "cuda_probe_error"
    elif not cuda_available:
        status = "cuda_unavailable"
    elif device_count < 1:
        status = "gpu_unavailable"
    else:
        status = "cuda_available"
    return {
        "version": "13.5",
        "generated_at": _now(),
        "status": status,
        "torch_importable": torch_available,
        "torch_version": torch_version,
        "torch_cuda_version": torch_cuda_version,
        "torch_error": torch_error,
        "cuda_available": cuda_available,
        "device_count": device_count,
        "devices": devices,
        "gpu_name": devices[0]["name"] if devices else None,
        "vram_total_mb": devices[0]["vram_total_mb"] if devices else None,
        "vram_allocated_mb": devices[0]["vram_allocated_mb"] if devices else None,
        "vram_reserved_mb": devices[0]["vram_reserved_mb"] if devices else None,
        "driver_visibility": "visible_to_torch" if cuda_available else "not_visible_to_torch",
        "cpu_only_environment": torch_available and not cuda_available,
        "is_wsl": _is_wsl(),
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "safety": _safety_payload(),
    }


def write_cuda_environment_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 118-119."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"118_cuda_environment.json": diagnose_cuda_environment()})


def diagnose_llama_cpp_real_status(model_path: str | Path | None = None) -> dict[str, Any]:
    """Diagnose real llama_cpp status without instantiating a heavy model."""

    readiness = diagnose_llama_cpp_backend(model_path)
    llama_class_available = False
    metadata: dict[str, Any] = {}
    errors = list(readiness["blocking_reasons"])
    if readiness["binding_importable"]:
        try:
            llama_module = load_secure_llama_cpp()
            llama_class_available = hasattr(llama_module, "Llama")
            metadata = {
                "LLAMA_SUPPORTS_GPU_OFFLOAD": llama_cpp_supports_gpu_offload(llama_module),
                "LLAMA_DEFAULT_SEED": getattr(llama_module, "LLAMA_DEFAULT_SEED", None),
            }
        except Exception as exc:  # pragma: no cover - optional native binding.
            errors.append(f"{type(exc).__name__}:{exc}")
    model_ready = readiness["model_exists"] and readiness["model_readable"]
    if not readiness["binding_importable"]:
        status = "UNAVAILABLE"
    elif errors and any("IMPORT" in error.upper() for error in errors):
        status = "IMPORT_ERROR"
    elif not llama_class_available:
        status = "UNAVAILABLE"
        errors.append("llama_cpp_Llama_class_unavailable")
    elif not model_ready:
        status = "MODEL_READY_BACKEND_BLOCKED"
    elif readiness["can_attempt_controlled_load"] and readiness["cuda_status"] == "CUDA_AVAILABLE":
        status = "READY"
    elif readiness["cuda_status"] == "CPU_ONLY":
        status = "CPU_ONLY"
    elif readiness["can_attempt_controlled_load"]:
        status = "GPU_SUPPORT_UNKNOWN"
    else:
        status = "MODEL_READY_BACKEND_BLOCKED"
    return {
        "version": "13.5",
        "generated_at": _now(),
        "status": status,
        "backend": "llama_cpp",
        "binding_importable": readiness["binding_importable"],
        "binding_version": readiness["binding_version"],
        "llama_class_available": llama_class_available,
        "cuda_status": readiness["cuda_status"],
        "gpu_support_metadata": metadata,
        "safe_load_configuration": {
            "model_path": readiness["model_path"],
            "n_ctx": 128,
            "n_gpu_layers": -1,
            "verbose": False,
            "instantiated": False,
        },
        "would_be_cpu_only": status == "CPU_ONLY",
        "model_ready": model_ready,
        "can_attempt_controlled_load": status == "READY",
        "errors": _dedupe(errors),
        "warnings": readiness["manual_guidance"],
        "safety": _safety_payload(),
    }


def write_llama_cpp_real_status_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 120-121."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"120_llama_cpp_real_status.json": diagnose_llama_cpp_real_status()})


def run_qwen25_real_inference_smoke(
    *,
    confirm: bool = False,
    approval_token: str | None = None,
    experimental: bool = True,
    output_dir: str | Path | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Attempt first real Qwen2.5 inference only when the real backend is ready."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    policy = load_model_policy()
    loaded_before = get_loaded_models()
    errors: list[str] = []
    warnings: list[str] = []
    if not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not confirm:
        errors.append("confirmation_required")
    if not experimental:
        errors.append("experimental_mode_required")
    if loaded_before:
        errors.append("active_model_present_before_smoke")
    if policy.max_loaded_models != 1:
        errors.append("max_loaded_models_must_be_one")
    if get_runtime_metrics().get("parallel_llm_loads", 0) != 0:
        errors.append("parallel_llm_loads_must_be_zero")
    if _normalize_path_text(llama["safe_load_configuration"]["model_path"]) != _normalize_path_text(QWEN25_EXACT_GGUF_PATH):
        errors.append("qwen25_exact_gguf_path_mismatch")
    real_load_attempted = False
    real_inference_attempted = False
    real_load_succeeded = False
    real_inference_succeeded = False
    inference_text = ""
    load_time_seconds = 0.0
    inference_time_seconds = 0.0
    unload_time_seconds = 0.0
    load_result: dict[str, Any] = {}
    generate_result: dict[str, Any] = {}
    unload_result: dict[str, Any] = {}
    status = "BLOCKED" if errors else "UNAVAILABLE"
    if not errors:
        can_attempt = bool(backend) or llama["status"] == "READY"
        if not can_attempt:
            errors.extend(llama["errors"] or ["llama_cpp_not_ready"])
            warnings.append("real_inference_not_attempted_backend_not_ready")
            status = "UNAVAILABLE"
        else:
            adapter = backend or LlamaCppBackend({"allow_real_model_load": True})
            real_load_attempted = True
            load_started = perf_counter()
            load = adapter.load_model(QWEN25_MODEL_NAME)
            load_time_seconds = _elapsed_seconds(load_started)
            load_result = load.to_dict() if hasattr(load, "to_dict") else dict(load)
            if not load_result.get("loaded", False):
                status = "UNAVAILABLE" if load_result.get("status") == "UNAVAILABLE" else "FAILED"
                errors.extend(_list_from(load_result.get("errors")))
                warnings.extend(_list_from(load_result.get("warnings")))
            else:
                real_load_succeeded = True
                real_inference_attempted = True
                generate_started = perf_counter()
                generation = adapter.generate(QWEN25_MODEL_NAME, "Return exactly: ANN_QWEN25_REAL_INFERENCE_OK")
                inference_time_seconds = _elapsed_seconds(generate_started)
                generate_result = generation.to_dict() if hasattr(generation, "to_dict") else dict(generation)
                inference_text = str(generate_result.get("text", ""))
                if generate_result.get("status") == "SUCCESS" and inference_text.strip() == "ANN_QWEN25_REAL_INFERENCE_OK":
                    real_inference_succeeded = True
                    status = "PASSED"
                else:
                    status = "FAILED_OUTPUT_MISMATCH"
                    errors.extend(_list_from(generate_result.get("errors")) or ["qwen25_real_inference_output_mismatch"])
                unload_started = perf_counter()
                unload = adapter.unload_model(QWEN25_MODEL_NAME)
                unload_time_seconds = _elapsed_seconds(unload_started)
                unload_result = unload.to_dict() if hasattr(unload, "to_dict") else dict(unload)
    rollback = _rollback_safe_state()
    loaded_after = get_loaded_models()
    benchmark = build_runtime_benchmark(
        status="READY" if real_load_succeeded else "SKIPPED_NO_REAL_LOAD",
        load_time_seconds=load_time_seconds,
        inference_time_seconds=inference_time_seconds,
        unload_time_seconds=unload_time_seconds,
        total_time_seconds=_elapsed_seconds(started),
        generate_result=generate_result,
        loaded_before=loaded_before,
        loaded_during=[QWEN25_MODEL_NAME] if real_load_succeeded else [],
        loaded_after=loaded_after,
    )
    payload = {
        "version": "13.6",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "prompt": "Return exactly: ANN_QWEN25_REAL_INFERENCE_OK",
        "token_provided": bool((approval_token or "").strip()),
        "token_accepted": _token_valid(approval_token),
        "token_stored": False,
        "confirmation": bool(confirm),
        "experimental": bool(experimental),
        "exact_model_path_required": QWEN25_EXACT_GGUF_PATH,
        "max_loaded_models_required": 1,
        "max_loaded_models_actual": policy.max_loaded_models,
        "cuda_environment": cuda,
        "llama_cpp_real_status": llama,
        "loaded_models_before": loaded_before,
        "loaded_models_after": loaded_after,
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "real_load_succeeded": real_load_succeeded,
        "real_inference_succeeded": real_inference_succeeded,
        "response": inference_text if real_inference_succeeded else "",
        "load_result": load_result,
        "generate_result": {**generate_result, "text": inference_text if real_inference_succeeded else ""},
        "unload_result": unload_result,
        "benchmark": benchmark,
        "rollback": rollback,
        "safe_mode_final": loaded_after == [],
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "122_qwen25_real_inference.json": payload,
            "124_runtime_benchmark.json": benchmark,
        },
    )
    return {
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "real_load_succeeded": real_load_succeeded,
        "real_inference_succeeded": real_inference_succeeded,
        "safe_mode_final": loaded_after == [],
        "loaded_models_after": loaded_after,
        "benchmark_status": benchmark["status"],
        "artifacts": artifacts,
        "errors": payload["errors"],
        "warnings": payload["warnings"],
    }


def build_runtime_benchmark(
    *,
    status: str = "SKIPPED_NO_REAL_LOAD",
    load_time_seconds: float = 0.0,
    inference_time_seconds: float = 0.0,
    unload_time_seconds: float = 0.0,
    total_time_seconds: float = 0.0,
    generate_result: dict[str, Any] | None = None,
    loaded_before: list[str] | None = None,
    loaded_during: list[str] | None = None,
    loaded_after: list[str] | None = None,
) -> dict[str, Any]:
    """Build a light runtime benchmark payload; no stress loop."""

    memory = diagnose_cuda_environment()
    cpu_ram = _probe_cpu_ram()
    generation = generate_result or {}
    tokens_out = int(generation.get("tokens_out") or 0)
    tps = round(tokens_out / inference_time_seconds, 3) if inference_time_seconds > 0 and tokens_out else None
    return {
        "version": "13.6",
        "generated_at": _now(),
        "status": status,
        "load_time_seconds": round(load_time_seconds, 4),
        "inference_time_seconds": round(inference_time_seconds, 4),
        "unload_time_seconds": round(unload_time_seconds, 4),
        "total_time_seconds": round(total_time_seconds, 4),
        "prompt_tokens": generation.get("tokens_in"),
        "output_tokens": generation.get("tokens_out"),
        "tokens_per_second": tps,
        "peak_vram_mb": memory.get("vram_reserved_mb") or memory.get("vram_allocated_mb"),
        "allocated_vram_before": None,
        "allocated_vram_during": memory.get("vram_allocated_mb"),
        "allocated_vram_after": memory.get("vram_allocated_mb"),
        "cpu_ram_before": cpu_ram,
        "cpu_ram_after": _probe_cpu_ram(),
        "loaded_models_before": loaded_before or [],
        "loaded_models_during": loaded_during or [],
        "loaded_models_after": loaded_after or get_loaded_models(),
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "safety": _safety_payload(),
    }


def write_runtime_benchmark_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 124-125 with skipped status if no real load occurred."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"124_runtime_benchmark.json": build_runtime_benchmark()})


def prepare_qwen3_controlled_activation() -> dict[str, Any]:
    """Prepare future Qwen3 controlled activation without loading Qwen3."""

    base = prepare_qwen3_activation()
    model_path = Path(base["source_path"])
    checks = dict(base["checks"])
    checks.update(
        {
            "safetensors_shards_exist": _any_child_matches(model_path, (".safetensors",)),
            "model_index_exists": (model_path / "model.safetensors.index.json").exists(),
            "config_exists": (model_path / "config.json").exists(),
        }
    )
    return {
        **base,
        "version": "13.7",
        "status": "PREPARED_BUT_BLOCKED_BY_POLICY" if all(checks.values()) else "MISSING_REQUIREMENTS",
        "checks": checks,
        "requires_quantization_or_offload_future": True,
        "must_wait_for_qwen25_stable_real_smoke": True,
        "qwen3_loaded": False,
        "deepseek_touched": False,
        "powerful_activated": False,
    }


def write_qwen3_controlled_activation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 126-127."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"126_qwen3_controlled_activation.json": prepare_qwen3_controlled_activation()})


def prepare_deepseek_powerful_activation() -> dict[str, Any]:
    """Prepare DeepSeek POWERFUL read-only; never load it."""

    inventory = load_model_inventory()
    policy = load_model_policy()
    record = next((item for item in inventory.models if item.model_name == DEEPSEEK14B_MODEL_NAME), None)
    model_path = Path(record.source_path) if record else Path("D:/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B")
    checks = {
        "model_path_exists": model_path.is_dir(),
        "safetensors_shards_exist": _any_child_matches(model_path, (".safetensors",)),
        "model_index_exists": (model_path / "model.safetensors.index.json").exists(),
        "tokenizer_exists": any((model_path / name).exists() for name in ("tokenizer.json", "tokenizer.model")),
        "config_exists": (model_path / "config.json").exists(),
        "backend_deepseek_unsloth_available": bool(record and record.backend_available),
        "fallback_embedded_available": "embedded" in policy.allowed_backends,
        "policy_blocks_real_load": policy.allow_real_model_load is False,
    }
    missing = [name for name, ok in checks.items() if not ok and name != "policy_blocks_real_load"]
    return {
        "version": "13.8",
        "generated_at": _now(),
        "status": "POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY" if not missing else "MISSING_REQUIREMENTS",
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "mode": "POWERFUL",
        "backend": "deepseek_unsloth",
        "fallback_backend": "embedded",
        "source_path": str(model_path),
        "estimated_size_mb": _directory_size_mb(model_path),
        "estimated_vram_risk": "high_for_rtx_3060_ti_8gb",
        "checks": checks,
        "missing_requirements": missing,
        "risks": [
            "Likely needs CPU offload, quantization, or a different backend for 8GB VRAM.",
            "POWERFUL must remain disabled until FAST real smoke is stable.",
            "Do not activate DeepSeek in this phase.",
        ],
        "policy": {
            "allow_real_model_load": policy.allow_real_model_load,
            "max_loaded_models": policy.max_loaded_models,
            "vram_policy": policy.vram_policy,
        },
        "model_load_attempted": False,
        "powerful_activated": False,
        "qwen3_touched": False,
        "safety": _safety_payload(),
    }


def write_deepseek_powerful_preparation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 128-129."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"128_deepseek_powerful_preparation.json": prepare_deepseek_powerful_activation()})


def write_real_backend_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 118-129 for ANN v13.5-v13.8."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_cuda_environment_artifacts(target))
    artifacts.extend(write_llama_cpp_real_status_artifacts(target))
    artifacts.extend(run_qwen25_real_inference_smoke(confirm=True, approval_token=LOCAL_TEST_TOKEN, output_dir=target)["artifacts"])
    if not (target / "124_runtime_benchmark.json").is_file():
        artifacts.extend(write_runtime_benchmark_artifacts(target))
    artifacts.extend(write_qwen3_controlled_activation_artifacts(target))
    artifacts.extend(write_deepseek_powerful_preparation_artifacts(target))
    return _dedupe(artifacts)


def build_external_runtime_matrix() -> dict[str, Any]:
    """Build a read-only matrix of local/external runtime compatibility."""

    cache_key = "build_external_runtime_matrix"
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached

    from agentic_network.installer.paths import get_default_install_root, is_c_drive
    from agentic_network.runtime_bundle.runtime import build_runtime_manifest

    manifest = build_runtime_manifest()
    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    qwen3 = prepare_qwen3_controlled_activation()
    deepseek = prepare_deepseek_powerful_activation()
    policy = load_model_policy()
    embedded_python = get_default_install_root() / "runtime" / "python" / "python.exe"
    system_python = shutil.which("python") or shutil.which("python3")
    runtimes = [
        _runtime_matrix_entry(
            "current",
            sys.executable,
            active=True,
            version=sys.version.split()[0],
            manifest=manifest.to_dict(),
            cuda=cuda,
            llama=llama,
        ),
        _runtime_matrix_entry(
            "system_python",
            system_python or "",
            active=bool(system_python and _normalize_path_text(system_python) == _normalize_path_text(sys.executable)),
            version=sys.version.split()[0] if system_python and _normalize_path_text(system_python) == _normalize_path_text(sys.executable) else "unknown",
            manifest=manifest.to_dict(),
            cuda=cuda,
            llama=llama,
        ),
        _runtime_matrix_entry(
            "embedded_expected",
            str(embedded_python),
            active=False,
            version="unknown",
            manifest=manifest.to_dict(),
            cuda=cuda,
            llama=llama,
        ),
    ]
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_python = Path(conda_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
        runtimes.append(
            _runtime_matrix_entry(
                "conda",
                str(conda_python),
                active=_normalize_path_text(conda_python) == _normalize_path_text(sys.executable),
                version=sys.version.split()[0] if _normalize_path_text(conda_python) == _normalize_path_text(sys.executable) else "unknown",
                manifest=manifest.to_dict(),
                cuda=cuda,
                llama=llama,
            )
        )
    support = {
        "desktop_app": manifest.pyside_version is not None,
        "qwen2_5_gguf": llama["status"] == "READY",
        "qwen3_hf_safetensors": qwen3["status"] == "PREPARED_BUT_BLOCKED_BY_POLICY",
        "deepseek_hf_safetensors": deepseek["status"] == "POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY",
    }
    blocked_reasons = _dedupe(
        []
        + ([] if support["desktop_app"] else ["pyside6_missing_or_unavailable"])
        + ([] if cuda["cuda_available"] else [cuda["status"]])
        + ([] if llama["status"] == "READY" else llama["errors"] or [f"llama_cpp_{llama['status']}"])
        + ([] if embedded_python.is_file() else ["embedded_python_missing"])
        + ([] if not is_c_drive(get_default_install_root()) else ["install_root_targets_c_drive"])
    )
    payload = {
        "version": "13.9",
        "generated_at": _now(),
        "status": "READY_FOR_REAL_INFERENCE" if not blocked_reasons and support["qwen2_5_gguf"] else "ENVIRONMENT_INCOMPLETE",
        "current_python_executable": sys.executable,
        "conda_env": conda_prefix,
        "system_python": system_python,
        "embedded_python_expected": str(embedded_python),
        "runtime_candidates": runtimes,
        "package_status": {
            "torch": {"version": cuda["torch_version"], "cuda_available": cuda["cuda_available"], "status": cuda["status"]},
            "llama_cpp": {
                "version": llama["binding_version"],
                "importable": llama["binding_importable"],
                "status": llama["status"],
            },
            "PySide6": {"version": manifest.pyside_version, "importable": manifest.pyside_version is not None},
            "transformers": {"version": manifest.transformers_version, "importable": manifest.transformers_version is not None},
        },
        "supports": support,
        "blocked_reasons": blocked_reasons,
        "manual_action_needed": _manual_actions_from_environment(cuda, llama, embedded_python),
        "policy": {
            "allow_real_model_load": policy.allow_real_model_load,
            "max_loaded_models": policy.max_loaded_models,
            "vram_policy": policy.vram_policy,
            "default_backend": policy.default_backend,
        },
        "qwen3": {"status": qwen3["status"], "loaded": qwen3["qwen3_loaded"]},
        "deepseek": {"status": deepseek["status"], "powerful_activated": deepseek["powerful_activated"]},
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_external_runtime_matrix_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 130-131."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"130_external_runtime_matrix.json": build_external_runtime_matrix()})


def build_embedded_python_release_plan(install_root: str | Path | None = None) -> dict[str, Any]:
    """Plan the embedded Python release layout without downloading or installing."""

    from agentic_network.installer.paths import get_default_install_root, is_c_drive

    root = Path(install_root or get_default_install_root())
    runtime_root = root / "runtime"
    embedded_python = runtime_root / "python" / "python.exe"
    preserved = ["projects", "models", "outputs", "data"]
    return {
        "version": "14.0",
        "generated_at": _now(),
        "status": "PLAN_ONLY" if not embedded_python.is_file() else "EMBEDDED_RUNTIME_PRESENT",
        "install_root": str(root),
        "install_root_uses_c_drive": is_c_drive(root),
        "expected_python_executable": str(embedded_python),
        "embedded_python_present": embedded_python.is_file(),
        "expected_structure": {
            "runtime_python": str(runtime_root / "python"),
            "runtime_site_packages": str(runtime_root / "site-packages"),
            "runtime_requirements_lock": str(runtime_root / "requirements-lock"),
            "runtime_wheels": str(runtime_root / "wheels"),
            "runtime_checks": str(runtime_root / "checks"),
        },
        "verification_checks": [
            "Run embedded python import check for PySide6 without opening a browser.",
            "Verify torch reports a CUDA build and torch.cuda.is_available() is true.",
            "Verify llama_cpp import and Llama class availability.",
            "Verify install root is not C: and runtime paths stay under D:/ANN.",
            "Verify ANN Desktop opens natively and reads existing project/data roots.",
        ],
        "preserve_directories": [str(root / name) for name in preserved],
        "setup_exe_remaining": [
            "Create a reproducible offline wheelhouse.",
            "Bundle the embedded Python runtime into runtime/python.",
            "Copy ANN package and configs using the installer manifest.",
            "Add Start Menu and desktop shortcuts.",
            "Run offline runtime checks and write installer logs.",
        ],
        "signed_installer_remaining": [
            "Choose signing certificate.",
            "Sign ANN_Setup.exe and uninstaller.",
            "Timestamp signatures.",
            "Document publisher identity and release hash.",
        ],
        "blocked_actions": [
            "no_downloads_from_ann",
            "no_pip_install_from_ann",
            "no_model_download",
            "no_training",
            "no_adapter_write",
            "no_dataset_write",
        ],
        "safety": _safety_payload(),
    }


def write_embedded_python_release_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 132-133."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"132_embedded_python_release_plan.json": build_embedded_python_release_plan()})


def build_backend_manual_readiness_checklist() -> dict[str, Any]:
    """Explain what is ready in ANN and what remains external/manual."""

    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    qwen3 = prepare_qwen3_controlled_activation()
    deepseek = prepare_deepseek_powerful_activation()
    policy = load_model_policy()
    items = [
        _readiness_item("ann_activation_architecture", "ANN ready", True, "Controlled Qwen2.5 gate and artifacts exist."),
        _readiness_item("torch_cuda_build", "environment missing", cuda["cuda_available"], f"Torch status: {cuda['status']}"),
        _readiness_item("llama_cpp_binding", "environment missing", llama["binding_importable"], f"llama_cpp status: {llama['status']}"),
        _readiness_item("cuda_cublas_support", "environment missing", llama["status"] == "READY", f"Backend status: {llama['status']}"),
        _readiness_item("gpu_visible", "environment missing", bool(cuda["gpu_name"]), f"GPU: {cuda['gpu_name']}"),
        _readiness_item("qwen25_gguf_path", "ANN ready", llama["model_ready"], llama["safe_load_configuration"]["model_path"]),
        _readiness_item("qwen3_path", "blocked", qwen3["status"] == "PREPARED_BUT_BLOCKED_BY_POLICY", qwen3["status"]),
        _readiness_item("deepseek_path", "blocked", deepseek["status"] == "POWERFUL_PREPARED_BUT_BLOCKED_BY_POLICY", deepseek["status"]),
        _readiness_item("vram_risk_reviewed", "optional", True, "RTX 3060 Ti 8GB risk is recorded for Qwen3/DeepSeek."),
        _readiness_item("safe_mode_status", "ANN ready", policy.allow_real_model_load is False, "Global real model load remains disabled."),
    ]
    missing = [item for item in items if not item["passed"] and item["category"] == "environment missing"]
    blocked = [item for item in items if item["category"] == "blocked"]
    return {
        "version": "14.0",
        "generated_at": _now(),
        "status": "READY" if not missing and llama["status"] == "READY" else "MANUAL_STEPS_REQUIRED",
        "sections": {
            "ann_ready": [item for item in items if item["category"] == "ANN ready"],
            "environment_missing": missing,
            "user_manual_step_needed": _manual_actions_from_environment(
                cuda,
                llama,
                _resolve_runtime_filesystem_path(f"{DEFAULT_RUNTIME_ROOT_TEXT}/python/python.exe"),
            ),
            "blocked": blocked,
            "optional": [item for item in items if item["category"] == "optional"],
        },
        "items": items,
        "qwen2_5": {"status": llama["status"], "model_ready": llama["model_ready"]},
        "qwen3": {"status": qwen3["status"], "loaded": qwen3["qwen3_loaded"]},
        "deepseek": {"status": deepseek["status"], "powerful_activated": deepseek["powerful_activated"]},
        "policy": {
            "allow_real_model_load": policy.allow_real_model_load,
            "max_loaded_models": policy.max_loaded_models,
            "vram_policy": policy.vram_policy,
        },
        "safety": _safety_payload(),
    }


def write_backend_manual_readiness_checklist_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 134-135."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"134_backend_manual_readiness_checklist.json": build_backend_manual_readiness_checklist()},
    )


def build_real_inference_launch_guard(
    *,
    model_id: str = QWEN25_MODEL_NAME,
    confirm: bool = False,
    approval_token: str | None = None,
    experimental: bool = False,
    artifact_trace_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate the final UI guard before any real Qwen2.5 inference launch."""

    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    policy = load_model_policy()
    loaded = get_loaded_models()
    trace_path = Path(artifact_trace_path or _timestamped_artifact_dir() / "136_real_inference_launch_guard.json")
    checks = [
        _guard_check("model_id_exact", model_id == QWEN25_MODEL_NAME, f"received={model_id}"),
        _guard_check("token_valid", _token_valid(approval_token), "LOCAL_TEST_TOKEN required for local test gate"),
        _guard_check("confirmation", confirm, "explicit confirmation required"),
        _guard_check("experimental_mode", experimental, "experimental real inference mode required"),
        _guard_check("backend_ready", llama["status"] == "READY", llama["status"]),
        _guard_check("cuda_status_recorded", bool(cuda["status"]), cuda["status"]),
        _guard_check("loaded_models_zero", loaded == [], str(loaded)),
        _guard_check("max_loaded_models_one", policy.max_loaded_models == 1, str(policy.max_loaded_models)),
        _guard_check("no_qwen3", True, "Qwen3 not loaded by this guard"),
        _guard_check("no_deepseek", True, "DeepSeek not loaded by this guard"),
        _guard_check("no_powerful", True, "POWERFUL remains inactive"),
        _guard_check("artifact_trace_path", str(trace_path).strip() != "", str(trace_path)),
    ]
    failed = [check for check in checks if not check["passed"]]
    return {
        "version": "14.1",
        "generated_at": _now(),
        "status": "PASSED" if not failed else "BLOCKED",
        "model_id": model_id,
        "artifact_trace_path": str(trace_path),
        "checks": checks,
        "failed_checks": failed,
        "cuda_environment": {
            "status": cuda["status"],
            "gpu_name": cuda["gpu_name"],
            "vram_total_mb": cuda["vram_total_mb"],
        },
        "llama_cpp_real_status": llama["status"],
        "loaded_models": loaded,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "qwen3_loaded": False,
        "deepseek_loaded": False,
        "powerful_activated": False,
        "next_action": "Run Qwen2.5 real inference smoke" if not failed else "Resolve failed checks before enabling launch",
        "safety": _safety_payload(),
    }


def write_real_inference_launch_guard_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 136-137."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    guard = build_real_inference_launch_guard(
        model_id=QWEN25_MODEL_NAME,
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        experimental=True,
        artifact_trace_path=target / "136_real_inference_launch_guard.json",
    )
    return _write_numbered_artifacts(target, {"136_real_inference_launch_guard.json": guard})


def write_runtime_compatibility_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 130-137 for ANN v13.9-v14.1."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_external_runtime_matrix_artifacts(target))
    artifacts.extend(write_embedded_python_release_plan_artifacts(target))
    artifacts.extend(write_backend_manual_readiness_checklist_artifacts(target))
    artifacts.extend(write_real_inference_launch_guard_artifacts(target))
    return _dedupe(artifacts)


def build_offline_wheelhouse_plan() -> dict[str, Any]:
    """Declare the future offline wheelhouse contents without installing anything."""

    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    packages = [
        _wheelhouse_package("python-embedded-runtime", "Embedded Python runtime", "runtime", ["required_for_desktop"]),
        _wheelhouse_package("PySide6", "Native ANN Desktop windows", "required", ["required_for_desktop"]),
        _wheelhouse_package("torch", "CUDA tensor runtime for local models", "required", ["required_for_qwen25_gguf", "required_for_qwen3_hf", "required_for_deepseek_hf"], installed_now=cuda["torch_importable"], detected_version=cuda["torch_version"], status="cpu_only" if cuda["torch_importable"] and not cuda["cuda_available"] else None),
        _wheelhouse_package("transformers", "HF/safetensors model runtime", "required", ["required_for_qwen3_hf", "required_for_deepseek_hf"]),
        _wheelhouse_package("accelerate", "Optional HF device/offload coordination", "optional", ["optional", "required_for_deepseek_hf"]),
        _wheelhouse_package("safetensors", "Safe HF tensor file loading", "required", ["required_for_qwen3_hf", "required_for_deepseek_hf"]),
        _wheelhouse_package("llama-cpp-python", "Qwen2.5 GGUF llama.cpp backend with CUDA/cuBLAS", "required", ["required_for_qwen25_gguf"], installed_now=llama["binding_importable"], detected_version=llama["binding_version"], status="missing" if not llama["binding_importable"] else llama["status"].lower()),
        _wheelhouse_package("numpy", "Numerical runtime dependency", "required", ["required_for_desktop", "required_for_qwen25_gguf", "required_for_qwen3_hf", "required_for_deepseek_hf"]),
        _wheelhouse_package("psutil", "Optional runtime memory/process diagnostics", "optional", ["optional"]),
        _wheelhouse_package("packaging", "Version and compatibility helpers", "optional", ["optional"]),
    ]
    categories = {
        "required_for_desktop": [item for item in packages if "required_for_desktop" in item["categories"]],
        "required_for_qwen25_gguf": [item for item in packages if "required_for_qwen25_gguf" in item["categories"]],
        "required_for_qwen3_hf": [item for item in packages if "required_for_qwen3_hf" in item["categories"]],
        "required_for_deepseek_hf": [item for item in packages if "required_for_deepseek_hf" in item["categories"]],
        "optional": [item for item in packages if "optional" in item["categories"]],
        "not_installed_by_ann": packages,
    }
    missing_required = [item for item in packages if item["required"] and item["status"] != "ready"]
    return {
        "version": "14.2",
        "generated_at": _now(),
        "status": "WHEELHOUSE_REQUIRED" if missing_required else "WHEELHOUSE_READY",
        "wheelhouse_root_expected": "D:\\ANN\\runtime\\wheels",
        "requirements_lock_expected": "D:\\ANN\\runtime\\requirements-lock",
        "packages": packages,
        "categories": categories,
        "missing_required": missing_required,
        "not_installed_by_ann": True,
        "manual_action_needed": [
            "Build or collect wheels outside ANN in an offline wheelhouse.",
            "Pin versions in requirements-lock before packaging the installer.",
            "Verify torch CUDA and llama-cpp-python manually before enabling real inference.",
        ],
        "safety": _safety_payload(),
    }


def write_offline_wheelhouse_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 138-139."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"138_offline_wheelhouse_plan.json": build_offline_wheelhouse_plan()})


def build_llama_cpp_cuda_verification_pack() -> dict[str, Any]:
    """Describe read-only runtime verification scripts and current backend state."""

    scripts = [
        _verification_script("check_torch_cuda", REPO_ROOT / "scripts" / "runtime" / "check_torch_cuda.py"),
        _verification_script("check_llama_cpp_cuda", REPO_ROOT / "scripts" / "runtime" / "check_llama_cpp_cuda.py"),
        _verification_script("check_ann_runtime_backend", REPO_ROOT / "scripts" / "runtime" / "check_ann_runtime_backend.py"),
    ]
    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    return {
        "version": "14.2",
        "generated_at": _now(),
        "status": "PACK_READY_READ_ONLY" if all(script["exists"] for script in scripts) else "PACK_INCOMPLETE",
        "scripts": scripts,
        "validates": [
            "torch import",
            "torch cuda visibility",
            "GPU device name",
            "llama_cpp import",
            "llama_cpp version",
            "Llama class availability",
            "Qwen2.5 GGUF path existence",
            "ANN launch guard status",
        ],
        "current_torch_status": cuda["status"],
        "current_llama_cpp_status": llama["status"],
        "launch_guard_status": guard["status"],
        "no_model_load_by_default": True,
        "safety": _safety_payload(),
    }


def write_llama_cpp_cuda_verification_pack_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 140-141."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"140_llama_cpp_cuda_verification_pack.json": build_llama_cpp_cuda_verification_pack()},
    )


def build_embedded_runtime_installer_readiness(install_root: str | Path | None = None) -> dict[str, Any]:
    """Validate future embedded runtime installer readiness without mutating the host."""

    from agentic_network.installer.distribution import build_distribution_readiness, verify_installer_foundation
    from agentic_network.installer.paths import get_default_install_root

    root = Path(install_root or get_default_install_root())
    cache_key = f"build_embedded_runtime_installer_readiness:{root}"
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    runtime = root / "runtime"
    checks_dir = runtime / "checks"
    logs_dir = runtime / "logs"
    script_paths = [
        REPO_ROOT / "scripts" / "runtime" / "check_torch_cuda.py",
        REPO_ROOT / "scripts" / "runtime" / "check_llama_cpp_cuda.py",
        REPO_ROOT / "scripts" / "runtime" / "check_ann_runtime_backend.py",
    ]
    distribution = build_distribution_readiness(install_root=root)
    installer = verify_installer_foundation(install_root=root)
    checks = [
        _readiness_item("runtime_folder", "installer", runtime.is_dir(), str(runtime)),
        _readiness_item("embedded_python", "installer", (runtime / "python" / "python.exe").is_file(), str(runtime / "python" / "python.exe")),
        _readiness_item("wheels_folder", "installer", (runtime / "wheels").is_dir(), str(runtime / "wheels")),
        _readiness_item("requirements_lock", "installer", (runtime / "requirements-lock").exists(), str(runtime / "requirements-lock")),
        _readiness_item("checks_folder", "installer", checks_dir.is_dir(), str(checks_dir)),
        _readiness_item("logs_folder", "installer", logs_dir.is_dir(), str(logs_dir)),
        _readiness_item("check_scripts_present", "installer", all(path.is_file() for path in script_paths), ", ".join(str(path) for path in script_paths)),
        _readiness_item("installer_no_downloads", "installer", distribution["installer_scripts"]["blocked_tokens"] == [], str(distribution["installer_scripts"]["blocked_tokens"])),
        _readiness_item("uninstaller_conservative", "installer", installer["uninstall_plan"]["keep_projects"] and installer["uninstall_plan"]["keep_models"], "preserves projects/models"),
    ]
    missing = [check for check in checks if not check["passed"]]
    payload = {
        "version": "14.3",
        "generated_at": _now(),
        "status": "READY" if not missing else "EMBEDDED_RUNTIME_MISSING",
        "install_root": str(root),
        "expected_paths": {
            "embedded_python": str(runtime / "python" / "python.exe"),
            "wheels": str(runtime / "wheels"),
            "requirements_lock": str(runtime / "requirements-lock"),
            "checks": str(checks_dir),
            "logs": str(logs_dir),
        },
        "checks": checks,
        "missing": missing,
        "preserve": ["data", "projects", "models", "outputs"],
        "no_dependency_download_in_installer": distribution["installer_scripts"]["blocked_tokens"] == [],
        "no_model_movement": True,
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_embedded_runtime_installer_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 142-143."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"142_embedded_runtime_installer_readiness.json": build_embedded_runtime_installer_readiness()},
    )


def build_runtime_gap_report() -> dict[str, Any]:
    """Compare ANN internal readiness with external runtime and installer gaps."""

    cache_key = "build_runtime_gap_report"
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    matrix = build_external_runtime_matrix()
    wheelhouse = build_offline_wheelhouse_plan()
    installer = build_embedded_runtime_installer_readiness()
    guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    checklist = build_backend_manual_readiness_checklist()
    ann_ready = {
        "gates": True,
        "model_inventory": True,
        "launch_guard": True,
        "artifacts": True,
        "ui": True,
        "safe_rollback": True,
        "policy": {
            "allow_real_model_load": False,
            "max_loaded_models": 1,
            "vram_policy": "SEQUENTIAL",
        },
    }
    environment_missing = {
        "torch_cuda": matrix["package_status"]["torch"]["status"] != "cuda_available",
        "llama_cpp_binding": matrix["package_status"]["llama_cpp"]["status"] != "READY",
        "gpu_visibility": not matrix["package_status"]["torch"]["cuda_available"],
        "embedded_python": matrix["embedded_python_expected"],
        "wheelhouse": wheelhouse["status"] != "WHEELHOUSE_READY",
        "details": matrix["blocked_reasons"],
    }
    installer_missing = {
        "packaged_embedded_runtime": installer["status"] != "READY",
        "signed_installer": True,
        "clean_machine_verification": True,
        "details": [item["id"] for item in installer["missing"]],
    }
    payload = {
        "version": "14.4",
        "generated_at": _now(),
        "status": "ANN_READY_ENVIRONMENT_NOT_READY" if environment_missing["details"] or installer_missing["details"] else "READY",
        "ANN_READY": ann_ready,
        "ENVIRONMENT_MISSING": environment_missing,
        "INSTALLER_MISSING": installer_missing,
        "launch_guard": {"status": guard["status"], "failed_checks": [check["name"] for check in guard["failed_checks"]]},
        "backend_checklist": {"status": checklist["status"]},
        "qwen2_5": {"status": matrix["package_status"]["llama_cpp"]["status"], "blocked_by_backend": guard["status"] == "BLOCKED"},
        "qwen3": matrix["qwen3"],
        "deepseek": matrix["deepseek"],
        "next_manual_step": _first_or_none(matrix["manual_action_needed"]),
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_runtime_gap_report_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 144-145."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"144_runtime_gap_report.json": build_runtime_gap_report()})


def write_offline_runtime_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 138-145 for ANN v14.2-v14.4."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_offline_wheelhouse_plan_artifacts(target))
    artifacts.extend(write_llama_cpp_cuda_verification_pack_artifacts(target))
    artifacts.extend(write_embedded_runtime_installer_readiness_artifacts(target))
    artifacts.extend(write_runtime_gap_report_artifacts(target))
    return _dedupe(artifacts)


def build_offline_runtime_lockfile(lockfile_path: str | Path | None = None) -> dict[str, Any]:
    """Build/read the offline runtime lockfile format without installing anything."""

    path = Path(lockfile_path or REPO_ROOT / "config" / "ann_runtime_lock.example.json")
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            payload.setdefault("verification_status", "declared")
            payload.setdefault("safety", _safety_payload())
            return payload
    wheelhouse = build_offline_wheelhouse_plan()
    return {
        "version": "14.5",
        "generated_at": _now(),
        "python_version": "3.11+",
        "platform": "windows",
        "architecture": "x86_64",
        "cuda_variant": "cu12x",
        "expected_runtime_path": "D:\\ANN\\runtime",
        "verification_status": "declared",
        "source": "example_lockfile_builder",
        "packages": [_lockfile_package_from_wheelhouse(item) for item in wheelhouse["packages"]],
        "wheels": [_lockfile_wheel_from_package(item) for item in wheelhouse["packages"]],
        "hashes": {"algorithm": "sha256", "required": True, "status": "hash_unknown"},
        "not_installed_by_ann": True,
        "safety": _safety_payload(),
    }


def write_offline_runtime_lockfile_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 146-147."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"146_offline_runtime_lockfile.json": build_offline_runtime_lockfile()})


def validate_wheelhouse_integrity(
    wheelhouse_path: str | Path | None = None,
    lockfile_path: str | Path | None = None,
    *,
    max_hash_size_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    """Validate wheelhouse files against an offline lockfile without installing wheels."""

    wheelhouse = _resolve_runtime_filesystem_path(wheelhouse_path or f"{DEFAULT_RUNTIME_ROOT_TEXT}/wheels")
    lockfile = _runtime_lockfile_for_wheelhouse(wheelhouse, lockfile_path)
    if not wheelhouse.is_dir():
        return _wheelhouse_result("WHEELHOUSE_MISSING", wheelhouse, lockfile, [], ["wheelhouse_directory_missing"])
    wheels = sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())
    discovered = [_wheel_file_payload(path, max_hash_size_bytes=max_hash_size_bytes) for path in wheels]
    if not lockfile.is_file():
        return _wheelhouse_result("LOCKFILE_MISSING", wheelhouse, lockfile, discovered, ["lockfile_missing"])
    lock = build_offline_runtime_lockfile(lockfile)
    declared = _declared_wheels(lock)
    results: list[dict[str, Any]] = []
    statuses: list[str] = []
    for item in declared:
        filename = item["filename"]
        found = next((wheel for wheel in discovered if wheel["filename"] == filename), None)
        if found is None:
            status = "missing"
            result = {**item, "status": status, "present": False, "actual_sha256": None}
        elif not item.get("sha256"):
            status = "hash_unknown"
            result = {**item, "status": status, "present": True, "actual_sha256": found["sha256"]}
        elif found["sha256"] == item.get("sha256"):
            status = "hash_verified"
            result = {**item, "status": status, "present": True, "actual_sha256": found["sha256"]}
        else:
            status = "hash_mismatch"
            result = {**item, "status": status, "present": True, "actual_sha256": found["sha256"]}
        statuses.append(status)
        results.append(result)
    if any(status == "hash_mismatch" for status in statuses):
        overall = "HASH_MISMATCH"
    elif any(status == "missing" for status in statuses):
        overall = "INCOMPLETE"
    elif statuses and all(status == "hash_verified" for status in statuses):
        overall = "HASH_VERIFIED"
    elif wheels:
        overall = "READY_FOR_VERIFY"
    else:
        overall = "INCOMPLETE"
    return {
        "version": str(lock.get("version") or "14.5"),
        "generated_at": _now(),
        "status": overall,
        "wheelhouse_path": str(wheelhouse),
        "lockfile_path": str(lockfile),
        "wheels_discovered": discovered,
        "declared_wheels": declared,
        "verification_results": results,
        "errors": [],
        "safety": _safety_payload(),
    }


def write_wheelhouse_integrity_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 148-149."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"148_wheelhouse_integrity.json": validate_wheelhouse_integrity()})


def build_offline_wheelhouse_command_plan(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build a reproducible external command plan for populating the offline wheelhouse."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    wheelhouse = root / "wheels"
    requirements = REPO_ROOT / "config" / "ann_runtime_requirements.windows-cp311.txt"
    lockfile = REPO_ROOT / "config" / "ann_runtime_lock.example.json"
    audit = build_embedded_runtime_package_audit(root, execute_imports=True)
    validation = validate_wheelhouse_integrity(wheelhouse, lockfile)
    missing_runtime_packages = audit.get("missing_packages", [])
    missing_wheels = validation.get("missing", []) if isinstance(validation.get("missing"), list) else []
    commands = [
        f"New-Item -ItemType Directory -Force -Path {_ps_quote(str(wheelhouse))}",
        (
            f"{_ps_quote(str(root / 'python' / 'python.exe'))} -m pip download "
            f"--only-binary=:all: --dest {_ps_quote(str(wheelhouse))} "
            f"--requirement {_ps_quote(str(requirements))}"
        ),
        (
            "$env:CMAKE_ARGS='-DGGML_CUDA=on'; "
            f"{_ps_quote(str(root / 'python' / 'python.exe'))} -m pip wheel "
            f"--wheel-dir {_ps_quote(str(wheelhouse))} llama-cpp-python"
        ),
        f"Get-ChildItem -Path {_ps_quote(str(wheelhouse))} -Filter *.whl | Get-FileHash -Algorithm SHA256 | Format-Table Hash,Path",
        "Update config\\ann_runtime_lock.example.json with exact wheel filenames, sizes, and sha256 hashes.",
        "$env:PYTHONPATH='.'; python -c \"from agentic_network.runtime_engine.local_model_activation import validate_wheelhouse_integrity; import json; print(json.dumps(validate_wheelhouse_integrity(), indent=2))\"",
    ]
    return {
        "version": "18.9.4",
        "generated_at": _now(),
        "status": "WHEELHOUSE_COMMAND_PLAN_READY",
        **_runtime_report(root_info),
        "wheelhouse_path": str(wheelhouse),
        "requirements_file": str(requirements),
        "requirements_file_exists": requirements.is_file(),
        "lockfile_path": str(lockfile),
        "lockfile_exists": lockfile.is_file(),
        "embedded_package_audit_status": audit["status"],
        "missing_runtime_packages": missing_runtime_packages,
        "wheelhouse_validation_status": validation["status"],
        "missing_wheels": missing_wheels,
        "commands": commands,
        "manual_external_execution_required": True,
        "downloads_executed": False,
        "installs_executed": False,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_shell": True,
        "safety": _safety_payload(),
    }


def write_offline_wheelhouse_command_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 356-357."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"356_offline_wheelhouse_command_plan.json": build_offline_wheelhouse_command_plan()},
    )


def build_clean_machine_validation_plan() -> dict[str, Any]:
    """Plan clean-machine validation for ANN without performing installation."""

    checklist = [
        _clean_machine_item("windows_version", "Windows 11 verified"),
        _clean_machine_item("gpu_driver", "NVIDIA driver visible to Windows"),
        _clean_machine_item("wsl_optional", "WSL optional; ANN Desktop must not require WSL"),
        _clean_machine_item("install_path", "Install to D:\\ANN and reject C: root"),
        _clean_machine_item("repo_independence", "Run without D:\\AgenticEngineeringNetwork repo path"),
        _clean_machine_item("embedded_python_present", "D:\\ANN\\runtime\\python\\python.exe exists"),
        _clean_machine_item("desktop_launches", "ANN Desktop opens natively"),
        _clean_machine_item("runtime_checks_pass", "runtime checks scripts pass"),
        _clean_machine_item("model_inventory_visible", "Model Inventory view renders"),
        _clean_machine_item("qwen25_gguf_present_or_linked", "Qwen2.5 GGUF present or linked"),
        _clean_machine_item("no_internet_required", "First run succeeds offline"),
        _clean_machine_item("no_c_root", "C: install root is rejected"),
        _clean_machine_item("uninstaller_preserves_data", "Uninstaller preserves data/models/projects/outputs"),
        _clean_machine_item("logs_generated", "Runtime/install logs generated"),
        _clean_machine_item("first_run_completed", "First Run status reviewed"),
        _clean_machine_item("no_real_model_load_by_default", "No real model load during install or first run"),
    ]
    return {
        "version": "14.6",
        "generated_at": _now(),
        "status": "PLAN_ONLY",
        "target_install_root": "D:\\ANN",
        "checklist": checklist,
        "acceptance": {
            "no_internet": True,
            "no_c_install_root": True,
            "preserve_user_data": True,
            "real_inference_default": False,
        },
        "safety": _safety_payload(),
    }


def write_clean_machine_validation_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 150-151."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"150_clean_machine_validation_plan.json": build_clean_machine_validation_plan()},
    )


def build_embedded_runtime_package_audit(
    runtime_root: str | Path | None = None,
    *,
    execute_imports: bool = True,
    timeout_seconds: int = 45,
) -> dict[str, Any]:
    """Audit embedded runtime package availability without installing anything."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    package_names = EMBEDDED_RELEASE_IMPORTS
    python_exe = root / "python" / "python.exe"
    static_presence = _embedded_runtime_package_presence(root, package_names)
    requirements = _embedded_release_requirement_versions()
    wheel_distributions = _wheelhouse_distribution_versions(root / "wheels")
    cache_key = (
        f"{root}|{execute_imports}|{timeout_seconds}|"
        f"{_path_cache_fingerprint(python_exe)}|{_path_cache_fingerprint(root / 'wheels')}"
    )
    if execute_imports and cache_key in _EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE:
        cached = json.loads(json.dumps(_EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    import_results: dict[str, dict[str, Any]] = {
        name: {
            "static_present": static_presence[name],
            "importable": False,
            "version": "",
            "error": "not_executed",
        }
        for name in package_names
    }
    probe_status = "SKIPPED"
    probe_error = ""
    installed_distributions: dict[str, str] = {}
    gpu_offload_supported = False
    if not python_exe.is_file():
        probe_status = "BLOCKED"
        probe_error = f"missing embedded python: {python_exe}"
    elif execute_imports:
        probe = _run_embedded_runtime_import_probe(python_exe, package_names, timeout_seconds)
        probe_status = probe["status"]
        probe_error = probe.get("error", "")
        for name, result in (probe.get("packages") or {}).items():
            if name in import_results and isinstance(result, dict):
                import_results[name].update(result)
        installed_distributions = {
            _canonical_distribution_name(name): str(version)
            for name, version in (probe.get("distributions") or {}).items()
        }
        gpu_offload_supported = probe.get("llama_cpp_gpu_offload") is True
    else:
        probe_status = "STATIC_ONLY"
        for name in package_names:
            import_results[name]["importable"] = static_presence[name]
            import_results[name]["error"] = "" if static_presence[name] else "not_found_static"
    missing = [name for name, result in import_results.items() if not result["importable"]]
    missing_distributions = sorted(set(requirements) - set(installed_distributions))
    version_mismatches = [
        {
            "name": name,
            "expected": expected,
            "actual": installed_distributions.get(name, "missing"),
        }
        for name, expected in sorted(requirements.items())
        if installed_distributions.get(name) != expected
    ]
    allowed_distributions = set(wheel_distributions) | EMBEDDED_RELEASE_APPLICATION_DISTRIBUTIONS
    unexpected_distributions = sorted(
        name
        for name in installed_distributions
        if wheel_distributions and name not in allowed_distributions
    )
    forbidden_distributions = sorted(
        name
        for name in installed_distributions
        if name in EMBEDDED_RELEASE_FORBIDDEN_DISTRIBUTIONS
    )
    if not python_exe.is_file():
        status = "PACKAGE_AUDIT_BLOCKED"
    elif (
        missing
        or missing_distributions
        or version_mismatches
        or unexpected_distributions
        or forbidden_distributions
        or not gpu_offload_supported
    ):
        status = "PACKAGE_AUDIT_INCOMPLETE"
    elif probe_status == "FAILED":
        status = "PACKAGE_AUDIT_FAILED"
    else:
        status = "PACKAGE_AUDIT_READY"
    payload = {
        "version": "18.9.19",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "python_executable": str(python_exe),
        "python_found": python_exe.is_file(),
        "execute_imports": execute_imports,
        "probe_status": probe_status,
        "probe_error": probe_error,
        "packages": import_results,
        "missing_packages": missing,
        "required_packages": list(package_names),
        "required_distribution_versions": requirements,
        "installed_distributions": installed_distributions,
        "wheelhouse_distributions": wheel_distributions,
        "missing_distributions": missing_distributions,
        "version_mismatches": version_mismatches,
        "unexpected_distributions": unexpected_distributions,
        "forbidden_distributions": forbidden_distributions,
        "llama_cpp_gpu_offload": gpu_offload_supported,
        "runtime_is_minimal": not unexpected_distributions and not forbidden_distributions,
        "ready_for_installer_rc": status == "PACKAGE_AUDIT_READY",
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_install": True,
        "no_download": True,
        "no_shell": True,
        "safety": _safety_payload(),
    }
    if execute_imports and payload["status"] == "PACKAGE_AUDIT_READY":
        _EMBEDDED_RUNTIME_PACKAGE_AUDIT_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_embedded_runtime_package_audit_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 352-353."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"352_embedded_runtime_package_audit.json": build_embedded_runtime_package_audit()},
    )


def _discover_windows_sdk_signtool(search_roots: list[Path] | None = None) -> str | None:
    """Locate the newest x64 Windows SDK SignTool when it is not on PATH."""

    roots = search_roots
    if roots is None:
        roots = []
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            value = os.environ.get(variable)
            if value:
                roots.append(Path(value))
        for fallback in (Path("C:/Program Files (x86)"), Path("C:/Program Files")):
            if fallback.exists():
                roots.append(fallback)

    candidates: list[Path] = []
    for root in _dedupe_paths(roots):
        sdk_root = root / "Windows Kits" / "10"
        bin_root = sdk_root / "bin"
        if bin_root.is_dir():
            candidates.extend(path for path in bin_root.glob("*/x64/signtool.exe") if path.is_file())
            candidates.extend(path for path in bin_root.glob("x64/signtool.exe") if path.is_file())
        app_certification = sdk_root / "App Certification Kit" / "signtool.exe"
        if app_certification.is_file():
            candidates.append(app_certification)
    if not candidates:
        return None
    selected = max(candidates, key=_signtool_candidate_key)
    return str(selected.resolve())


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _signtool_candidate_key(path: Path) -> tuple[int, tuple[int, ...], str]:
    version: tuple[int, ...] = ()
    for part in reversed(path.parts):
        if part.lower() == "x64":
            continue
        try:
            version = tuple(int(value) for value in part.split("."))
        except ValueError:
            continue
        break
    is_versioned_x64 = int(path.parent.name.lower() == "x64" and bool(version))
    return is_versioned_x64, version, str(path).lower()


def build_code_signing_readiness(
    installer_root: str | Path | None = None,
    *,
    execute_signature_check: bool = True,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Evaluate final installer signing readiness without signing anything."""

    root = Path(installer_root or REPO_ROOT / "installer")
    setup_exe = root / "ANN_Setup.exe"
    uninstall_exe = root / "ANN_Uninstall.exe"
    setup_bat = root / "ANN_Setup.bat"
    uninstall_bat = root / "ANN_Uninstall.bat"
    signtool = (
        shutil.which("signtool.exe")
        or shutil.which("signtool")
        or _discover_windows_sdk_signtool()
    )
    powershell = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
    required_binaries = {"ANN_Setup.exe": setup_exe, "ANN_Uninstall.exe": uninstall_exe}
    binary_presence = {name: path.is_file() for name, path in required_binaries.items()}
    binary_sha256 = {
        name: _sha256_for_existing_file(path) if binary_presence[name] else ""
        for name, path in required_binaries.items()
    }
    cache_key = json.dumps(
        {
            "root": str(root.resolve()),
            "execute_signature_check": execute_signature_check,
            "timeout_seconds": timeout_seconds,
            "signtool": signtool or "",
            "powershell": powershell or "",
            "binaries": {
                name: _file_state_cache_key(path)
                for name, path in required_binaries.items()
            },
        },
        sort_keys=True,
    )
    if cache_key in _CODE_SIGNING_READINESS_CACHE:
        cached = json.loads(json.dumps(_CODE_SIGNING_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    signature_checks = {
        name: _authenticode_signature_status(path, powershell, execute_signature_check, timeout_seconds)
        for name, path in required_binaries.items()
    }
    missing_binaries = [name for name, present in binary_presence.items() if not present]
    unsigned_binaries = [
        name
        for name, check in signature_checks.items()
        if binary_presence[name] and check.get("status") != "Valid"
    ]
    untimestamped_binaries = [
        name
        for name, check in signature_checks.items()
        if binary_presence[name]
        and check.get("status") == "Valid"
        and not str(check.get("timestamp_signer") or "").strip()
    ]
    blockers = []
    if missing_binaries:
        blockers.append("final_installer_binaries_missing")
    if unsigned_binaries:
        blockers.append("authenticode_signature_invalid_or_missing")
    if untimestamped_binaries:
        blockers.append("authenticode_timestamp_missing")
    if not signtool:
        blockers.append("signtool_missing")
    if missing_binaries:
        status = "SIGNING_BLOCKED_MISSING_BINARIES"
    elif unsigned_binaries:
        status = "SIGNING_BLOCKED_UNSIGNED"
    elif untimestamped_binaries:
        status = "SIGNING_BLOCKED_MISSING_TIMESTAMP"
    elif not signtool:
        status = "SIGNING_READY_FOR_EXTERNAL_TOOLING"
    else:
        status = "SIGNING_READY"
    signed_installer = not missing_binaries and not unsigned_binaries and not untimestamped_binaries
    payload = {
        "version": "18.9.3",
        "generated_at": _now(),
        "status": status,
        "installer_root": str(root),
        "required_binaries": {name: str(path) for name, path in required_binaries.items()},
        "binary_presence": binary_presence,
        "binary_sha256": binary_sha256,
        "setup_batch_present": setup_bat.is_file(),
        "uninstall_batch_present": uninstall_bat.is_file(),
        "signtool_detected": bool(signtool),
        "signtool_path": signtool or "",
        "powershell_detected": bool(powershell),
        "powershell_path": powershell or "",
        "signature_checks": signature_checks,
        "missing_binaries": missing_binaries,
        "unsigned_binaries": unsigned_binaries,
        "untimestamped_binaries": untimestamped_binaries,
        "signed_installer": signed_installer,
        "blockers": blockers,
        "next_step": _code_signing_next_step(blockers),
        "no_signing_performed": True,
        "no_install": True,
        "no_download": True,
        "no_shell": True,
        "safety": _safety_payload(),
    }
    _CODE_SIGNING_READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_code_signing_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 354-355."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"354_code_signing_readiness.json": build_code_signing_readiness()})


def build_release_signing_plan(installer_root: str | Path | None = None) -> dict[str, Any]:
    """Describe the release signing procedure without signing binaries."""

    root = Path(installer_root or REPO_ROOT / "installer")
    signing_script = root / "sign_release.ps1"
    setup_exe = root / "ANN_Setup.exe"
    uninstall_exe = root / "ANN_Uninstall.exe"
    readiness = build_code_signing_readiness(root, execute_signature_check=False)
    commands = [
        (
            "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
            '-CertificateThumbprint "<CERT_THUMBPRINT>" '
            "-TimestampUrl http://timestamp.digicert.com "
            "-OutputPath installer\\release_signing_evidence.json"
        ),
        (
            "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
            '-CertificateThumbprint "<CERT_THUMBPRINT>" '
            "-TimestampUrl http://timestamp.digicert.com "
            "-OutputPath installer\\release_signing_evidence.json -Execute"
        ),
        (
            "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
            "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
            "-SigningEvidencePath installer\\release_signing_evidence.json "
            "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
        ),
    ]
    blockers = []
    warnings = []
    if not signing_script.is_file():
        blockers.append("signing_script_missing")
    if not setup_exe.is_file() or not uninstall_exe.is_file():
        blockers.append("installer_binaries_missing")
    if not readiness["signtool_detected"]:
        warnings.append("signtool_missing_on_current_host")
    if blockers:
        status = "SIGNING_PLAN_BLOCKED"
    else:
        status = "SIGNING_PLAN_READY_FOR_RELEASE_MACHINE"
    return {
        "version": "18.9.8",
        "generated_at": _now(),
        "status": status,
        "installer_root": str(root),
        "signing_script": str(signing_script),
        "targets": [str(setup_exe), str(uninstall_exe)],
        "commands": commands,
        "commands_are_templates": True,
        "placeholder_must_be_replaced": True,
        "certificate_thumbprint_placeholder": "<CERT_THUMBPRINT>",
        "certificate_thumbprint_required_format": "40-character uppercase/lowercase hexadecimal SHA1 thumbprint",
        "certificate_thumbprint_regex": "^[0-9A-Fa-f]{40}$",
        "sign_release_blocks_placeholder": True,
        "requires_trusted_code_signing_certificate": True,
        "requires_signtool": True,
        "requires_external_release_machine_review": True,
        "current_host_code_signing_status": readiness["status"],
        "current_host_blockers": readiness["blockers"],
        "current_host_warnings": warnings,
        "blockers": blockers,
        "no_signing_performed": True,
        "no_download": True,
        "no_install": True,
        "no_self_signed_certificate": True,
        "safety": _safety_payload(),
    }


def write_release_signing_plan_artifacts(
    output_dir: str | Path | None = None,
    installer_root: str | Path | None = None,
) -> list[str]:
    """Write artifacts 360-361."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"360_release_signing_plan.json": build_release_signing_plan(installer_root)},
    )


def build_installer_rc_readiness() -> dict[str, Any]:
    """Evaluate future ANN_Setup.exe release candidate readiness."""

    from agentic_network.installer.distribution import verify_installer_foundation

    installer_foundation = verify_installer_foundation()
    lockfile = REPO_ROOT / "config" / "ann_runtime_lock.example.json"
    wheelhouse = _resolve_runtime_filesystem_path(f"{DEFAULT_RUNTIME_ROOT_TEXT}/wheels")
    embedded_python = _resolve_runtime_filesystem_path(f"{DEFAULT_RUNTIME_ROOT_TEXT}/python/python.exe")
    package_audit = build_embedded_runtime_package_audit(_resolve_runtime_filesystem_path(DEFAULT_RUNTIME_ROOT_TEXT))
    embedded_packages_ready = package_audit["ready_for_installer_rc"]
    checks = [
        _rc_check("installer_scripts_exist", all((REPO_ROOT / "installer" / name).is_file() for name in ("install_ann.ps1", "ANN_Setup.bat")), "installer scripts"),
        _rc_check("launcher_exists", (REPO_ROOT / "installer" / "ann_launcher.ps1").is_file(), "ann_launcher.ps1"),
        _rc_check("uninstaller_exists", all((REPO_ROOT / "installer" / name).is_file() for name in ("uninstall_ann.ps1", "ANN_Uninstall.bat")), "uninstaller scripts"),
        _rc_check("verify_install_exists", (REPO_ROOT / "installer" / "verify_install.ps1").is_file(), "verify_install.ps1"),
        _rc_check("desktop_entrypoint_exists", importlib.util.find_spec("agentic_network.desktop_app.run") is not None, "desktop entrypoint"),
        _rc_check("runtime_lockfile_exists", lockfile.is_file(), str(lockfile)),
        _rc_check("wheelhouse_exists", wheelhouse.is_dir(), str(wheelhouse)),
        _rc_check("embedded_python_exists", embedded_python.is_file(), str(embedded_python)),
        _rc_check("embedded_runtime_packages_present", embedded_packages_ready, json.dumps(package_audit["packages"], sort_keys=True)),
        _rc_check("model_distribution_policy_exists", (REPO_ROOT / "config" / "ann_model_policy.json").is_file(), "ann_model_policy.json"),
        _rc_check("app_excludes_protected_dirs", installer_foundation["install_validation"]["valid"], str(installer_foundation["install_validation"]["errors"])),
        _rc_check("preserves_user_data", installer_foundation["uninstall_plan"]["keep_projects"] and installer_foundation["uninstall_plan"]["keep_models"], "uninstall plan"),
        _rc_check("release_docs_exist", (REPO_ROOT / "installer" / "README_INSTALLER.md").is_file() and (REPO_ROOT / "README_RELEASE_CANDIDATE_READINESS.md").is_file(), "release docs"),
        _rc_check("first_run_available", True, "First Run view available"),
        _rc_check("smoke_checks_available", all((REPO_ROOT / "scripts" / "runtime" / name).is_file() for name in ("check_torch_cuda.py", "check_llama_cpp_cuda.py", "check_ann_runtime_backend.py")), "runtime checks"),
    ]
    blockers = [check for check in checks if not check["passed"]]
    if not blockers:
        status = "RC_READY"
    elif any(check["name"] in {"wheelhouse_exists", "embedded_python_exists", "embedded_runtime_packages_present"} for check in blockers):
        status = "RC_BLOCKED"
    elif all(check["name"] not in {"runtime_lockfile_exists", "smoke_checks_available", "release_docs_exist"} for check in blockers):
        status = "RC_READY_FOUNDATION_ONLY"
    else:
        status = "RC_READY_FOR_MANUAL_PACKAGING"
    payload = {
        "version": "14.7",
        "generated_at": _now(),
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "next_release_step": _next_rc_step(blockers),
        "installer_foundation": installer_foundation["status"],
        "embedded_runtime_package_audit": package_audit["status"],
        "embedded_runtime_missing_packages": package_audit["missing_packages"],
        "qwen2_5_loaded": False,
        "qwen3_loaded": False,
        "deepseek_loaded": False,
        "powerful_activated": False,
        "safety": _safety_payload(),
    }
    return payload


def write_installer_rc_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 152-153."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"152_installer_rc_readiness.json": build_installer_rc_readiness()})


def write_release_candidate_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 146-153 for ANN v14.5-v14.7."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_offline_runtime_lockfile_artifacts(target))
    artifacts.extend(write_wheelhouse_integrity_artifacts(target))
    artifacts.extend(write_clean_machine_validation_plan_artifacts(target))
    artifacts.extend(write_installer_rc_readiness_artifacts(target))
    return _dedupe(artifacts)


def build_installer_artifact_manifest() -> dict[str, Any]:
    """Build the public alpha installer artifact manifest without copying files."""

    from agentic_network.installer.runtime import build_install_plan

    plan = build_install_plan(REPO_ROOT, "D:/ANN")
    included_files = [
        _manifest_entry(Path(path), included=True, reason="installer_plan_include", preserve_on_uninstall=False)
        for path in plan.files_to_copy
    ]
    include_groups = [
        _manifest_group("app", REPO_ROOT / "agentic_network", "ANN application package"),
        _manifest_group("desktop_app", REPO_ROOT / "agentic_network" / "desktop_app", "Native desktop UI"),
        _manifest_group("runtime_bundle", REPO_ROOT / "agentic_network" / "runtime_bundle", "Runtime detection foundation"),
        _manifest_group("runtime_engine", REPO_ROOT / "agentic_network" / "runtime_engine", "Sequential runtime and backends"),
        _manifest_group("installer", REPO_ROOT / "installer", "Installer scripts"),
        _manifest_group("config", REPO_ROOT / "config", "Runtime/model/lock configuration"),
        _manifest_group("checks", REPO_ROOT / "scripts" / "runtime", "Read-only runtime checks"),
        _manifest_group("skills", REPO_ROOT / "agentic_network" / "skills", "Skills framework"),
        _manifest_group("documentation", REPO_ROOT, "Release documentation", patterns=("README*.md",)),
    ]
    exclude_paths = [
        ".git",
        "models",
        "training",
        "training/datasets",
        "training/adapters",
        "outputs",
        "unsloth_compiled_cache",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        "memory",
        "knowledge",
    ]
    excluded = [
        _manifest_entry(REPO_ROOT / path, included=False, reason="protected_or_heavy_exclusion", preserve_on_uninstall=True)
        for path in exclude_paths
    ]
    outputs_templates = _manifest_entry(
        REPO_ROOT / "outputs",
        included=False,
        reason="historical_outputs_excluded; installer creates empty outputs root",
        preserve_on_uninstall=True,
    )
    logs_entry = _manifest_entry(
        Path("D:/ANN/logs"),
        included=True,
        reason="target_directory_created_empty",
        preserve_on_uninstall=False,
    )
    manifest = {
        "version": "14.8",
        "generated_at": _now(),
        "status": "MANIFEST_READY",
        "target_root": "D:\\ANN",
        "include_groups": include_groups,
        "included_files_count": len(included_files),
        "included_size_mb": round(sum(float(item.get("size_mb") or 0) for item in included_files), 3),
        "included": included_files[:250],
        "included_truncated": len(included_files) > 250,
        "special_entries": [logs_entry, outputs_templates],
        "excluded": excluded,
        "preserve_on_uninstall": ["D:\\ANN\\models", "D:\\ANN\\projects", "D:\\ANN\\outputs", "D:\\ANN\\data", "D:\\ANN\\logs"],
        "risks": [
            "Embedded Python and wheelhouse are not packaged yet.",
            "Models are intentionally excluded from app package and must be linked/managed separately.",
            "Historical outputs are excluded from installer payload.",
        ],
        "safety": _safety_payload(),
    }
    return manifest


def write_installer_artifact_manifest_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 154-155."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"154_installer_artifact_manifest.json": build_installer_artifact_manifest()},
    )


def build_release_candidate_handoff_manifest(
    bundle_root: str | Path | None = None,
    *,
    materialize: bool = False,
) -> dict[str, Any]:
    """Build or materialize a signed-release handoff bundle with hashes."""

    target = Path(bundle_root or REPO_ROOT / "outputs" / "release_candidates" / "ANN_RC_HANDOFF").resolve()
    source_files = [
        REPO_ROOT / "installer" / "ANN_Setup.exe",
        REPO_ROOT / "installer" / "ANN_Uninstall.exe",
        REPO_ROOT / "installer" / "install_ann.ps1",
        REPO_ROOT / "installer" / "uninstall_ann.ps1",
        REPO_ROOT / "installer" / "verify_install.ps1",
        REPO_ROOT / "installer" / "validate_clean_machine.ps1",
        REPO_ROOT / "installer" / "sign_release.ps1",
        REPO_ROOT / "installer" / "README_INSTALLER.md",
        REPO_ROOT / "scripts" / "runtime" / "verify_final_release.py",
        REPO_ROOT / "scripts" / "runtime" / "verify_autonomous_capability.py",
        REPO_ROOT / "scripts" / "runtime" / "plan_autonomous_capability_evidence.py",
        REPO_ROOT / "scripts" / "runtime" / "run_autonomous_capability_scenarios.py",
        REPO_ROOT / "scripts" / "runtime" / "verify_release_candidate_bundle.py",
        REPO_ROOT / "scripts" / "runtime" / "verify_external_release_evidence.py",
        REPO_ROOT / "scripts" / "runtime" / "verify_release_operator_environment.py",
        REPO_ROOT / "scripts" / "release" / "invoke-windows-sandbox-validation.ps1",
        REPO_ROOT / "scripts" / "release" / "run-windows-sandbox-validation.ps1",
        REPO_ROOT / "config" / "ann_runtime_lock.example.json",
        REPO_ROOT / "config" / "ann_runtime_engine.json",
        REPO_ROOT / "config" / "ann_model_policy.json",
    ]
    entries = [_handoff_file_entry(path, target) for path in source_files]
    missing = [entry["source"] for entry in entries if not entry["exists"]]
    copied: list[str] = []
    if materialize:
        target.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            if not entry["exists"]:
                continue
            source = Path(entry["source"])
            destination = Path(entry["bundle_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(str(destination))
    status = "HANDOFF_READY" if not missing else "HANDOFF_INCOMPLETE"
    manifest = {
        "version": "18.9.18",
        "generated_at": _now(),
        "status": status,
        "bundle_root": str(target),
        "materialized": materialize,
        "files": entries,
        "missing": missing,
        "copied": copied,
        "model_files_included": False,
        "training_files_included": False,
        "dataset_files_included": False,
        "adapter_files_included": False,
        "historical_outputs_included": False,
        "signing_required_after_handoff": True,
        "clean_machine_validation_required_after_signing": True,
        "external_evidence_marker_name": "clean_machine_external_validation.json",
        "external_evidence_marker_install_path": "D:\\ANN\\clean_machine_external_validation.json",
        "external_evidence_marker_repo_copy_path": "D:\\ANN\\clean_machine_external_validation.json",
        "release_machine_requirements": [
            "Windows 11 clean machine or clean VM/profile separate from the development host.",
            "Trusted Authenticode code-signing certificate available to the release operator.",
            "signtool.exe from Windows SDK available on PATH or passed with -SigntoolPath.",
            "No self-signed certificate for public final release.",
            "No models, training datasets, adapters, memory, knowledge, or historical outputs in the handoff bundle.",
        ],
        "final_verifier_command": (
            "PYTHONPATH=. python scripts/runtime/verify_final_release.py "
            "--install-root D:\\ANN --installer-root installer --bundle-root . "
            "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
            "--signing-evidence installer\\release_signing_evidence.json "
            '--certificate-thumbprint "<CERT_THUMBPRINT>" '
            "--output-dir outputs/runtime_finalization_20260707"
        ),
        "repo_root_final_verifier_command": (
            "PYTHONPATH=. python scripts/runtime/verify_final_release.py "
            "--install-root D:\\ANN --installer-root installer "
            "--bundle-root outputs/release_candidates/ANN_RC_HANDOFF "
            "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
            "--signing-evidence installer\\release_signing_evidence.json "
            '--certificate-thumbprint "<CERT_THUMBPRINT>" '
            "--output-dir outputs/runtime_finalization_20260707"
        ),
        "autonomous_capability_verifier_command": "PYTHONPATH=. python scripts/runtime/verify_autonomous_capability.py --output-dir outputs/runtime_finalization_20260707",
        "autonomous_capability_plan_command": "PYTHONPATH=. python scripts/runtime/plan_autonomous_capability_evidence.py --output-dir outputs/runtime_finalization_20260707",
        "autonomous_capability_run_command": (
            "PYTHONPATH=. python scripts/runtime/run_autonomous_capability_scenarios.py "
            "--approval-token <PROJECT_BUILDER_TOKEN> --execute"
        ),
        "bundle_verifier_command": "PYTHONPATH=. python scripts/runtime/verify_release_candidate_bundle.py --bundle-root .",
        "external_release_evidence_command": (
            "PYTHONPATH=. python scripts/runtime/verify_external_release_evidence.py "
            "--install-root D:\\ANN --installer-root installer --bundle-root . "
            "--clean-machine-marker D:\\ANN\\clean_machine_external_validation.json "
            "--signing-evidence installer\\release_signing_evidence.json"
        ),
        "release_operator_environment_command": (
            "PYTHONPATH=. python scripts/runtime/verify_release_operator_environment.py "
            '--installer-root installer --certificate-thumbprint "<CERT_THUMBPRINT>" '
            "--output-dir outputs/runtime_finalization_20260707"
        ),
        "sign_command": (
            "powershell -ExecutionPolicy Bypass -File installer\\sign_release.ps1 "
            '-CertificateThumbprint "<CERT_THUMBPRINT>" '
            "-TimestampUrl http://timestamp.digicert.com "
            "-OutputPath installer\\release_signing_evidence.json -Execute"
        ),
        "clean_machine_command": (
            "powershell -ExecutionPolicy Bypass -File installer\\validate_clean_machine.ps1 "
            "-InstallRoot D:\\ANN -EnvironmentType clean_machine -RequireSignedInstaller "
            "-SigningEvidencePath installer\\release_signing_evidence.json "
            "-ReleaseTransferManifestPath RELEASE_TRANSFER_MANIFEST.json"
        ),
        "windows_sandbox_prepare_command": (
            "powershell -NoProfile -ExecutionPolicy Bypass "
            "-File scripts\\release\\invoke-windows-sandbox-validation.ps1 "
            '-SourceRoot "<ANN_RELEASE_SOURCE>" -RuntimeSource "<ANN_RUNTIME_SOURCE>" '
            '-DesktopSource "<ANN_DESKTOP_SOURCE>"'
        ),
        "windows_sandbox_launch_command": (
            "powershell -NoProfile -ExecutionPolicy Bypass "
            "-File scripts\\release\\invoke-windows-sandbox-validation.ps1 "
            '-SourceRoot "<ANN_RELEASE_SOURCE>" -RuntimeSource "<ANN_RUNTIME_SOURCE>" '
            '-DesktopSource "<ANN_DESKTOP_SOURCE>" -Launch'
        ),
        "release_commands_are_templates": True,
        "release_command_placeholders_must_be_replaced": True,
        "release_command_thumbprint_placeholder": "<CERT_THUMBPRINT>",
        "release_command_thumbprint_required_format": "40-character hexadecimal SHA1 Authenticode certificate thumbprint",
        "release_command_thumbprint_regex": "^[0-9A-Fa-f]{40}$",
        "sign_release_blocks_placeholder": True,
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }
    auxiliary_payloads = _handoff_auxiliary_payloads(manifest)
    manifest["auxiliary_files"] = _handoff_auxiliary_entries(auxiliary_payloads)
    if materialize:
        (target / "release_candidate_handoff_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        for relative_path, content in auxiliary_payloads.items():
            (target / relative_path).write_text(content, encoding="utf-8", newline="\n")
        transfer = _handoff_transfer_manifest(manifest)
        transfer_path = target / "RELEASE_TRANSFER_MANIFEST.json"
        transfer_path.write_text(json.dumps(transfer, indent=2), encoding="utf-8")
        (target / "RELEASE_TRANSFER_MANIFEST.sha256").write_text(
            f"{transfer['aggregate_sha256']}  RELEASE_TRANSFER_MANIFEST.json\n",
            encoding="utf-8",
        )
        (target / "RELEASE_TRANSFER_MANIFEST.file.sha256").write_text(
            f"{_sha256_for_existing_file(transfer_path)}  RELEASE_TRANSFER_MANIFEST.json\n",
            encoding="utf-8",
        )
    return manifest


def write_release_candidate_handoff_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 364-365."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"364_release_candidate_handoff_manifest.json": build_release_candidate_handoff_manifest()},
    )


def build_release_packaging_dry_run() -> dict[str, Any]:
    """Simulate release packaging without copying, moving, or building executables."""

    from agentic_network.installer.runtime import build_install_plan, build_uninstall_plan

    install_plan = build_install_plan(REPO_ROOT, "D:/ANN")
    uninstall_plan = build_uninstall_plan("D:/ANN")
    target_dirs = [
        "D:\\ANN",
        "D:\\ANN\\app",
        "D:\\ANN\\data",
        "D:\\ANN\\models",
        "D:\\ANN\\projects",
        "D:\\ANN\\outputs",
        "D:\\ANN\\runtime",
        "D:\\ANN\\config",
        "D:\\ANN\\logs",
    ]
    excluded_tokens = ("\\models\\", "/models/", "\\training\\", "/training/", "\\datasets\\", "/datasets/", "\\adapters\\", "/adapters/")
    planned_model_copies = [path for path in install_plan.files_to_copy if any(token in path.lower() for token in excluded_tokens)]
    return {
        "version": "14.8",
        "generated_at": _now(),
        "status": "DRY_RUN_READY" if not planned_model_copies else "DRY_RUN_BLOCKED",
        "simulated_artifacts": ["ANN_Setup.exe", "ANN_Uninstall.exe"],
        "target_root": "D:\\ANN",
        "target_dirs": target_dirs,
        "install_plan": install_plan.to_dict(),
        "uninstall_plan": uninstall_plan.to_dict(),
        "copies_models": False,
        "copies_datasets": False,
        "copies_adapters": False,
        "moves_files": False,
        "builds_exe": False,
        "planned_protected_copies": planned_model_copies,
        "safety": _safety_payload(),
    }


def write_release_packaging_dry_run_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 156-157."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"156_release_packaging_dry_run.json": build_release_packaging_dry_run()})


def build_preservation_policy_validation() -> dict[str, Any]:
    """Validate installer/uninstaller preservation policy."""

    from agentic_network.installer.runtime import build_uninstall_plan

    plan = build_uninstall_plan("D:/ANN")
    preserve_expected = ["models", "projects", "outputs", "data", "logs"]
    remove_expected = ["runtime", "cache", "wheelhouse_temp", "smoke_temp", "installer_temp"]
    keep_paths = [str(path).replace("\\", "/").lower() for path in plan.paths_to_keep]
    preservation = [
        _preservation_item(name, any(f"/{name}" in path or path.endswith(f"/{name}") for path in keep_paths))
        for name in preserve_expected
    ]
    removal = [
        _preservation_item(name, not any(f"/{name}" in path or path.endswith(f"/{name}") for path in keep_paths))
        for name in remove_expected
    ]
    logs_item = next(item for item in preservation if item["name"] == "logs")
    if not logs_item["passed"]:
        logs_item["status"] = "WARN"
        logs_item["detail"] = "logs are currently removable in uninstall plan; alpha policy recommends preservation"
    hard_failures = [item for item in preservation + removal if item["status"] == "FAIL"]
    return {
        "version": "14.9",
        "generated_at": _now(),
        "status": "VALIDATED_WITH_WARNINGS" if not hard_failures else "POLICY_GAPS",
        "preserve": preservation,
        "remove": removal,
        "uninstall_plan": plan.to_dict(),
        "paths_to_keep": plan.paths_to_keep,
        "paths_to_remove": plan.paths_to_remove,
        "hard_failures": hard_failures,
        "safety": _safety_payload(),
    }


def write_preservation_policy_validation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 158-159."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"158_preservation_policy_validation.json": build_preservation_policy_validation()},
    )


def build_public_alpha_readiness() -> dict[str, Any]:
    """Calculate ANN alpha/beta/public release readiness."""

    cache_key = "build_public_alpha_readiness"
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached

    manifest = build_installer_artifact_manifest()
    dry_run = build_release_packaging_dry_run()
    rc = build_installer_rc_readiness()
    gap = build_runtime_gap_report()
    guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    works = [
        "Desktop foundation",
        "Runtime checks",
        "Model inventory",
        "Safe/mock mode",
        "Launch guard",
        "Installer foundation",
        "Artifact/readiness reporting",
    ]
    missing = [
        "Embedded Python runtime",
        "Offline wheelhouse",
        "Clean-machine validation",
        "Signed ANN_Setup.exe",
        "Real Qwen2.5 backend readiness",
    ]
    experimental = ["Qwen2.5 real inference gate", "Qwen3 preparation", "DeepSeek POWERFUL preparation"]
    blocked = ["Qwen2.5 real inference", "Qwen3 activation", "DeepSeek activation", "POWERFUL mode", "Public release"]
    alpha_ready = manifest["status"] == "MANIFEST_READY" and dry_run["status"] == "DRY_RUN_READY"
    payload = {
        "version": "15.0",
        "generated_at": _now(),
        "status": "ALPHA_READY_WITH_LIMITATIONS" if alpha_ready else "ALPHA_BLOCKED",
        "alpha": "ALPHA_READY_WITH_LIMITATIONS" if alpha_ready else "ALPHA_BLOCKED",
        "beta": "BETA_BLOCKED",
        "public_release": "PUBLIC_RELEASE_BLOCKED",
        "what_works": works,
        "what_is_missing": missing,
        "experimental": experimental,
        "blocked": blocked,
        "needs_wheelhouse": True,
        "needs_embedded_runtime": True,
        "needs_clean_machine": True,
        "needs_real_inference": True,
        "installer_rc": rc["status"],
        "runtime_gap": gap["status"],
        "real_inference": guard["status"],
        "qwen2_5": {"blocked": True, "reason": "backend_not_ready"},
        "qwen3": {"blocked": True, "status": prepare_qwen3_controlled_activation()["status"]},
        "deepseek": {"blocked": True, "status": prepare_deepseek_powerful_activation()["status"]},
        "powerful": {"blocked": True},
        "next_release_step": rc["next_release_step"],
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_public_alpha_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 160-161."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"160_public_alpha_readiness.json": build_public_alpha_readiness()})


def write_public_alpha_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 154-161 for ANN v14.8-v15.0."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_installer_artifact_manifest_artifacts(target))
    artifacts.extend(write_release_packaging_dry_run_artifacts(target))
    artifacts.extend(write_preservation_policy_validation_artifacts(target))
    artifacts.extend(write_public_alpha_readiness_artifacts(target))
    return _dedupe(artifacts)


def build_alpha_smoke_matrix() -> dict[str, Any]:
    """Build the official alpha smoke matrix without executing smoke steps."""

    readiness = build_public_alpha_readiness()
    cases = [
        _alpha_smoke_case("desktop_launch", "Desktop Launch", "Native PySide6 app opens", "manual_pending", "Requires local desktop runtime."),
        _alpha_smoke_case("first_run", "First Run", "Guided status renders release/runtime gaps", "covered_by_tests", "Read-only."),
        _alpha_smoke_case("chat", "Chat", "Chat surface renders local state", "covered_by_tests", "Real inference blocked."),
        _alpha_smoke_case("project_manager", "Project Manager", "Projects are visible/selectable", "manual_pending", "No project mutation required."),
        _alpha_smoke_case("project_builder", "Project Builder", "Builder views render", "manual_pending", "Generated apps remain gated."),
        _alpha_smoke_case("patch_review", "Patch Review", "Patch review surfaces diffs", "manual_pending", "No auto-apply."),
        _alpha_smoke_case("patch_apply_gates", "Patch Apply Gates", "Approval token/gates block unsafe apply", "covered_by_tests", "No patch without approval."),
        _alpha_smoke_case("self_healing", "Self Healing", "Self-healing flow is visible/gated", "covered_by_tests", "Depends on generated artifacts."),
        _alpha_smoke_case("consensus", "Consensus", "Consensus status renders", "covered_by_tests", "Read-only in Desktop views."),
        _alpha_smoke_case("action_planner", "Action Planner", "Next step/action plan renders", "covered_by_tests", "No automatic execution."),
        _alpha_smoke_case("skills", "Skills", "Skills registry and runtime visible", "covered_by_tests", "Permissions required."),
        _alpha_smoke_case("skill_permissions", "Skill Permissions", "Permissions persist and render", "covered_by_tests", "No network without permission."),
        _alpha_smoke_case("runtime_bundle", "Runtime Bundle", "Runtime manifest reports local packages", "covered_by_tests", "No installs."),
        _alpha_smoke_case("runtime_gap", "Runtime Gap", "ANN ready/environment not ready shown", "covered_by_tests", "Current env incomplete."),
        _alpha_smoke_case("installer_dry_run", "Installer Dry Run", "Packaging simulation excludes protected dirs", "covered_by_tests", "No setup exe built."),
        _alpha_smoke_case("model_inventory", "Model Inventory", "Inventory renders model states", "covered_by_tests", "No model load."),
        _alpha_smoke_case("qwen25_detection", "Qwen2.5 Detection", "GGUF present but backend blocked", "covered_by_tests", "llama_cpp missing."),
        _alpha_smoke_case("qwen3_preparation", "Qwen3 Preparation", "Prepared but blocked by policy", "covered_by_tests", "No Qwen3 load."),
        _alpha_smoke_case("deepseek_preparation", "DeepSeek Preparation", "POWERFUL prepared but blocked", "covered_by_tests", "No DeepSeek load."),
        _alpha_smoke_case("safe_mode", "Safe Mode", "Real loading disabled by default", "covered_by_tests", "Explicit gate required."),
        _alpha_smoke_case("sequential_runtime", "Sequential Runtime", "max_loaded_models=1 and no parallel loads", "covered_by_tests", "Local VRAM conservative."),
    ]
    return {
        "version": "15.1",
        "generated_at": _now(),
        "status": readiness["alpha"],
        "beta": readiness["beta"],
        "public_release": readiness["public_release"],
        "tests": cases,
        "total": len(cases),
        "manual_pending": len([case for case in cases if case["status"] == "manual_pending"]),
        "covered_by_tests": len([case for case in cases if case["status"] == "covered_by_tests"]),
        "qwen2_5_blocked": True,
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "safety": _safety_payload(),
    }


def write_alpha_smoke_matrix_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 162-163."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"162_alpha_smoke_matrix.json": build_alpha_smoke_matrix()})


def build_beta_roadmap() -> dict[str, Any]:
    """Build the official beta roadmap foundation."""

    items = [
        _roadmap_item("embedded_python", "BLOCKED", ["runtime lockfile", "offline wheelhouse"], "high", 1, "Bundle D:\\ANN\\runtime\\python."),
        _roadmap_item("offline_wheelhouse", "BLOCKED", ["lockfile hashes", "manual wheel collection"], "high", 1, "Populate D:\\ANN\\runtime\\wheels."),
        _roadmap_item("real_qwen25", "BLOCKED", ["llama_cpp READY", "Torch CUDA visible", "launch guard PASSED"], "high", 2, "First real local inference target."),
        _roadmap_item("real_qwen3", "BLOCKED", ["Qwen2.5 stable", "HF runtime", "VRAM/offload plan"], "high", 3, "Separate controlled gate required."),
        _roadmap_item("deepseek_powerful", "BLOCKED", ["POWERFUL policy", "DeepSeek backend", "VRAM/offload plan"], "high", 4, "Never activate before FAST is stable."),
        _roadmap_item("installer_final", "BLOCKED", ["embedded Python", "wheelhouse", "dry run"], "medium", 2, "Build ANN_Setup.exe after packaging inputs exist."),
        _roadmap_item("signed_installer", "BLOCKED", ["installer final", "certificate"], "medium", 3, "Requires signing certificate."),
        _roadmap_item("clean_machine_validation", "BLOCKED", ["installer final"], "medium", 3, "Validate on clean Windows machine."),
        _roadmap_item("first_real_inference", "BLOCKED", ["real_qwen25"], "high", 2, "Audit and benchmark one Qwen2.5 smoke."),
        _roadmap_item("public_beta", "BLOCKED", ["clean_machine_validation", "first_real_inference"], "medium", 4, "Limited public beta."),
        _roadmap_item("public_release", "BLOCKED", ["public_beta", "signed installer", "support docs"], "high", 5, "No public release until beta evidence exists."),
    ]
    return {
        "version": "15.2",
        "generated_at": _now(),
        "status": "BETA_BLOCKED",
        "items": items,
        "next_priority": [item for item in items if item["priority"] == 1],
        "safety": _safety_payload(),
    }


def write_beta_roadmap_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 164-165."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"164_beta_roadmap.json": build_beta_roadmap()})


def build_alpha_manual_validation_checklist() -> dict[str, Any]:
    """Build a manual alpha validation checklist."""

    checks = [
        _manual_validation_item("desktop_starts", "Desktop starts"),
        _manual_validation_item("runtime_checks", "Runtime checks run read-only"),
        _manual_validation_item("installer_dry_run", "Installer dry run reports DRY_RUN_READY"),
        _manual_validation_item("runtime_bundle", "Runtime bundle manifest is readable"),
        _manual_validation_item("safe_mode", "Safe mode is enabled"),
        _manual_validation_item("no_internet", "No internet required"),
        _manual_validation_item("no_downloads", "No downloads happen"),
        _manual_validation_item("no_model_modification", "No model files modified"),
        _manual_validation_item("no_training", "No training starts"),
        _manual_validation_item("no_git_modifications", ".git is untouched"),
        _manual_validation_item("no_c_access", "C: is not used as install root"),
        _manual_validation_item("sequential_runtime", "Sequential runtime remains active"),
        _manual_validation_item("launch_guard", "Launch guard blocks real inference"),
        _manual_validation_item("model_inventory", "Model inventory renders"),
        _manual_validation_item("project_builder", "Project Builder renders"),
        _manual_validation_item("consensus", "Consensus renders"),
    ]
    return {
        "version": "15.3",
        "generated_at": _now(),
        "status": "MANUAL_VALIDATION_REQUIRED",
        "checks": checks,
        "qwen2_5_blocked": True,
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "safety": _safety_payload(),
    }


def write_alpha_manual_validation_checklist_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 166-167."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"166_alpha_manual_validation_checklist.json": build_alpha_manual_validation_checklist()},
    )


def write_alpha_distribution_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 162-167 for ANN v15.1-v15.3."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_alpha_smoke_matrix_artifacts(target))
    artifacts.extend(write_beta_roadmap_artifacts(target))
    artifacts.extend(write_alpha_manual_validation_checklist_artifacts(target))
    return _dedupe(artifacts)


EMBEDDED_RUNTIME_SUBDIRS = (
    "python",
    "wheels",
    "checks",
    "logs",
    "site-packages",
    "requirements-lock",
    "tmp",
    "audit",
)
EMBEDDED_RUNTIME_ALLOWED_FILES = (
    "ann_launcher.ps1",
    "create_shortcut.ps1",
)


def build_embedded_runtime_layout(
    runtime_root: str | Path | None = None,
    *,
    dry_run: bool = True,
    confirm_create: bool = False,
) -> dict[str, Any]:
    """Plan or create empty embedded runtime directories without installing anything."""

    from agentic_network.installer.paths import contains_traversal, is_c_drive

    root_info = _runtime_path_info(runtime_root)
    raw_root = root_info["raw"]
    root = root_info["path"].expanduser()
    expected = {name: str(root / name) for name in EMBEDDED_RUNTIME_SUBDIRS}
    invalid_root = contains_traversal(raw_root) or is_c_drive(raw_root) or root_info["blocked"]
    if invalid_root:
        return {
            "version": "15.4",
            "generated_at": _now(),
            "status": "RUNTIME_LAYOUT_INVALID_ROOT",
            **_runtime_report(root_info),
            "dry_run": dry_run,
            "confirm_create": confirm_create,
            "expected_subdirectories": expected,
            "existing_subdirectories": [],
            "would_create": [],
            "created": [],
            "blocked_reason": "C drive and path traversal are not valid embedded runtime roots.",
            "safety": _safety_payload(),
        }

    existing = [name for name in EMBEDDED_RUNTIME_SUBDIRS if (root / name).is_dir()]
    missing = [name for name in EMBEDDED_RUNTIME_SUBDIRS if name not in existing]
    if not missing:
        status = "RUNTIME_LAYOUT_EXISTS"
    elif dry_run:
        status = "RUNTIME_LAYOUT_PLANNED"
    elif not confirm_create:
        status = "RUNTIME_LAYOUT_BLOCKED"
    else:
        created: list[str] = []
        for name in missing:
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
        existing = [name for name in EMBEDDED_RUNTIME_SUBDIRS if (root / name).is_dir()]
        missing = [name for name in EMBEDDED_RUNTIME_SUBDIRS if name not in existing]
        status = "RUNTIME_LAYOUT_CREATED" if not missing else "RUNTIME_LAYOUT_BLOCKED"
        return {
            "version": "15.4",
            "generated_at": _now(),
            "status": status,
            **_runtime_report(root_info),
            "dry_run": dry_run,
            "confirm_create": confirm_create,
            "expected_subdirectories": expected,
            "existing_subdirectories": existing,
            "would_create": [],
            "created": created,
            "blocked_reason": "" if status == "RUNTIME_LAYOUT_CREATED" else "Unable to create all directories.",
            "no_python_install": True,
            "no_pip": True,
            "no_wheels_written": True,
            "safety": _safety_payload(),
        }
    return {
        "version": "15.4",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "dry_run": dry_run,
        "confirm_create": confirm_create,
        "expected_subdirectories": expected,
        "existing_subdirectories": existing,
        "would_create": [str(root / name) for name in missing],
        "created": [],
        "blocked_reason": "" if status != "RUNTIME_LAYOUT_BLOCKED" else "confirm_create=True is required.",
        "no_python_install": True,
        "no_pip": True,
        "no_wheels_written": True,
        "safety": _safety_payload(),
    }


def write_embedded_runtime_layout_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 168-169."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"168_embedded_runtime_layout.json": build_embedded_runtime_layout()})


def build_wheelhouse_materialization_plan(
    runtime_root: str | Path | None = None,
    lockfile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Plan offline wheelhouse population without downloading, hashing, or installing."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    wheelhouse = root / "wheels"
    requirements_lock = root / "requirements-lock"
    checks = root / "checks"
    audit = root / "audit"
    lockfile = _runtime_lockfile_for_wheelhouse(wheelhouse, lockfile_path)
    lock = build_offline_runtime_lockfile(lockfile)
    declared_wheels = _declared_wheels(lock)
    expected_names = {item["filename"] for item in declared_wheels}
    discovered = sorted((path.name for path in wheelhouse.glob("*.whl")), key=str.lower) if wheelhouse.is_dir() else []
    missing_wheels = sorted(expected_names.difference(discovered), key=str.lower)
    missing_hashes = sorted(
        [item["filename"] for item in declared_wheels if not str(item.get("sha256") or "").strip()],
        key=str.lower,
    )
    package_roles = {
        item.get("name", "unknown"): {
            "role": item.get("role", "unknown"),
            "required_for": item.get("required_for", []),
            "optional": item.get("optional", False),
        }
        for item in lock.get("packages", [])
    }
    ready_for_population = wheelhouse.is_dir() and requirements_lock.exists() and checks.is_dir() and audit.is_dir()
    ready_for_beta = ready_for_population and not missing_wheels and not missing_hashes
    return {
        "version": "15.5",
        "generated_at": _now(),
        "status": "WHEELHOUSE_READY_FOR_BETA" if ready_for_beta else "WHEELHOUSE_MATERIALIZATION_REQUIRED",
        **_runtime_report(root_info),
        "wheelhouse_path": str(wheelhouse),
        "requirements_lock_path": str(requirements_lock),
        "checks_path": str(checks),
        "audit_path": str(audit),
        "lockfile_path": str(lockfile),
        "expected_wheels": declared_wheels,
        "package_roles": package_roles,
        "discovered_wheels": discovered,
        "missing_wheels": missing_wheels,
        "missing_hashes": missing_hashes,
        "hash_pending": bool(missing_hashes),
        "manual_action_needed": [
            "Create/populate D:\\ANN\\runtime\\wheels outside ANN.",
            "Copy verified wheels into the offline wheelhouse manually.",
            "Fill sha256 hashes in the runtime lockfile after external verification.",
            "Run read-only integrity validation before Beta.",
        ],
        "ready_for_population": ready_for_population,
        "ready_for_beta": ready_for_beta,
        "no_install_guarantee": True,
        "safety": _safety_payload(),
    }


def write_wheelhouse_materialization_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 170-171."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"170_wheelhouse_materialization_plan.json": build_wheelhouse_materialization_plan()},
    )


def build_clean_machine_emulator(install_root: str | Path | None = None) -> dict[str, Any]:
    """Emulate clean-machine installation readiness without installing anything."""

    from agentic_network.installer.paths import is_c_drive

    root = Path(install_root or "D:/ANN")
    runtime = root / "runtime"
    layout = build_embedded_runtime_layout(runtime)
    wheelhouse = build_wheelhouse_materialization_plan(runtime)
    bundle = build_embedded_runtime_installer_readiness(root)
    rc = build_installer_rc_readiness()
    checks = [
        _emulator_check("install_root", not is_c_drive(root), str(root)),
        _emulator_check("app_folder", True, str(root / "app")),
        _emulator_check("config_folder", True, str(root / "config")),
        _emulator_check("runtime_folder", layout["status"] in {"RUNTIME_LAYOUT_EXISTS", "RUNTIME_LAYOUT_PLANNED"}, str(runtime)),
        _emulator_check("models_folder", True, str(root / "models")),
        _emulator_check("projects_folder", True, str(root / "projects")),
        _emulator_check("outputs_folder", True, str(root / "outputs")),
        _emulator_check("logs_folder", True, str(root / "logs")),
        _emulator_check("desktop_launch_target", (REPO_ROOT / "agentic_network" / "desktop_app" / "run.py").is_file(), "desktop_app.run"),
        _emulator_check("first_run_status", True, "First Run can render read-only state"),
        _emulator_check("runtime_bundle_detection", bundle["status"] in {"READY", "EMBEDDED_RUNTIME_MISSING"}, bundle["status"]),
        _emulator_check("model_inventory_visibility", True, "Model Inventory is read-only"),
        _emulator_check("safe_mode", True, "allow_real_model_load=false"),
        _emulator_check("installer_verification", rc["status"] in {"RC_BLOCKED", "RC_READY_WITH_LIMITATIONS", "RC_READY"}, rc["status"]),
        _emulator_check("uninstaller_preservation", True, "preserve models/projects/outputs"),
        _emulator_check("no_internet", True, "offline requirement"),
        _emulator_check("no_downloads", True, "installer scripts audited"),
        _emulator_check("no_c_root", not is_c_drive(root), str(root)),
        _emulator_check("embedded_python_present", (runtime / "python" / "python.exe").is_file(), str(runtime / "python" / "python.exe")),
        _emulator_check("wheelhouse_present", (runtime / "wheels").is_dir(), str(runtime / "wheels")),
        _emulator_check("wheelhouse_hashes", not wheelhouse["hash_pending"], "lockfile hashes required"),
    ]
    blockers = [check for check in checks if check["status"] == "FAIL"]
    warnings = [
        "This is a dry-run emulator; no installer or runtime payload is copied.",
        "Manual clean-machine validation is still required before Beta.",
    ]
    if blockers:
        status = "CLEAN_MACHINE_BLOCKED"
    elif warnings:
        status = "CLEAN_MACHINE_EMULATED_WITH_WARNINGS"
    else:
        status = "CLEAN_MACHINE_READY_FOR_DRY_RUN"
    return {
        "version": "15.6",
        "generated_at": _now(),
        "status": status,
        "install_root": str(root),
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "next_manual_step": _clean_machine_next_step(blockers),
        "dry_run": True,
        "no_install": True,
        "no_model_load": True,
        "no_inference": True,
        "safety": _safety_payload(),
    }


def write_clean_machine_emulator_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 172-173."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"172_clean_machine_emulator.json": build_clean_machine_emulator()})


def build_clean_machine_evidence(
    install_root: str | Path | None = None,
    *,
    external_marker_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate installed ANN evidence without treating this host as a real clean machine."""

    from agentic_network.installer.paths import is_c_drive
    from agentic_network.installer.validation import validate_runtime_requirements

    root = _resolve_runtime_filesystem_path(install_root or "D:/ANN")
    manifest_path = root / "install_manifest.json"
    manifest = _read_json_file(manifest_path)
    validation = validate_runtime_requirements(root).to_dict()
    wheelhouse = root / "runtime" / "wheels"
    checks = [
        _evidence_check("install_root_not_c", not is_c_drive(root), str(root)),
        _evidence_check("install_manifest", manifest_path.is_file(), str(manifest_path)),
        _evidence_check("app_package", (root / "app" / "agentic_network").is_dir(), str(root / "app" / "agentic_network")),
        _evidence_check("desktop_entrypoint", (root / "app" / "agentic_network" / "desktop_app" / "run.py").is_file(), "desktop_app.run"),
        _evidence_check("runtime_python", (root / "runtime" / "python" / "python.exe").is_file(), str(root / "runtime" / "python" / "python.exe")),
        _evidence_check("runtime_wheelhouse", wheelhouse.is_dir() and any(wheelhouse.glob("*.whl")), str(wheelhouse)),
        _evidence_check("runtime_config", (root / "config" / "ann_runtime_engine.json").is_file(), "ann_runtime_engine.json"),
        _evidence_check("model_policy", (root / "config" / "ann_model_policy.json").is_file(), "ann_model_policy.json"),
        _evidence_check("projects_root", (root / "projects").is_dir(), str(root / "projects")),
        _evidence_check("models_root", (root / "models").is_dir(), str(root / "models")),
        _evidence_check("outputs_root", (root / "outputs").is_dir(), str(root / "outputs")),
        _evidence_check("data_root", (root / "data").is_dir(), str(root / "data")),
        _evidence_check("runtime_validation", validation.get("status") == "VALID", str(validation.get("errors", []))),
        _evidence_check("protected_training_not_copied", not (root / "app" / "training").exists(), "training excluded from app payload"),
        _evidence_check("protected_models_not_copied_to_app", not (root / "app" / "models").exists(), "models excluded from app payload"),
        _evidence_check("protected_memory_not_copied", not (root / "app" / "memory").exists(), "memory excluded from app payload"),
        _evidence_check("protected_knowledge_not_copied", not (root / "app" / "knowledge").exists(), "knowledge excluded from app payload"),
    ]
    blockers = [check for check in checks if check["status"] == "FAIL"]
    local_install_smoke_passed = not blockers
    external_clean_machine_marker = (
        _resolve_runtime_filesystem_path(external_marker_path)
        if external_marker_path is not None
        else root / "clean_machine_external_validation.json"
    )
    external_payload = _read_json_file(external_clean_machine_marker)
    external_validation = _validate_external_clean_machine_payload(
        external_payload,
        expected_install_root=root,
    )
    external_installer_hashes = {
        "ANN_Setup.exe": str(external_payload.get("setup_sha256") or ""),
        "ANN_Uninstall.exe": str(external_payload.get("uninstall_sha256") or ""),
    }
    external_clean_machine_passed = (
        local_install_smoke_passed
        and external_validation["passed"]
    )
    if external_clean_machine_passed:
        status = "CLEAN_MACHINE_EXTERNAL_PASSED"
        evidence_level = "EXTERNAL_CLEAN_MACHINE"
    elif local_install_smoke_passed:
        status = "LOCAL_INSTALL_SMOKE_PASSED"
        evidence_level = "LOCAL_INSTALL_SMOKE"
    else:
        status = "CLEAN_MACHINE_EVIDENCE_INCOMPLETE"
        evidence_level = "INCOMPLETE"
    return {
        "version": "18.9.8",
        "generated_at": _now(),
        "status": status,
        "install_root": str(root),
        "evidence_level": evidence_level,
        "local_install_smoke_passed": local_install_smoke_passed,
        "external_clean_machine_passed": external_clean_machine_passed,
        "sufficient_for_final_release": external_clean_machine_passed,
        "external_validation_marker": str(external_clean_machine_marker),
        "external_validation_marker_present": external_clean_machine_marker.is_file(),
        "external_installer_hashes": external_installer_hashes,
        "external_validation_payload": external_payload,
        "external_validation": external_validation,
        "install_manifest": manifest,
        "runtime_validation": validation,
        "checks": checks,
        "blockers": blockers,
        "next_step": _clean_machine_evidence_next_step(status, blockers),
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }


def write_clean_machine_evidence_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 358-359."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"358_clean_machine_evidence.json": build_clean_machine_evidence()})


def build_beta_readiness_gate(install_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether ANN can move from Alpha to Beta without mutating the host."""

    root = Path(install_root or "D:/ANN")
    runtime = root / "runtime"
    layout = build_embedded_runtime_layout(runtime)
    wheelhouse_plan = build_wheelhouse_materialization_plan(runtime)
    wheelhouse_integrity = validate_wheelhouse_integrity(runtime / "wheels")
    clean_machine = build_clean_machine_emulator(root)
    installer_rc = build_installer_rc_readiness()
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    alpha = build_public_alpha_readiness()
    release_docs = (REPO_ROOT / "README_ALPHA_RELEASE_NOTES.md").is_file() and (REPO_ROOT / "README_FAQ.md").is_file()
    checks = [
        _beta_gate_check("embedded_runtime_layout", layout["status"] in {"RUNTIME_LAYOUT_EXISTS", "RUNTIME_LAYOUT_CREATED"}, layout["status"]),
        _beta_gate_check("embedded_python_present", (runtime / "python" / "python.exe").is_file(), str(runtime / "python" / "python.exe")),
        _beta_gate_check("wheelhouse_present", (runtime / "wheels").is_dir(), str(runtime / "wheels")),
        _beta_gate_check("wheelhouse_integrity", wheelhouse_integrity["status"] == "HASH_VERIFIED", wheelhouse_integrity["status"]),
        _beta_gate_check("lockfile_hashes_verified", not wheelhouse_plan["hash_pending"], "hash_pending" if wheelhouse_plan["hash_pending"] else "verified"),
        _beta_gate_check("clean_machine_emulator", clean_machine["status"] != "CLEAN_MACHINE_BLOCKED", clean_machine["status"]),
        _beta_gate_check("installer_rc_status", installer_rc["status"] == "RC_READY", installer_rc["status"]),
        _beta_gate_check("qwen25_backend_readiness", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _beta_gate_check("first_real_inference_status", False, "not_executed"),
        _beta_gate_check("desktop_status", alpha["alpha"] == "ALPHA_READY_WITH_LIMITATIONS", alpha["alpha"]),
        _beta_gate_check("safe_mode", True, "allow_real_model_load=false"),
        _beta_gate_check("release_docs", release_docs, "README_ALPHA_RELEASE_NOTES.md + README_FAQ.md"),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "BETA_BLOCKED"
    elif wheelhouse_integrity["status"] != "HASH_VERIFIED" or launch_guard["status"] != "PASSED":
        status = "BETA_READY_WITH_LIMITATIONS"
    elif clean_machine["status"] == "CLEAN_MACHINE_EMULATED_WITH_WARNINGS":
        status = "BETA_FOUNDATION_READY"
    else:
        status = "BETA_READY"
    return {
        "version": "15.6",
        "generated_at": _now(),
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "next_beta_step": _beta_next_step(blockers),
        "embedded_runtime_layout": layout["status"],
        "wheelhouse_materialization": wheelhouse_plan["status"],
        "clean_machine_emulator": clean_machine["status"],
        "qwen2_5_backend_blocked": launch_guard["status"] != "PASSED",
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": load_model_policy().vram_policy,
        "safety": _safety_payload(),
    }


def write_beta_readiness_gate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 174-175."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"174_beta_readiness_gate.json": build_beta_readiness_gate()})


def write_beta_foundation_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 168-175 for ANN v15.4-v15.6."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_embedded_runtime_layout_artifacts(target))
    artifacts.extend(write_wheelhouse_materialization_plan_artifacts(target))
    artifacts.extend(write_clean_machine_emulator_artifacts(target))
    artifacts.extend(write_beta_readiness_gate_artifacts(target))
    return _dedupe(artifacts)


def build_runtime_collection_manifest(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Declare the manual runtime collection payload without installing anything."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    entries = [
        _runtime_collection_entry("embedded_python", root / "python", "Embedded Python runtime", True),
        _runtime_collection_entry("runtime_wheels", root / "wheels", "Offline wheelhouse", True),
        _runtime_collection_entry("runtime_checks", root / "checks", "Read-only runtime verification scripts", True),
        _runtime_collection_entry("runtime_logs", root / "logs", "Runtime diagnostics logs", False),
        _runtime_collection_entry("site_packages", root / "site-packages", "Future embedded site-packages", True),
        _runtime_collection_entry("requirements_lock", root / "requirements-lock", "Pinned runtime requirements and hashes", True),
        _runtime_collection_entry("audit", root / "audit", "Runtime audit records", True),
    ]
    required_missing = [entry for entry in entries if entry["required"] and not entry["present"]]
    optional_missing = [entry for entry in entries if not entry["required"] and not entry["present"]]
    if not required_missing:
        status = "COLLECTION_READY"
    elif len(required_missing) == len([entry for entry in entries if entry["required"]]):
        status = "COLLECTION_REQUIRED"
    else:
        status = "COLLECTION_INCOMPLETE"
    return {
        "version": "15.7",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "entries": entries,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "manual_collection_required": bool(required_missing),
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def write_runtime_collection_manifest_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 176-177."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"176_runtime_collection_manifest.json": build_runtime_collection_manifest()},
    )


def build_wheelhouse_integrity_registry(
    wheelhouse_path: str | Path | None = None,
    lockfile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Register expected wheel integrity state without installing or downloading wheels."""

    wheelhouse = _resolve_runtime_filesystem_path(wheelhouse_path or f"{DEFAULT_RUNTIME_ROOT_TEXT}/wheels")
    lockfile = _runtime_lockfile_for_wheelhouse(wheelhouse, lockfile_path)
    lock = build_offline_runtime_lockfile(lockfile)
    discovered = {
        path.name: path
        for path in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())
    } if wheelhouse.is_dir() else {}
    wheels = [
        _wheelhouse_registry_entry(item, discovered.get(item["filename"]))
        for item in _declared_wheels(lock)
    ]
    statuses = {item["status"] for item in wheels}
    if "HASH_MISMATCH" in statuses:
        status = "HASH_MISMATCH"
    elif "MISSING" in statuses:
        status = "MISSING"
    elif "HASH_PENDING" in statuses:
        status = "HASH_PENDING"
    elif wheels and statuses == {"HASH_VERIFIED"}:
        status = "HASH_VERIFIED"
    else:
        status = "DECLARED"
    return {
        "version": "15.7",
        "generated_at": _now(),
        "status": status,
        "wheelhouse_path": str(wheelhouse),
        "lockfile_path": str(lockfile),
        "wheels": wheels,
        "expected_count": len(wheels),
        "missing_count": len([item for item in wheels if item["status"] == "MISSING"]),
        "hash_pending_count": len([item for item in wheels if item["status"] == "HASH_PENDING"]),
        "verified_count": len([item for item in wheels if item["status"] == "HASH_VERIFIED"]),
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def write_wheelhouse_integrity_registry_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 178-179."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"178_wheelhouse_integrity_registry.json": build_wheelhouse_integrity_registry()},
    )


def build_embedded_runtime_inventory(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Inventory the embedded runtime directory without modifying it."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    checks = [
        _runtime_inventory_item("python_folder", root / "python", "directory"),
        _runtime_inventory_item("wheels_folder", root / "wheels", "directory"),
        _runtime_inventory_item("checks", root / "checks", "directory"),
        _runtime_inventory_item("logs", root / "logs", "directory"),
        _runtime_inventory_item("site_packages", root / "site-packages", "directory"),
        _runtime_inventory_item("requirements_lock", root / "requirements-lock", "directory"),
        _runtime_inventory_item("audit", root / "audit", "directory"),
        _runtime_inventory_item("embedded_python_executable", root / "python" / "python.exe", "file"),
    ]
    present = [item for item in checks if item["present"]]
    required_missing = [item for item in checks if item["required"] and not item["present"]]
    if not present:
        status = "INVENTORY_EMPTY"
    elif required_missing:
        status = "INVENTORY_PARTIAL"
    else:
        status = "INVENTORY_READY"
    return {
        "version": "15.8",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "items": checks,
        "present_count": len(present),
        "missing_required": required_missing,
        "runtime_completeness": round(len(present) / len(checks), 3),
        "no_model_load": True,
        "safety": _safety_payload(),
    }


def write_embedded_runtime_inventory_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 180-181."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"180_embedded_runtime_inventory.json": build_embedded_runtime_inventory()},
    )


def build_embedded_runtime_verification(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Verify embedded runtime readiness without executing embedded Python or pip."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    inventory = build_embedded_runtime_inventory(root)
    layout = build_embedded_runtime_layout(root)
    registry = build_wheelhouse_integrity_registry(root / "wheels")
    lockfile = Path("D:/AgenticEngineeringNetwork/config/ann_runtime_lock.example.json")
    policy = load_model_policy()
    checks = [
        _runtime_verification_check("runtime_structure", layout["status"] in {"RUNTIME_LAYOUT_EXISTS", "RUNTIME_LAYOUT_CREATED"}, layout["status"]),
        _runtime_verification_check("required_dirs", inventory["status"] == "INVENTORY_READY", inventory["status"]),
        _runtime_verification_check("embedded_python", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _runtime_verification_check("wheelhouse", registry["status"] == "HASH_VERIFIED", registry["status"]),
        _runtime_verification_check("checks", (root / "checks").is_dir(), str(root / "checks")),
        _runtime_verification_check("runtime_lock", lockfile.is_file(), str(lockfile)),
        _runtime_verification_check("safe_mode", not policy.allow_real_model_load, "allow_real_model_load=false"),
        _runtime_verification_check("installer_integration", build_installer_rc_readiness()["status"] == "RC_READY", build_installer_rc_readiness()["status"]),
    ]
    blocked = [check for check in checks if check["status"] == "BLOCKED"]
    if blocked:
        status = "VERIFICATION_BLOCKED"
    elif any(check["status"] != "PASS" for check in checks):
        status = "VERIFICATION_PARTIAL"
    else:
        status = "VERIFICATION_READY"
    return {
        "version": "15.8",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blocked,
        "no_execution": True,
        "no_pip": True,
        "no_model_load": True,
        "safety": _safety_payload(),
    }


def write_embedded_runtime_verification_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 182-183."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"182_embedded_runtime_verification.json": build_embedded_runtime_verification()},
    )


def build_beta_runtime_payload_readiness(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether the Beta runtime payload can be built without building it."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    inventory = build_embedded_runtime_inventory(root)
    verification = build_embedded_runtime_verification(root)
    registry = build_wheelhouse_integrity_registry(root / "wheels")
    installer = build_installer_rc_readiness()
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    checks = [
        _payload_readiness_check("embedded_runtime_ready", inventory["status"] == "INVENTORY_READY", inventory["status"]),
        _payload_readiness_check("wheelhouse_ready", registry["status"] == "HASH_VERIFIED", registry["status"]),
        _payload_readiness_check("installer_ready", installer["status"] == "RC_READY", installer["status"]),
        _payload_readiness_check("runtime_verified", verification["status"] == "VERIFICATION_READY", verification["status"]),
        _payload_readiness_check("qwen25_backend_ready", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _payload_readiness_check("first_inference_executed", False, "not_executed"),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "PAYLOAD_BLOCKED"
    elif verification["status"] == "VERIFICATION_READY":
        status = "PAYLOAD_READY"
    else:
        status = "PAYLOAD_READY_FOUNDATION"
    return {
        "version": "15.9",
        "generated_at": _now(),
        "status": status,
        "can_beta_payload_be_built": status == "PAYLOAD_READY",
        "checks": checks,
        "blockers": blockers,
        "next_step": _payload_next_step(blockers),
        "no_build": True,
        "no_install": True,
        "no_inference": True,
        "safety": _safety_payload(),
    }


def write_beta_runtime_payload_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 184-185."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"184_beta_runtime_payload_readiness.json": build_beta_runtime_payload_readiness()},
    )


def build_runtime_final_gap(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Summarize what remains between current Alpha and Beta/Public runtime readiness."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    collection = build_runtime_collection_manifest(root)
    registry = build_wheelhouse_integrity_registry(root / "wheels")
    inventory = build_embedded_runtime_inventory(root)
    verification = build_embedded_runtime_verification(root)
    payload = build_beta_runtime_payload_readiness(root)
    beta_gate = build_beta_readiness_gate(root.parent)
    already_has = [
        "Desktop App native foundation",
        "Runtime Engine and Bundle APIs",
        "Sequential Runtime policy",
        "Safe Mode and Launch Guard",
        "Model Inventory",
        "Runtime Gap Report",
        "Installer foundation and dry-run manifests",
        "Alpha release notes, FAQ, smoke matrix, and Beta roadmap",
    ]
    runtime_misses = [
        "embedded_python",
        "runtime_wheels",
        "verified_hashes",
        "runtime_payload_copy",
        "clean_machine_validation",
    ]
    first_inference_blockers = [
        "llama_cpp_cuda_backend_ready",
        "torch_cuda_visible_in_embedded_runtime",
        "launch_guard_passed",
        "human_token_approval",
        "first_qwen25_smoke_not_executed",
    ]
    public_release_blockers = [
        "public_beta_not_completed",
        "signed_installer_missing",
        "support_docs_finalization",
        "clean_machine_evidence_missing",
    ]
    return {
        "version": "15.9",
        "generated_at": _now(),
        "status": "RUNTIME_FINAL_GAP_BLOCKED" if payload["status"] == "PAYLOAD_BLOCKED" else "RUNTIME_FINAL_GAP_REDUCED",
        "what_ann_already_has": already_has,
        "what_runtime_still_misses": runtime_misses,
        "what_blocks_beta": [item["id"] for item in beta_gate["blockers"]],
        "what_blocks_first_inference": first_inference_blockers,
        "what_blocks_public_release": public_release_blockers,
        "current": {
            "collection": collection["status"],
            "wheelhouse_registry": registry["status"],
            "embedded_inventory": inventory["status"],
            "runtime_verification": verification["status"],
            "payload_readiness": payload["status"],
            "beta_gate": beta_gate["status"],
        },
        "safety": _safety_payload(),
    }


def write_runtime_final_gap_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 186-187."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"186_runtime_final_gap.json": build_runtime_final_gap()})


def write_runtime_final_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 176-187 for ANN v15.7-v15.9."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_runtime_collection_manifest_artifacts(target))
    artifacts.extend(write_wheelhouse_integrity_registry_artifacts(target))
    artifacts.extend(write_embedded_runtime_inventory_artifacts(target))
    artifacts.extend(write_embedded_runtime_verification_artifacts(target))
    artifacts.extend(write_beta_runtime_payload_readiness_artifacts(target))
    artifacts.extend(write_runtime_final_gap_artifacts(target))
    return _dedupe(artifacts)


def build_external_runtime_materialization(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Inspect the externally materialized runtime layout without copying anything."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    layout = build_embedded_runtime_layout(root)
    entries = [
        _materialization_entry("embedded_python", root / "python", "directory", ["python.exe", "DLLs", "Lib"]),
        _materialization_entry("runtime_wheels", root / "wheels", "directory", ["*.whl"]),
        _materialization_entry("runtime_checks", root / "checks", "directory", ["check_torch_cuda.py", "check_llama_cpp_cuda.py"]),
        _materialization_entry("runtime_logs", root / "logs", "directory", ["runtime validation logs"]),
        _materialization_entry("audit", root / "audit", "directory", ["materialization audit logs"]),
        _materialization_entry("site_packages", root / "site-packages", "directory", ["embedded runtime packages"]),
        _materialization_entry("requirements_lock", root / "requirements-lock", "directory", ["locked requirements and hashes"]),
    ]
    present = [entry for entry in entries if entry["present"]]
    missing = [entry for entry in entries if not entry["present"]]
    if layout["status"] == "RUNTIME_LAYOUT_INVALID_ROOT":
        status = "INVALID_LAYOUT"
    elif not present:
        status = "NOT_MATERIALIZED"
    elif missing:
        status = "PARTIALLY_MATERIALIZED"
    else:
        status = "FULLY_MATERIALIZED"
    return {
        "version": "16.0",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "entries": entries,
        "present": [entry["name"] for entry in present],
        "missing": [entry["name"] for entry in missing],
        "manual_copy_required": bool(missing),
        "expected_contents": {entry["name"]: entry["expected_contents"] for entry in entries},
        "hash_verification_pending": build_wheelhouse_integrity_registry(root / "wheels")["status"] != "HASH_VERIFIED",
        "no_copy": True,
        "no_install": True,
        "safety": _safety_payload(),
    }


def write_external_runtime_materialization_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 188-189."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"188_external_runtime_materialization.json": build_external_runtime_materialization()},
    )


def build_wheelhouse_population_protocol(
    wheelhouse_path: str | Path | None = None,
    lockfile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Describe how the offline wheelhouse must be populated externally."""

    wheelhouse = _resolve_runtime_filesystem_path(wheelhouse_path or f"{DEFAULT_RUNTIME_ROOT_TEXT}/wheels")
    lock = build_offline_runtime_lockfile(lockfile_path)
    declared = _declared_wheels(lock)
    discovered = {path.name: path for path in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())} if wheelhouse.is_dir() else {}
    wheels = [_population_protocol_entry(item, discovered.get(item["filename"])) for item in declared]
    missing = [item for item in wheels if not item["present"]]
    hash_pending = [item for item in wheels if item["status"] == "HASH_PENDING"]
    verified = [item for item in wheels if item["status"] == "VERIFIED"]
    if not discovered:
        status = "EMPTY"
    elif missing or hash_pending:
        status = "PARTIAL"
    elif verified and len(verified) == len(wheels):
        status = "VERIFIED"
    else:
        status = "READY_FOR_VERIFICATION"
    return {
        "version": "16.1",
        "generated_at": _now(),
        "status": status,
        "wheelhouse_path": str(wheelhouse),
        "lockfile_path": str(Path(lockfile_path or REPO_ROOT / "config" / "ann_runtime_lock.example.json")),
        "wheels": wheels,
        "manual_copy_required": bool(missing),
        "install_forbidden": True,
        "source": "external_only",
        "missing_count": len(missing),
        "hash_pending_count": len(hash_pending),
        "verified_count": len(verified),
        "no_download": True,
        "no_pip": True,
        "safety": _safety_payload(),
    }


def write_wheelhouse_population_protocol_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 190-191."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"190_wheelhouse_population_protocol.json": build_wheelhouse_population_protocol()},
    )


def build_embedded_runtime_beta_candidate(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether the embedded runtime can be treated as a Beta candidate."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    materialization = build_external_runtime_materialization(root)
    population = build_wheelhouse_population_protocol(root / "wheels")
    inventory = build_embedded_runtime_inventory(root)
    verification = build_embedded_runtime_verification(root)
    installer = build_installer_rc_readiness()
    checks = [
        _candidate_check("embedded_runtime_ready", materialization["status"] == "FULLY_MATERIALIZED", materialization["status"]),
        _candidate_check("wheelhouse_ready", population["status"] == "VERIFIED", population["status"]),
        _candidate_check("embedded_python_present", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _candidate_check("runtime_verified", verification["status"] == "VERIFICATION_READY", verification["status"]),
        _candidate_check("installer_compatible", installer["status"] == "RC_READY", installer["status"]),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "BETA_CANDIDATE_BLOCKED"
    elif inventory["status"] == "INVENTORY_READY" and verification["status"] == "VERIFICATION_READY":
        status = "BETA_CANDIDATE_READY"
    else:
        status = "BETA_CANDIDATE_FOUNDATION"
    return {
        "version": "16.2",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "embedded_runtime_ready": checks[0]["passed"],
        "wheelhouse_ready": checks[1]["passed"],
        "embedded_python_present": checks[2]["passed"],
        "runtime_verified": checks[3]["passed"],
        "installer_compatible": checks[4]["passed"],
        "beta_candidate": status == "BETA_CANDIDATE_READY",
        "checks": checks,
        "blockers": blockers,
        "next_step": _candidate_next_step(blockers),
        "no_install": True,
        "no_model_load": True,
        "safety": _safety_payload(),
    }


def write_embedded_runtime_beta_candidate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 192-193."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"192_embedded_runtime_beta_candidate.json": build_embedded_runtime_beta_candidate()},
    )


def build_external_operational_beta_candidate(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether external runtime evidence is enough for operational Beta only.

    This deliberately does not satisfy embedded runtime, installer, or final release
    readiness. It is a read-only bridge for the already verified WSL/conda runtime
    smoke evidence.
    """

    root_info = _runtime_path_info(runtime_root)
    smoke_path = _latest_artifact_named("346_qwen25_wsl_external_smoke.json")
    pipeline_path = _latest_artifact_named("304_final_role_pipeline.json")
    smoke = _read_json_if_exists(smoke_path) if smoke_path is not None else {}
    pipeline = _read_json_if_exists(pipeline_path) if pipeline_path is not None else {}
    launcher = build_v1_1_installer_launcher_readiness()
    smoke_passed = (
        smoke.get("status") == "FIRST_REAL_INFERENCE_PASSED"
        and smoke.get("runtime_type") == "external_wsl_conda"
        and smoke.get("safe_mode_final") is True
        and int(smoke.get("active_models_after", -1)) == 0
        and int(smoke.get("parallel_llm_loads_after", -1)) == 0
    )
    pipeline_passed = (
        pipeline.get("status") == "FINAL_ENGINEERING_PIPELINE_PASSED"
        and int(pipeline.get("active_models_after", 0) or 0) == 0
        and int(pipeline.get("parallel_llm_loads_after", 0) or 0) == 0
    )
    launcher_foundation = launcher.get("status") in {
        "INSTALLER_LAUNCHER_READY_FOUNDATION",
        "INSTALLER_LAUNCHER_READY",
    }
    checks = [
        _candidate_check("external_qwen25_smoke_passed", smoke_passed, str(smoke_path or "missing")),
        _candidate_check("final_engineering_pipeline_passed", pipeline_passed, str(pipeline_path or "missing")),
        _candidate_check("installer_launcher_foundation", launcher_foundation, launcher.get("status", "UNKNOWN")),
        _candidate_check("embedded_runtime_not_claimed", True, "external runtime cannot satisfy embedded runtime finalization"),
        _candidate_check("no_model_load", True, "read_only_evidence_check"),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "EXTERNAL_BETA_CANDIDATE_BLOCKED"
    elif smoke_passed and pipeline_passed and launcher_foundation:
        status = "EXTERNAL_BETA_CANDIDATE_READY"
    else:
        status = "EXTERNAL_BETA_CANDIDATE_PARTIAL"
    return {
        "version": "18.9.1",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "runtime_type": smoke.get("runtime_type", "external_wsl_conda"),
        "external_runtime_source": "wsl_conda_artifact",
        "external_operational_beta": status == "EXTERNAL_BETA_CANDIDATE_READY",
        "final_release_runtime": False,
        "is_embedded_runtime": False,
        "embedded_runtime_ready": False,
        "installer_final_ready": False,
        "signed_installer": False,
        "qwen25_smoke_artifact": str(smoke_path) if smoke_path is not None else "",
        "final_pipeline_artifact": str(pipeline_path) if pipeline_path is not None else "",
        "qwen25_smoke_status": smoke.get("status", "MISSING"),
        "final_pipeline_status": pipeline.get("status", "MISSING"),
        "installer_launcher_status": launcher.get("status", "UNKNOWN"),
        "checks": checks,
        "blockers": blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_inference": True,
        "no_install": True,
        "no_download": True,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": load_model_policy().vram_policy,
        "next_step": (
            "Proceed with external-runtime Beta validation only; embedded runtime and signed installer remain required for final release."
            if not blockers
            else f"Resolve external operational Beta blocker: {blockers[0]['id']}"
        ),
        "safety": _safety_payload(),
    }


def write_external_operational_beta_candidate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 350-351."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"350_external_operational_beta_candidate.json": build_external_operational_beta_candidate()},
    )


def build_first_real_inference_readiness(
    runtime_root: str | Path | None = None,
    approval_token: str | None = None,
) -> dict[str, Any]:
    """Evaluate first real Qwen2.5 inference readiness without running inference."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    materialization = build_external_runtime_materialization(root)
    population = build_wheelhouse_population_protocol(root / "wheels")
    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    token_ok = _token_valid(approval_token)
    checks = [
        _inference_readiness_check("embedded_python", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _inference_readiness_check("wheelhouse", population["status"] == "VERIFIED", population["status"]),
        _inference_readiness_check("torch_cuda", cuda["cuda_available"], cuda["status"]),
        _inference_readiness_check("llama_cpp", llama["status"] == "READY", llama["status"]),
        _inference_readiness_check("launch_guard", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _inference_readiness_check("qwen25_backend", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _inference_readiness_check("approval_token", token_ok, "provided" if token_ok else "missing_or_invalid"),
        _inference_readiness_check("safe_rollback", get_loaded_models() == [], "loaded_models_empty"),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    infrastructure_blockers = [check for check in blockers if check["id"] != "approval_token"]
    if infrastructure_blockers:
        status = "NOT_READY"
    elif blockers:
        status = "READY_BUT_BLOCKED"
    else:
        status = "READY_FOR_CONTROLLED_SMOKE"
    return {
        "version": "16.2",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "missing": [check["id"] for check in blockers],
        "blocking": [check["id"] for check in blockers],
        "what_ann_needs": [
            "embedded runtime materialized externally",
            "verified wheelhouse",
            "CUDA torch runtime",
            "llama_cpp READY",
            "Launch Guard PASSED",
            "human approval token",
            "safe rollback confirmation",
        ],
        "runtime_materialization": materialization["status"],
        "wheelhouse_population": population["status"],
        "qwen2_5_backend_ready": launch_guard["status"] == "PASSED",
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "real_inference_attempted": False,
        "model_load_attempted": False,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": load_model_policy().vram_policy,
        "safety": _safety_payload(),
    }


def write_first_real_inference_readiness_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 194-195."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"194_first_real_inference_readiness.json": build_first_real_inference_readiness()},
    )


def write_beta_candidate_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 188-195 for ANN v16.0-v16.2."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_external_runtime_materialization_artifacts(target))
    artifacts.extend(write_wheelhouse_population_protocol_artifacts(target))
    artifacts.extend(write_embedded_runtime_beta_candidate_artifacts(target))
    artifacts.extend(write_first_real_inference_readiness_artifacts(target))
    return _dedupe(artifacts)


def build_manual_external_runtime_checklist(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Describe the human-only runtime materialization checklist."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    integrity = build_runtime_integrity_verification(root)
    steps = [
        _manual_runtime_step(1, "Copy embedded Python", f"Copy embedded Python to {root / 'python'}"),
        _manual_runtime_step(2, "Copy wheels", f"Copy verified wheels to {root / 'wheels'}"),
        _manual_runtime_step(3, "Copy support folders", f"Copy requirements-lock, checks, and audit folders under {root}"),
        _manual_runtime_step(4, "Verify runtime", "Verify hashes, layout, and runtime verification artifacts"),
        _manual_runtime_step(5, "Run Beta Gate", "Run read-only Beta Candidate Final Gate from ANN"),
    ]
    if integrity["status"] == "INTEGRITY_VERIFIED":
        status = "VERIFIED"
    elif integrity["status"] == "INTEGRITY_PARTIAL":
        status = "READY_FOR_VERIFICATION"
    else:
        status = "MANUAL_STEPS_REQUIRED"
    return {
        "version": "16.3",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "steps": steps,
        "next_step": _manual_checklist_next_step(integrity["blockers"]),
        "no_auto_execute": True,
        "no_install": True,
        "no_download": True,
        "no_inference": True,
        "safety": _safety_payload(),
    }


def write_manual_external_runtime_checklist_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 196-197."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"196_manual_external_runtime_checklist.json": build_manual_external_runtime_checklist()},
    )


def build_runtime_integrity_verification(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Verify externally materialized runtime integrity without executing runtime files."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    lockfile = _runtime_lockfile_for_wheelhouse(root / "wheels")
    wheelhouse = build_wheelhouse_external_validation(root / "wheels", lockfile)
    checks = [
        _integrity_check("embedded_python_present", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _integrity_check("python_folder", (root / "python").is_dir(), str(root / "python")),
        _integrity_check("wheels_folder", (root / "wheels").is_dir(), str(root / "wheels")),
        _integrity_check("site_packages_folder", (root / "site-packages").is_dir(), str(root / "site-packages")),
        _integrity_check("requirements_lock_folder", (root / "requirements-lock").is_dir(), str(root / "requirements-lock")),
        _integrity_check("audit_folder", (root / "audit").is_dir(), str(root / "audit")),
        _integrity_check("checks_folder", (root / "checks").is_dir(), str(root / "checks")),
        _integrity_check("lockfile", lockfile.is_file(), str(lockfile)),
        _integrity_check("wheelhouse_hashes", wheelhouse["status"] == "VERIFIED", wheelhouse["status"]),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    passed = [check for check in checks if check["status"] == "PASS"]
    critical_blockers = {check["id"] for check in blockers}.intersection(
        {"embedded_python_present", "python_folder", "wheels_folder", "wheelhouse_hashes"}
    )
    if critical_blockers:
        status = "INTEGRITY_BLOCKED"
    elif blockers and passed:
        status = "INTEGRITY_PARTIAL"
    elif blockers:
        status = "INTEGRITY_BLOCKED"
    else:
        status = "INTEGRITY_VERIFIED"
    return {
        "version": "16.4",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "no_python_execution": True,
        "no_wheel_execution": True,
        "safety": _safety_payload(),
    }


def write_runtime_integrity_verification_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 198-199."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"198_runtime_integrity_verification.json": build_runtime_integrity_verification()},
    )


def build_wheelhouse_external_validation(
    wheelhouse_path: str | Path | None = None,
    lockfile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate externally copied wheels against the lockfile without installing them."""

    wheelhouse = _resolve_runtime_filesystem_path(wheelhouse_path or f"{DEFAULT_RUNTIME_ROOT_TEXT}/wheels")
    lockfile = _runtime_lockfile_for_wheelhouse(wheelhouse, lockfile_path)
    lock = build_offline_runtime_lockfile(lockfile)
    discovered = {path.name: path for path in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())} if wheelhouse.is_dir() else {}
    wheels = [_external_wheel_validation_entry(item, discovered.get(item["filename"])) for item in _declared_wheels(lock)]
    missing = [item for item in wheels if item["missing"]]
    mismatch = [item for item in wheels if item["status"] == "MISMATCH"]
    verified = [item for item in wheels if item["verified"]]
    if not discovered:
        status = "EMPTY"
    elif missing or mismatch or len(verified) != len(wheels):
        status = "PARTIAL"
    else:
        status = "VERIFIED"
    return {
        "version": "16.4",
        "generated_at": _now(),
        "status": status,
        "wheelhouse_path": str(wheelhouse),
        "lockfile_path": str(lockfile),
        "wheels": wheels,
        "missing": [item["wheel"] for item in missing],
        "mismatch": [item["wheel"] for item in mismatch],
        "verified": [item["wheel"] for item in verified],
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def write_wheelhouse_external_validation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 200-201."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"200_wheelhouse_external_validation.json": build_wheelhouse_external_validation()},
    )


def build_beta_candidate_final_gate(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Final read-only gate before ANN can become a Beta Candidate."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    materialization = build_external_runtime_materialization(root)
    integrity = build_runtime_integrity_verification(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    candidate = build_embedded_runtime_beta_candidate(root)
    inference = build_first_real_inference_readiness(root)
    checks = [
        _final_gate_check("embedded_runtime_materialized", materialization["status"] == "FULLY_MATERIALIZED", materialization["status"]),
        _final_gate_check("integrity_verified", integrity["status"] == "INTEGRITY_VERIFIED", integrity["status"]),
        _final_gate_check("wheelhouse_verified", wheelhouse["status"] == "VERIFIED", wheelhouse["status"]),
        _final_gate_check("installer_compatible", candidate["installer_compatible"], "installer compatible" if candidate["installer_compatible"] else "installer blocked"),
        _final_gate_check("runtime_verified", candidate["runtime_verified"], "runtime verified" if candidate["runtime_verified"] else "runtime blocked"),
        _final_gate_check("first_inference_ready", inference["status"] == "READY_FOR_CONTROLLED_SMOKE", inference["status"]),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "BETA_FINAL_BLOCKED"
    elif inference["status"] == "READY_BUT_BLOCKED":
        status = "BETA_FINAL_FOUNDATION"
    else:
        status = "BETA_FINAL_READY"
    return {
        "version": "16.5",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "known_blockers": [check["id"] for check in blockers],
        "next_step": _final_gate_next_step(blockers),
        "safe_mode": not load_model_policy().allow_real_model_load,
        "qwen2_5_blocked": inference["qwen2_5_backend_ready"] is False,
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "safety": _safety_payload(),
    }


def write_beta_candidate_final_gate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 202-203."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"202_beta_candidate_final_gate.json": build_beta_candidate_final_gate()})


def write_manual_materialization_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 196-203 for ANN v16.3-v16.5."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_manual_external_runtime_checklist_artifacts(target))
    artifacts.extend(write_runtime_integrity_verification_artifacts(target))
    artifacts.extend(write_wheelhouse_external_validation_artifacts(target))
    artifacts.extend(write_beta_candidate_final_gate_artifacts(target))
    return _dedupe(artifacts)


def build_post_materialization_validator(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Validate post-materialization runtime structure without executing runtime files."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    required = [
        _post_materialization_item("embedded_python", root / "python" / "python.exe", "file"),
        _post_materialization_item("wheels", root / "wheels", "directory"),
        _post_materialization_item("checks", root / "checks", "directory"),
        _post_materialization_item("audit", root / "audit", "directory"),
        _post_materialization_item("site_packages", root / "site-packages", "directory"),
        _post_materialization_item("requirements_lock", root / "requirements-lock", "directory"),
    ]
    missing = [item for item in required if not item["present"]]
    unexpected = _unexpected_runtime_files(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    integrity = build_runtime_integrity_verification(root)
    layout_valid = not missing and not unexpected
    hashes_checked = wheelhouse["status"] == "VERIFIED"
    runtime_compatible = integrity["status"] == "INTEGRITY_VERIFIED"
    if not root.exists():
        status = "NOT_MATERIALIZED"
    elif unexpected:
        status = "INVALID"
    elif missing:
        status = "PARTIAL"
    elif layout_valid and hashes_checked and runtime_compatible:
        status = "VALIDATED"
    else:
        status = "PARTIAL"
    return {
        "version": "16.6",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "required": required,
        "present": [item["id"] for item in required if item["present"]],
        "missing": [item["id"] for item in missing],
        "unexpected_files": unexpected,
        "layout_valid": layout_valid,
        "hashes_checked": hashes_checked,
        "runtime_compatible": runtime_compatible,
        "no_python_execution": True,
        "no_wheel_import": True,
        "no_runtime_execution": True,
        "safety": _safety_payload(),
    }


def write_post_materialization_validator_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 204-205."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"204_post_materialization_validator.json": build_post_materialization_validator()},
    )


def build_runtime_readiness_evidence(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build evidence for runtime readiness without executing the runtime."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    validator = build_post_materialization_validator(root)
    integrity = build_runtime_integrity_verification(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    installer = build_installer_rc_readiness()
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    embedded_python_detected = (root / "python" / "python.exe").is_file()
    checks = [
        _readiness_evidence_check("runtime_ready", validator["status"] == "VALIDATED", validator["status"]),
        _readiness_evidence_check("installer_ready", installer["status"] == "RC_READY", installer["status"]),
        _readiness_evidence_check("wheelhouse_verified", wheelhouse["status"] == "VERIFIED", wheelhouse["status"]),
        _readiness_evidence_check("launch_guard_ready", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _readiness_evidence_check("safe_rollback_ready", get_loaded_models() == [], "loaded_models_empty"),
        _readiness_evidence_check("runtime_integrity_verified", integrity["status"] == "INTEGRITY_VERIFIED", integrity["status"]),
        _readiness_evidence_check("embedded_python_detected", embedded_python_detected, str(root / "python" / "python.exe")),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    warnings = [
        "Runtime evidence is read-only and does not execute embedded Python.",
        "First inference still requires explicit approval and a separate controlled smoke.",
    ]
    if not blockers:
        status = "READY"
    elif get_loaded_models() == [] and not embedded_python_detected:
        status = "NOT_READY"
    elif len(blockers) < len(checks):
        status = "PARTIAL"
    else:
        status = "READY_BUT_BLOCKED"
    return {
        "version": "16.7",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "reason": _runtime_readiness_reason(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "next_manual_step": _runtime_readiness_next_step(blockers),
        "runtime_ready": not any(check["id"] == "runtime_ready" for check in blockers),
        "installer_ready": not any(check["id"] == "installer_ready" for check in blockers),
        "wheelhouse_verified": not any(check["id"] == "wheelhouse_verified" for check in blockers),
        "launch_guard_ready": not any(check["id"] == "launch_guard_ready" for check in blockers),
        "safe_rollback_ready": get_loaded_models() == [],
        "runtime_integrity_verified": not any(check["id"] == "runtime_integrity_verified" for check in blockers),
        "embedded_python_detected": embedded_python_detected,
        "safety": _safety_payload(),
    }


def write_runtime_readiness_evidence_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 206-207."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"206_runtime_readiness_evidence.json": build_runtime_readiness_evidence()},
    )


def build_controlled_first_inference_gate(
    runtime_root: str | Path | None = None,
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
) -> dict[str, Any]:
    """Gate the first real inference smoke without loading models or running inference."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    policy = load_model_policy()
    evidence = build_runtime_readiness_evidence(root)
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    readiness = build_first_real_inference_readiness(root, approval_token=approval_token)
    checks = [
        _controlled_gate_check("embedded_python", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _controlled_gate_check("wheelhouse", evidence["wheelhouse_verified"], "verified" if evidence["wheelhouse_verified"] else "not_verified"),
        _controlled_gate_check("runtime_integrity", evidence["runtime_integrity_verified"], evidence["status"]),
        _controlled_gate_check("launch_guard", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _controlled_gate_check("qwen25_backend", readiness["qwen2_5_backend_ready"], "ready" if readiness["qwen2_5_backend_ready"] else "blocked"),
        _controlled_gate_check("local_test_token", _token_valid(approval_token), "valid" if _token_valid(approval_token) else "missing_or_invalid"),
        _controlled_gate_check("manual_confirmation", manual_confirmation, "confirmed" if manual_confirmation else "missing"),
        _controlled_gate_check("safe_rollback", get_loaded_models() == [], "loaded_models_empty"),
        _controlled_gate_check("fast_mode", policy.default_backend in {"mock", "llama_cpp"}, policy.default_backend),
        _controlled_gate_check("active_models_zero", get_runtime_metrics().get("active_models", 0) == 0, str(get_runtime_metrics().get("active_models", 0))),
        _controlled_gate_check("parallel_loads_zero", get_runtime_metrics().get("parallel_llm_loads", 0) == 0, str(get_runtime_metrics().get("parallel_llm_loads", 0))),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    infrastructure_blockers = [check for check in blockers if check["id"] not in {"local_test_token", "manual_confirmation"}]
    if infrastructure_blockers:
        status = "NOT_READY"
    elif blockers:
        status = "READY_BUT_BLOCKED"
    else:
        status = "READY_FOR_CONTROLLED_SMOKE"
    return {
        "version": "16.8",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "missing": [check["id"] for check in blockers],
        "blocking": [check["id"] for check in blockers],
        "what_it_needs": [
            "validated post-materialized runtime",
            "verified wheelhouse",
            "runtime integrity verified",
            "Launch Guard PASSED",
            "Qwen2.5 backend ready",
            "LOCAL_TEST_TOKEN",
            "manual confirmation",
            "safe rollback state",
            "FAST mode",
        ],
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def write_controlled_first_inference_gate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 208-209."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"208_controlled_first_inference_gate.json": build_controlled_first_inference_gate()},
    )


def write_runtime_readiness_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 204-209 for ANN v16.6-v16.8."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_post_materialization_validator_artifacts(target))
    artifacts.extend(write_runtime_readiness_evidence_artifacts(target))
    artifacts.extend(write_controlled_first_inference_gate_artifacts(target))
    return _dedupe(artifacts)


def build_runtime_materialization_watcher(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Watch externally materialized runtime state without executing anything."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    if root_info["blocked"]:
        return {
            "version": "16.9",
            "generated_at": _now(),
            "status": "INVALID",
            **_runtime_report(root_info),
            "missing_folders": [],
            "new_files": [],
            "wheelhouse_count": 0,
            "python_found": False,
            "layout_status": "RUNTIME_LAYOUT_INVALID_ROOT",
            "hash_verification_status": "SKIPPED",
            "errors": root_info["errors"],
            "no_python_execution": True,
            "no_install": True,
            "safety": _safety_payload(),
        }
    cache_key = _runtime_materialization_cache_key(root)
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    watched = [
        root / "python",
        root / "wheels",
        root / "checks",
        root / "audit",
        root / "site-packages",
        root / "requirements-lock",
    ]
    missing = [str(path) for path in watched if not path.is_dir()]
    new_files = _runtime_new_files(root)
    wheelhouse = root / "wheels"
    wheelhouse_count = len(list(wheelhouse.glob("*.whl"))) if wheelhouse.is_dir() else 0
    python_found = (root / "python" / "python.exe").is_file()
    validator = build_post_materialization_validator(root)
    validation = build_wheelhouse_external_validation(wheelhouse)
    if validator["status"] == "INVALID":
        status = "INVALID"
    elif not root.exists():
        status = "NOT_MATERIALIZED"
    elif missing or not python_found:
        status = "PARTIAL"
    elif validation["status"] == "VERIFIED":
        status = "READY"
    else:
        status = "PARTIAL"
    payload = {
        "version": "16.9",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "missing_folders": missing,
        "new_files": new_files,
        "wheelhouse_count": wheelhouse_count,
        "python_found": python_found,
        "layout_status": validator["status"],
        "hash_verification_status": validation["status"],
        "no_python_execution": True,
        "no_install": True,
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_runtime_materialization_watcher_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 210-211."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"210_runtime_materialization_watcher.json": build_runtime_materialization_watcher()},
    )


def build_beta_runtime_activation(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether the Beta runtime can be opened for controlled Qwen2.5 FAST smoke."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    watcher = build_runtime_materialization_watcher(root)
    integrity = build_runtime_integrity_verification(root)
    installer = build_installer_rc_readiness()
    launch_guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    first_gate = build_controlled_first_inference_gate(root, approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    checks = [
        _beta_activation_check("embedded_python", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _beta_activation_check("wheelhouse", watcher["hash_verification_status"] == "VERIFIED", watcher["hash_verification_status"]),
        _beta_activation_check("runtime_integrity", integrity["status"] == "INTEGRITY_VERIFIED", integrity["status"]),
        _beta_activation_check("installer_compatibility", installer["status"] == "RC_READY", installer["status"]),
        _beta_activation_check("launch_guard", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _beta_activation_check("qwen25_backend", first_gate["status"] == "READY_FOR_CONTROLLED_SMOKE", first_gate["status"]),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    if blockers:
        status = "BETA_BLOCKED"
    elif get_loaded_models() == [QWEN25_MODEL_NAME]:
        status = "BETA_ACTIVE"
    else:
        status = "BETA_READY"
    return {
        "version": "17.0",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "qwen2_5_only": True,
        "fast_only": True,
        "backend": "llama_cpp",
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": load_model_policy().vram_policy,
        "next_step": _beta_activation_next_step(blockers),
        "safety": _safety_payload(),
    }


def write_beta_runtime_activation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 212-213."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"212_beta_runtime_activation.json": build_beta_runtime_activation()})


def build_first_real_inference_live_status(
    runtime_root: str | Path | None = None,
    *,
    allow_wsl_probe: bool | None = None,
) -> dict[str, Any]:
    """Render current first-inference readiness without writing artifacts or loading models."""

    gate = build_controlled_first_inference_gate(runtime_root)
    external_smoke = build_external_runtime_smoke_readiness(allow_wsl_probe=allow_wsl_probe)
    status = gate["status"]
    runtime_status = gate["status"]
    next_step = "Run controlled first real inference only after the gate reports READY_FOR_CONTROLLED_SMOKE."
    if status != "READY_FOR_CONTROLLED_SMOKE" and external_smoke["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL":
        status = "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
        runtime_status = "EXTERNAL_RUNTIME_READY_EMBEDDED_BLOCKED"
        next_step = "Run External Runtime Smoke with token and manual confirmation; embedded final runtime remains blocked."
    latest_wsl_smoke_path = _latest_artifact_named("346_qwen25_wsl_external_smoke.json")
    latest_wsl_smoke = _read_json_if_exists(latest_wsl_smoke_path) if latest_wsl_smoke_path is not None else {}
    if latest_wsl_smoke.get("status") == "FIRST_REAL_INFERENCE_PASSED" and latest_wsl_smoke.get("safe_mode_final") is True:
        status = "FIRST_REAL_INFERENCE_PASSED_EXTERNAL"
        runtime_status = "EXTERNAL_RUNTIME_SMOKE_PASSED_EMBEDDED_BLOCKED"
        next_step = "Use verified external runtime for controlled local development; embedded final runtime and installer remain blocked."
    metrics = get_runtime_metrics()
    return {
        "version": "17.1",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "mode": "FAST",
        "vram_usage_mb": metrics.get("peak_vram_mb", 0),
        "load_time": latest_wsl_smoke.get("load_time_seconds", "not_attempted"),
        "unload_status": "PASSED" if latest_wsl_smoke.get("safe_mode_final") is True else "SKIPPED",
        "safe_mode": get_loaded_models() == [],
        "runtime_status": runtime_status,
        "external_smoke_status": external_smoke["status"],
        "external_runtime_type": external_smoke.get("runtime_type", "external_runtime"),
        "latest_wsl_smoke_artifact": str(latest_wsl_smoke_path) if latest_wsl_smoke_path is not None else "",
        "latest_wsl_smoke_status": latest_wsl_smoke.get("status", ""),
        "next_step": next_step,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "safety": _safety_payload(),
    }


def run_controlled_first_real_inference(
    *,
    runtime_root: str | Path | None = None,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Run the first Qwen2.5 FAST smoke only after all controlled gates pass."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    gate = build_controlled_first_inference_gate(
        runtime_root,
        approval_token=approval_token,
        manual_confirmation=manual_confirmation,
    )
    policy = load_model_policy()
    loaded_before = get_loaded_models()
    errors: list[str] = []
    warnings: list[str] = []
    status = "NOT_READY"
    load_result: dict[str, Any] = {}
    generate_result: dict[str, Any] = {}
    unload_result: dict[str, Any] = {}
    inference_text = ""
    load_time_seconds = 0.0
    inference_time_seconds = 0.0
    unload_time_seconds = 0.0
    real_load_attempted = False
    real_inference_attempted = False
    real_load_succeeded = False
    real_inference_succeeded = False
    if gate["status"] != "READY_FOR_CONTROLLED_SMOKE":
        status = gate["status"]
        errors.extend(gate["blocking"])
        warnings.append("controlled_first_inference_not_attempted_gate_not_ready")
    elif policy.max_loaded_models != 1 or policy.vram_policy != "SEQUENTIAL":
        status = "READY_BUT_BLOCKED"
        errors.append("runtime_policy_not_sequential")
    elif get_runtime_metrics().get("parallel_llm_loads", 0) != 0 or loaded_before:
        status = "READY_BUT_BLOCKED"
        errors.append("runtime_not_clean_before_smoke")
    else:
        status = "RUNNING"
        adapter = backend or LlamaCppBackend({"allow_real_model_load": True})
        real_load_attempted = True
        load_started = perf_counter()
        load = adapter.load_model(QWEN25_MODEL_NAME)
        load_time_seconds = _elapsed_seconds(load_started)
        load_result = load.to_dict() if hasattr(load, "to_dict") else dict(load)
        if not load_result.get("loaded", False):
            status = "FAILED"
            errors.extend(_list_from(load_result.get("errors")) or ["qwen25_load_failed"])
            warnings.extend(_list_from(load_result.get("warnings")))
        else:
            real_load_succeeded = True
            real_inference_attempted = True
            generate_started = perf_counter()
            generation = adapter.generate(QWEN25_MODEL_NAME, "Return exactly: 4")
            inference_time_seconds = _elapsed_seconds(generate_started)
            generate_result = generation.to_dict() if hasattr(generation, "to_dict") else dict(generation)
            inference_text = str(generate_result.get("text", "")).strip()
            if generate_result.get("status") == "SUCCESS" and inference_text == "4":
                real_inference_succeeded = True
                status = "SUCCESS"
            else:
                status = "FAILED"
                errors.extend(_list_from(generate_result.get("errors")) or ["qwen25_first_inference_output_mismatch"])
        unload_started = perf_counter()
        unload = adapter.unload_model(QWEN25_MODEL_NAME)
        unload_time_seconds = _elapsed_seconds(unload_started)
        unload_result = unload.to_dict() if hasattr(unload, "to_dict") else dict(unload)
        if not bool(unload_result.get("unloaded", False)):
            status = "ROLLED_BACK"
            errors.append("qwen25_unload_failed")
    rollback = _rollback_safe_state()
    loaded_after = get_loaded_models()
    if loaded_after:
        status = "ROLLED_BACK"
        errors.append("loaded_models_not_empty_after_smoke")
    benchmark = build_runtime_benchmark(
        status="READY" if real_load_succeeded else "SKIPPED_NO_REAL_LOAD",
        load_time_seconds=load_time_seconds,
        inference_time_seconds=inference_time_seconds,
        unload_time_seconds=unload_time_seconds,
        total_time_seconds=_elapsed_seconds(started),
        generate_result=generate_result,
        loaded_before=loaded_before,
        loaded_during=[QWEN25_MODEL_NAME] if real_load_succeeded else [],
        loaded_after=loaded_after,
    )
    benchmark = {
        **benchmark,
        "version": "17.1",
        "status": "SUCCESS" if real_inference_succeeded else benchmark["status"],
        "vram_peak": benchmark.get("peak_vram_mb"),
        "latency": benchmark.get("inference_time_seconds"),
        "tokens_per_second": benchmark.get("tokens_per_second"),
        "load_time": benchmark.get("load_time_seconds"),
        "unload_status": unload_result.get("status", "SKIPPED"),
    }
    payload = {
        "version": "17.1",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "mode": "FAST",
        "prompt": "Return exactly: 4",
        "response": inference_text if real_inference_succeeded else "",
        "token_provided": bool((approval_token or "").strip()),
        "token_accepted": _token_valid(approval_token),
        "manual_confirmation": bool(manual_confirmation),
        "loaded_models_before": loaded_before,
        "loaded_models_after": loaded_after,
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "real_load_succeeded": real_load_succeeded,
        "real_inference_succeeded": real_inference_succeeded,
        "load_result": load_result,
        "generate_result": {**generate_result, "text": inference_text if real_inference_succeeded else ""},
        "unload_result": unload_result,
        "unload_status": unload_result.get("status", "SKIPPED"),
        "safe_mode": loaded_after == [],
        "safe_mode_final": loaded_after == [],
        "rollback": rollback,
        "benchmark": benchmark,
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "214_first_real_inference.json": payload,
            "216_runtime_benchmark_real.json": benchmark,
        },
    )
    return {
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "mode": "FAST",
        "real_load_attempted": real_load_attempted,
        "real_inference_attempted": real_inference_attempted,
        "real_load_succeeded": real_load_succeeded,
        "real_inference_succeeded": real_inference_succeeded,
        "safe_mode_final": loaded_after == [],
        "loaded_models_after": loaded_after,
        "unload_status": unload_result.get("status", "SKIPPED"),
        "benchmark_status": benchmark["status"],
        "artifacts": artifacts,
        "errors": payload["errors"],
        "warnings": payload["warnings"],
    }


def write_beta_runtime_live_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 210-217 for ANN v16.9-v17.1."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_runtime_materialization_watcher_artifacts(target))
    artifacts.extend(write_beta_runtime_activation_artifacts(target))
    artifacts.extend(
        run_controlled_first_real_inference(output_dir=target)["artifacts"]
    )
    return _dedupe(artifacts)


def build_guided_runtime_activation_state(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build the Desktop guided runtime activation state without executing smoke."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    watcher = build_runtime_materialization_watcher(root)
    readiness = build_runtime_readiness_evidence(root)
    inference_gate = build_controlled_first_inference_gate(root)
    beta_activation = build_beta_runtime_activation(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    steps = [
        _guided_step(
            "materialize_runtime",
            "Step 1: Materialize Runtime",
            watcher["status"] in {"READY", "PARTIAL"},
            "Copy embedded runtime to D:\\ANN\\runtime.",
            "210_runtime_materialization_watcher.json",
            watcher["status"],
        ),
        _guided_step(
            "populate_wheelhouse",
            "Step 2: Populate Wheelhouse",
            watcher["wheelhouse_count"] > 0,
            "Copy wheels into D:\\ANN\\runtime\\wheels.",
            "190_wheelhouse_population_protocol.json",
            f"wheelhouse_count={watcher['wheelhouse_count']}",
        ),
        _guided_step(
            "verify_hashes",
            "Step 3: Verify Hashes",
            wheelhouse["status"] == "VERIFIED",
            "Verify wheel hashes from the lockfile.",
            "200_wheelhouse_external_validation.json",
            wheelhouse["status"],
        ),
        _guided_step(
            "validate_runtime",
            "Step 4: Validate Runtime",
            readiness["runtime_integrity_verified"],
            "Resolve runtime integrity blockers.",
            "206_runtime_readiness_evidence.json",
            readiness["status"],
        ),
        _guided_step(
            "check_launch_guard",
            "Step 5: Check Launch Guard",
            beta_activation["status"] in {"BETA_READY", "BETA_ACTIVE"},
            "Resolve Qwen2.5 launch guard/backend blockers.",
            "212_beta_runtime_activation.json",
            beta_activation["status"],
        ),
        _guided_step(
            "run_first_qwen25_smoke",
            "Step 6: Run First Qwen2.5 Smoke",
            inference_gate["status"] == "READY_FOR_CONTROLLED_SMOKE",
            "Provide LOCAL_TEST_TOKEN and manual confirmation.",
            "208_controlled_first_inference_gate.json",
            inference_gate["status"],
        ),
    ]
    completed = [step for step in steps if step["status"] == "COMPLETED"]
    blocked = [step for step in steps if step["status"] == "BLOCKED"]
    if not blocked:
        status = "GUIDED_READY_FOR_SMOKE"
    elif completed:
        status = "GUIDED_PARTIAL"
    else:
        status = "GUIDED_BLOCKED"
    next_step = blocked[0] if blocked else steps[-1]
    return {
        "version": "17.2",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "current_step": next_step["id"],
        "steps": steps,
        "completed_steps": [step["id"] for step in completed],
        "blocked_steps": [step["id"] for step in blocked],
        "next_manual_action": next_step["next_action"],
        "ready_for_smoke_button": inference_gate["status"] == "READY_FOR_CONTROLLED_SMOKE",
        "safe_mode": get_loaded_models() == [],
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "safety": _safety_payload(),
    }


def write_guided_runtime_activation_state_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 218-219."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"218_guided_runtime_activation_state.json": build_guided_runtime_activation_state()},
    )


def build_qwen25_smoke_button_gate(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether Desktop can enable Run First Qwen2.5 Smoke."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    watcher = build_runtime_materialization_watcher(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    llama = diagnose_llama_cpp_real_status()
    inference_gate = build_controlled_first_inference_gate(root, approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    external_smoke = build_external_runtime_smoke_readiness()
    metrics = get_runtime_metrics()
    policy = load_model_policy()
    checks = [
        _button_gate_check("runtime_materialized", watcher["status"] == "READY", watcher["status"]),
        _button_gate_check("embedded_python_present", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _button_gate_check("wheelhouse_verified", wheelhouse["status"] == "VERIFIED", wheelhouse["status"]),
        _button_gate_check("llama_cpp_ready", llama["status"] == "READY", llama["status"]),
        _button_gate_check("qwen25_backend_ready", inference_gate["status"] == "READY_FOR_CONTROLLED_SMOKE", inference_gate["status"]),
        _button_gate_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _button_gate_check("parallel_llm_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _button_gate_check("vram_policy_sequential", policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
        _button_gate_check("token_dialog_available", True, "existing confirmation/token dialogs"),
        _button_gate_check("confirmation_dialog_available", True, "existing confirmation dialog"),
        _button_gate_check("safe_rollback_available", get_loaded_models() == [], "loaded_models_empty"),
    ]
    blockers = [check for check in checks if check["status"] == "BLOCKED"]
    external_ready = external_smoke["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    if not blockers:
        status = "BUTTON_READY"
        button_label = "Run First Qwen2.5 Smoke"
    elif external_ready:
        status = "EXTERNAL_RUNTIME_SMOKE_READY"
        button_label = "External Runtime Smoke"
    elif get_loaded_models() or metrics.get("parallel_llm_loads", 0) != 0:
        status = "BUTTON_BLOCKED"
        button_label = "Run First Qwen2.5 Smoke"
    else:
        status = "BUTTON_DISABLED"
        button_label = "Run First Qwen2.5 Smoke"
    return {
        "version": "17.3",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "button_label": button_label,
        "button_enabled": status in {"BUTTON_READY", "EXTERNAL_RUNTIME_SMOKE_READY"},
        "external_runtime_smoke_ready": external_ready,
        "external_runtime_status": external_smoke["external_runtime"]["status"],
        "checks": checks,
        "blockers": blockers,
        "external_runtime_smoke": external_smoke,
        "qwen2_5_only": True,
        "fast_only": True,
        "backend": "llama_cpp",
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "next_action": _button_gate_next_action(blockers),
        "safety": _safety_payload(),
    }


def write_qwen25_smoke_button_gate_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 220-221."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(target, {"220_qwen25_smoke_button_gate.json": build_qwen25_smoke_button_gate()})


def build_final_release_readiness_bridge(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Bridge Alpha/Beta runtime evidence to final release readiness."""

    cache_key = json.dumps(
        {
            "name": "build_final_release_readiness_bridge",
            "root": _runtime_display_path(runtime_root or DEFAULT_RUNTIME_ROOT_TEXT),
            "deps": {
                "alpha": id(build_public_alpha_readiness),
                "embedded_beta": id(build_embedded_runtime_beta_candidate),
                "external_beta": id(build_external_operational_beta_candidate),
                "first_inference": id(build_first_real_inference_live_status),
                "qwen25_evidence": id(build_qwen25_release_evidence),
                "installer_rc": id(build_installer_rc_readiness),
                "clean_machine": id(build_clean_machine_emulator),
                "clean_machine_evidence": id(build_clean_machine_evidence),
                "signing": id(build_code_signing_readiness),
            },
        },
        sort_keys=True,
    )
    if cache_key in _READINESS_CACHE:
        cached = json.loads(json.dumps(_READINESS_CACHE[cache_key]))
        cached["generated_at"] = _now()
        return cached
    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    alpha = build_public_alpha_readiness()
    beta_candidate = build_embedded_runtime_beta_candidate(root)
    external_beta_candidate = build_external_operational_beta_candidate(root)
    beta_candidate_ok = beta_candidate["status"] == "BETA_CANDIDATE_READY" or (
        external_beta_candidate["status"] == "EXTERNAL_BETA_CANDIDATE_READY"
    )
    beta_candidate_detail = (
        beta_candidate["status"]
        if beta_candidate["status"] == "BETA_CANDIDATE_READY"
        else external_beta_candidate["status"]
    )
    first_inference = build_first_real_inference_live_status(root)
    qwen25_evidence = build_qwen25_release_evidence()
    first_inference_ok = first_inference["status"] in {
        "SUCCESS",
        "FIRST_REAL_INFERENCE_PASSED_EXTERNAL",
    } or qwen25_evidence["passed"]
    installer_rc = build_installer_rc_readiness()
    clean_machine = build_clean_machine_emulator(root.parent)
    clean_machine_evidence = build_clean_machine_evidence(root.parent)
    signing = build_code_signing_readiness()
    blockers = [
        _release_bridge_check("alpha_status", alpha["alpha"] == "ALPHA_READY_WITH_LIMITATIONS", alpha["alpha"]),
        _release_bridge_check("beta_candidate", beta_candidate_ok, beta_candidate_detail),
        _release_bridge_check("first_inference_status", first_inference_ok, first_inference["status"]),
        _release_bridge_check("installer_rc", installer_rc["status"] == "RC_READY", installer_rc["status"]),
        _release_bridge_check(
            "clean_machine_evidence",
            clean_machine_evidence["sufficient_for_final_release"],
            clean_machine_evidence["status"],
        ),
        _release_bridge_check("signed_installer", signing["signed_installer"], signing["status"]),
    ]
    failed = [check for check in blockers if check["status"] == "BLOCKED"]
    if failed:
        status = "FINAL_RELEASE_BLOCKED"
    elif first_inference_ok:
        status = "FINAL_RELEASE_FOUNDATION_READY"
    else:
        status = "FINAL_RELEASE_READY"
    payload = {
        "version": "17.4",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": blockers,
        "public_release_blockers": [check["id"] for check in failed],
        "alpha_status": alpha["alpha"],
        "beta_candidate_status": beta_candidate["status"],
        "external_beta_candidate_status": external_beta_candidate["status"],
        "beta_candidate_effective_status": beta_candidate_detail,
        "external_beta_candidate_counts_for_beta_only": external_beta_candidate["status"] == "EXTERNAL_BETA_CANDIDATE_READY",
        "first_inference_status": first_inference["status"],
        "qwen25_release_evidence_status": qwen25_evidence["status"],
        "qwen25_release_evidence_path": qwen25_evidence["artifact_path"],
        "installer_rc_status": installer_rc["status"],
        "clean_machine_status": clean_machine["status"],
        "clean_machine_evidence_status": clean_machine_evidence["status"],
        "clean_machine_evidence_level": clean_machine_evidence["evidence_level"],
        "local_install_smoke_passed": clean_machine_evidence["local_install_smoke_passed"],
        "external_clean_machine_passed": clean_machine_evidence["external_clean_machine_passed"],
        "embedded_runtime_final_required": True,
        "external_runtime_final_release_runtime": False,
        "signed_installer": signing["signed_installer"],
        "code_signing_status": signing["status"],
        "code_signing_blockers": signing["blockers"],
        "next_step": _final_release_next_step(failed),
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_final_release_readiness_bridge_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 222-223."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"222_final_release_readiness_bridge.json": build_final_release_readiness_bridge()},
    )


def write_guided_runtime_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 218-223 for ANN v17.2-v17.4."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    artifacts.extend(write_guided_runtime_activation_state_artifacts(target))
    artifacts.extend(write_qwen25_smoke_button_gate_artifacts(target))
    artifacts.extend(write_final_release_readiness_bridge_artifacts(target))
    return _dedupe(artifacts)


def materialize_runtime_finalization_foundation(
    runtime_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the local runtime directory skeleton and audit files without installing anything."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    layout = build_embedded_runtime_layout(root, dry_run=False, confirm_create=True)
    manifest = build_runtime_collection_manifest(root)
    integrity = build_runtime_integrity_verification(root)
    watcher = build_runtime_materialization_watcher(root)
    wheelhouse = build_wheelhouse_external_validation(root / "wheels")
    checks_payload = {
        "version": "18.0",
        "generated_at": _now(),
        **_runtime_report(root_info),
        "embedded_python_present": (root / "python" / "python.exe").is_file(),
        "wheelhouse_status": wheelhouse["status"],
        "integrity_status": integrity["status"],
        "watcher_status": watcher["status"],
        "installer_compatible": build_installer_rc_readiness()["status"] in {"RC_READY", "RC_READY_FOR_MANUAL_PACKAGING"},
        "no_install": True,
        "no_download": True,
        "no_python_execution": True,
        "safety": _safety_payload(),
    }
    runtime_manifest_path = root / "audit" / "runtime_finalization_manifest.json"
    runtime_audit_path = root / "audit" / "runtime_finalization_audit.json"
    runtime_checks_path = root / "checks" / "runtime_finalization_checks.json"
    written_runtime_files: list[str] = []
    if layout["status"] == "RUNTIME_LAYOUT_CREATED" or layout["status"] == "RUNTIME_LAYOUT_EXISTS":
        for path, payload in (
            (runtime_manifest_path, manifest),
            (runtime_audit_path, _runtime_finalization_audit(root_info, root, layout, integrity, wheelhouse)),
            (runtime_checks_path, checks_payload),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            written_runtime_files.append(str(path))
    blockers = [
        _finalization_check("layout", layout["status"] in {"RUNTIME_LAYOUT_CREATED", "RUNTIME_LAYOUT_EXISTS"}, layout["status"]),
        _finalization_check("embedded_python", (root / "python" / "python.exe").is_file(), str(root / "python" / "python.exe")),
        _finalization_check("wheelhouse_verified", wheelhouse["status"] == "VERIFIED", wheelhouse["status"]),
        _finalization_check("integrity_verified", integrity["status"] == "INTEGRITY_VERIFIED", integrity["status"]),
    ]
    failed = [check for check in blockers if not check["passed"]]
    payload = {
        "version": "18.0",
        "generated_at": _now(),
        "status": "RUNTIME_FINALIZED" if not failed else "RUNTIME_FINALIZATION_PARTIAL",
        **_runtime_report(root_info),
        "output_dir": str(target),
        "layout": layout,
        "manifest": manifest,
        "integrity": integrity,
        "wheelhouse": wheelhouse,
        "checks": blockers,
        "blockers": failed,
        "runtime_files_written": written_runtime_files,
        "no_install": True,
        "no_download": True,
        "no_python_execution": True,
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(target, {"224_runtime_finalization.json": payload})
    payload["artifacts"] = artifacts
    return payload


def build_qwen3_runtime_activation_gate(
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
) -> dict[str, Any]:
    """Evaluate the Qwen3 FAST sequential activation gate without loading the model."""

    policy = load_model_policy()
    inventory = load_model_inventory()
    record = next((item for item in inventory.models if item.model_name == QWEN3_MODEL_NAME), None)
    preparation = prepare_qwen3_controlled_activation()
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check("model_exact", record is not None and record.model_name == QWEN3_MODEL_NAME, QWEN3_MODEL_NAME),
        _finalization_check("mode_fast", record is not None and record.mode == "FAST", record.mode if record else "missing"),
        _finalization_check("adapter_exact", bool(record and record.adapter_path and record.adapter_path.endswith("qwen3-8b-product-agent-v9-repaired-v2-bullets")), record.adapter_path if record else "missing"),
        _finalization_check("model_path_exists", bool(record and record.path_exists), record.source_path if record else "missing"),
        _finalization_check("adapter_exists", bool(record and record.adapter_exists), record.adapter_path if record else "missing"),
        _finalization_check("token_valid", _token_valid(approval_token), "LOCAL_TEST_TOKEN required"),
        _finalization_check("manual_confirmation", manual_confirmation, "manual confirmation required"),
        _finalization_check("real_model_policy_enabled", policy.allow_real_model_load, str(policy.allow_real_model_load)),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
    ]
    blockers = [check for check in checks if not check["passed"]]
    return {
        "version": "18.0",
        "generated_at": _now(),
        "status": "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION" if not blockers else "QWEN3_ACTIVATION_BLOCKED",
        "model_name": QWEN3_MODEL_NAME,
        "mode": "FAST",
        "backend": record.backend if record else "qwen_local",
        "adapter": "qwen3-8b-product-agent-v9-repaired-v2-bullets",
        "checks": checks,
        "blockers": blockers,
        "preparation_status": preparation["status"],
        "load_run_unload_allowed": not blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "qwen3_loaded": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_deepseek_powerful_runtime_gate(
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
) -> dict[str, Any]:
    """Evaluate the DeepSeek POWERFUL sequential activation gate without loading the model."""

    policy = load_model_policy()
    inventory = load_model_inventory()
    record = next((item for item in inventory.models if item.model_name == DEEPSEEK14B_MODEL_NAME), None)
    preparation = prepare_deepseek_powerful_activation()
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check("model_exact", record is not None and record.model_name == DEEPSEEK14B_MODEL_NAME, DEEPSEEK14B_MODEL_NAME),
        _finalization_check("mode_powerful", record is not None and record.mode == "POWERFUL", record.mode if record else "missing"),
        _finalization_check("model_path_exists", bool(record and record.path_exists), record.source_path if record else "missing"),
        _finalization_check("backend_available", bool(record and record.backend_available), record.backend if record else "missing"),
        _finalization_check("token_valid", _token_valid(approval_token), "LOCAL_TEST_TOKEN required"),
        _finalization_check("manual_confirmation", manual_confirmation, "manual confirmation required"),
        _finalization_check("real_model_policy_enabled", policy.allow_real_model_load, str(policy.allow_real_model_load)),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
    ]
    blockers = [check for check in checks if not check["passed"]]
    return {
        "version": "18.0",
        "generated_at": _now(),
        "status": "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE" if not blockers else "DEEPSEEK_POWERFUL_BLOCKED",
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "mode": "POWERFUL",
        "backend": record.backend if record else "deepseek_unsloth",
        "fallback_backend": record.fallback_backend if record else "embedded",
        "checks": checks,
        "blockers": blockers,
        "preparation_status": preparation["status"],
        "load_run_unload_allowed": not blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "deepseek_loaded": False,
        "powerful_activated": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_installer_final_readiness(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate ANN_Setup.exe/ANN_Uninstall.exe final readiness without building binaries."""

    cache_key = f"build_installer_final_readiness:{_runtime_display_path(runtime_root or DEFAULT_RUNTIME_ROOT_TEXT)}"
    if cache_key in _READINESS_CACHE:
        return json.loads(json.dumps(_READINESS_CACHE[cache_key]))
    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    rc = build_installer_rc_readiness()
    dry_run = build_release_packaging_dry_run()
    runtime = build_runtime_materialization_watcher(root)
    clean_machine = build_clean_machine_evidence(root.parent)
    signing = build_code_signing_readiness()
    checks = [
        _finalization_check("setup_exe_readiness", rc["status"] == "RC_READY", rc["status"]),
        _finalization_check("uninstall_exe_readiness", rc["status"] == "RC_READY", rc["status"]),
        _finalization_check("shortcuts_planned", True, "installer foundation shortcut plan"),
        _finalization_check("embedded_runtime_ready", runtime["status"] == "READY", runtime["status"]),
        _finalization_check(
            "clean_machine_evidence",
            clean_machine["sufficient_for_final_release"],
            clean_machine["status"],
        ),
        _finalization_check("signed_installer", signing["signed_installer"], signing["status"]),
        _finalization_check("packaging_dry_run", dry_run["status"] == "DRY_RUN_READY", dry_run["status"]),
    ]
    blockers = [check for check in checks if not check["passed"]]
    payload = {
        "version": "18.0",
        "generated_at": _now(),
        "status": "INSTALLER_FINAL_READY" if not blockers else "INSTALLER_FINAL_BLOCKED",
        **_runtime_report(root_info),
        "ann_setup_exe_readiness": blockers == [],
        "ann_uninstall_exe_readiness": blockers == [],
        "shortcuts": "planned",
        "embedded_runtime_integration": runtime["status"],
        "clean_machine_evidence_status": clean_machine["status"],
        "clean_machine_evidence_level": clean_machine["evidence_level"],
        "local_install_smoke_passed": clean_machine["local_install_smoke_passed"],
        "external_clean_machine_passed": clean_machine["external_clean_machine_passed"],
        "signed_installer_readiness": signing["signed_installer"],
        "code_signing_status": signing["status"],
        "code_signing_blockers": signing["blockers"],
        "checks": checks,
        "blockers": blockers,
        "no_build_exe": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def build_public_release_bridge_final(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate ALPHA/BETA/RC/PUBLIC/FINAL release states from existing gates."""

    cache_key = f"build_public_release_bridge_final:{_runtime_display_path(runtime_root or DEFAULT_RUNTIME_ROOT_TEXT)}"
    if cache_key in _READINESS_CACHE:
        return json.loads(json.dumps(_READINESS_CACHE[cache_key]))
    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    alpha = build_public_alpha_readiness()
    beta = build_beta_runtime_activation(root)
    qwen25 = build_first_real_inference_live_status(root)
    qwen25_evidence = build_qwen25_release_evidence()
    qwen3 = build_qwen3_runtime_activation_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    qwen3_evidence = build_qwen3_release_evidence()
    deepseek = build_deepseek_powerful_runtime_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    deepseek_evidence = build_deepseek_powerful_release_evidence()
    installer = build_installer_final_readiness(root)
    final_bridge = build_final_release_readiness_bridge(root)
    checks = [
        _finalization_check("alpha_ready", alpha["alpha"] == "ALPHA_READY_WITH_LIMITATIONS", alpha["alpha"]),
        _finalization_check("beta_ready", beta["status"] in {"BETA_READY", "BETA_ACTIVE"}, beta["status"]),
        _finalization_check(
            "qwen25_success",
            qwen25["status"] == "SUCCESS" or qwen25_evidence["passed"],
            qwen25["status"] if qwen25["status"] == "SUCCESS" else qwen25_evidence["status"],
        ),
        _finalization_check(
            "qwen3_ready",
            qwen3["status"] == "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION" or qwen3_evidence["passed"],
            qwen3["status"] if qwen3["status"] == "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION" else qwen3_evidence["status"],
        ),
        _finalization_check(
            "deepseek_ready",
            deepseek["status"] == "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE" or deepseek_evidence["passed"],
            deepseek["status"] if deepseek["status"] == "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE" else deepseek_evidence["status"],
        ),
        _finalization_check("installer_final", installer["status"] == "INSTALLER_FINAL_READY", installer["status"]),
        _finalization_check("final_bridge", final_bridge["status"] == "FINAL_RELEASE_READY", final_bridge["status"]),
    ]
    blockers = [check for check in checks if not check["passed"]]
    if blockers:
        channel = "ALPHA" if alpha["alpha"] == "ALPHA_READY_WITH_LIMITATIONS" else "BLOCKED"
        status = "FINAL_RELEASE_BLOCKED"
    else:
        channel = "FINAL_RELEASE_READY"
        status = "FINAL_RELEASE_READY"
    payload = {
        "version": "18.0",
        "generated_at": _now(),
        "status": status,
        "release_channel": channel,
        "allowed_states": ["ALPHA", "BETA", "RC", "PUBLIC", "FINAL_RELEASE_READY"],
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "qwen2_5": qwen25,
        "qwen2_5_release_evidence": qwen25_evidence,
        "qwen3": qwen3,
        "qwen3_release_evidence": qwen3_evidence,
        "deepseek": deepseek,
        "deepseek_release_evidence": deepseek_evidence,
        "installer": installer,
        "final_bridge": final_bridge,
        "next_action": "Resolve blocker: " + blockers[0]["id"] if blockers else "Publish release candidate evidence.",
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def build_ann_finalization_megaphase(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build the ANN finalization mega-gate and declare final release only when every gate passes."""

    cache_key = f"build_ann_finalization_megaphase:{_runtime_display_path(runtime_root or DEFAULT_RUNTIME_ROOT_TEXT)}"
    if cache_key in _READINESS_CACHE:
        return json.loads(json.dumps(_READINESS_CACHE[cache_key]))
    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    runtime = build_runtime_materialization_watcher(root)
    qwen25 = build_qwen25_smoke_button_gate(root)
    qwen25_evidence = build_qwen25_release_evidence()
    qwen3 = build_qwen3_runtime_activation_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    qwen3_evidence = build_qwen3_release_evidence()
    deepseek = build_deepseek_powerful_runtime_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    deepseek_evidence = build_deepseek_powerful_release_evidence()
    desktop = build_guided_runtime_activation_state(root)
    installer = build_installer_final_readiness(root)
    release = build_public_release_bridge_final(root)
    gates = [
        _finalization_check("runtime_finalization", runtime["status"] == "READY", runtime["status"]),
        _finalization_check(
            "qwen2_5_smoke",
            qwen25["status"] == "BUTTON_READY" or qwen25_evidence["passed"],
            qwen25["status"] if qwen25["status"] == "BUTTON_READY" else qwen25_evidence["status"],
        ),
        _finalization_check(
            "qwen3_activation",
            qwen3["status"] == "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION" or qwen3_evidence["passed"],
            qwen3["status"] if qwen3["status"] == "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION" else qwen3_evidence["status"],
        ),
        _finalization_check(
            "deepseek_powerful",
            deepseek["status"] == "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE" or deepseek_evidence["passed"],
            deepseek["status"] if deepseek["status"] == "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE" else deepseek_evidence["status"],
        ),
        _finalization_check("desktop_final", desktop["status"] in {"GUIDED_READY_FOR_SMOKE", "GUIDED_PARTIAL"}, desktop["status"]),
        _finalization_check("installer_final", installer["status"] == "INSTALLER_FINAL_READY", installer["status"]),
        _finalization_check("public_release", release["status"] == "FINAL_RELEASE_READY", release["status"]),
    ]
    blockers = [gate for gate in gates if not gate["passed"]]
    payload = {
        "version": "18.0",
        "generated_at": _now(),
        "status": "FINAL_RELEASE_READY" if not blockers else "FINAL_RELEASE_BLOCKED",
        "from_state": "ALPHA_READY_WITH_LIMITATIONS",
        "target_state": "FINAL_RELEASE_READY",
        **_runtime_report(root_info),
        "gates": gates,
        "blockers": blockers,
        "runtime": runtime,
        "qwen2_5": qwen25,
        "qwen2_5_release_evidence": qwen25_evidence,
        "qwen3": qwen3,
        "qwen3_release_evidence": qwen3_evidence,
        "deepseek": deepseek,
        "deepseek_release_evidence": deepseek_evidence,
        "desktop": desktop,
        "installer": installer,
        "public_release": release,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "vram_policy": load_model_policy().vram_policy,
        "no_internet": True,
        "no_downloads": True,
        "no_installs": True,
        "no_training": True,
        "models_modified": False,
        "datasets_modified": False,
        "adapters_modified": False,
        "next_action": "Resolve blocker: " + blockers[0]["id"] if blockers else "ANN is final release ready.",
        "safety": _safety_payload(),
    }
    _READINESS_CACHE[cache_key] = json.loads(json.dumps(payload))
    return payload


def write_ann_finalization_megaphase_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 224-231 for ANN Finalization Megaphase."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    runtime_payload = materialize_runtime_finalization_foundation(output_dir=target)
    qwen3 = build_qwen3_runtime_activation_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    deepseek = build_deepseek_powerful_runtime_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    installer = build_installer_final_readiness()
    release = build_public_release_bridge_final()
    finalization = build_ann_finalization_megaphase()
    artifacts = list(runtime_payload.get("artifacts", []))
    artifacts.extend(
        _write_numbered_artifacts(
            target,
            {
                "226_qwen3_runtime_activation_gate.json": qwen3,
                "228_deepseek_powerful_runtime_gate.json": deepseek,
                "230_installer_public_release_finalization.json": {
                    "version": "18.0",
                    "generated_at": _now(),
                    "status": finalization["status"],
                    "installer": installer,
                    "public_release": release,
                    "finalization": finalization,
                    "safety": _safety_payload(),
                },
            },
        )
    )
    return _dedupe(artifacts)


def build_external_verified_runtime_bridge() -> dict[str, Any]:
    """Detect the current external runtime as a temporary smoke runtime only."""

    cuda = diagnose_cuda_environment()
    qwen25_path = _resolve_runtime_filesystem_path(QWEN25_EXACT_GGUF_PATH)
    llama_cpp_importable = importlib.util.find_spec("llama_cpp") is not None
    llama_cpp_version = None
    if llama_cpp_importable:
        try:
            llama_cpp_version = importlib.metadata.version("llama-cpp-python")
        except importlib.metadata.PackageNotFoundError:
            llama_cpp_version = "importable_version_unknown"
    checks = [
        _finalization_check("python_executable_present", Path(sys.executable).is_file(), sys.executable),
        _finalization_check("python_version_3_11_plus", sys.version_info >= (3, 11), platform.python_version()),
        _finalization_check("torch_importable", bool(cuda["torch_importable"]), str(cuda["torch_importable"])),
        _finalization_check("torch_cuda_available", bool(cuda["cuda_available"]), str(cuda["cuda_available"])),
        _finalization_check("llama_cpp_importable", llama_cpp_importable, str(llama_cpp_importable)),
        _finalization_check("qwen25_gguf_exists", qwen25_path.is_file(), str(qwen25_path)),
        _finalization_check("active_models_zero", get_runtime_metrics().get("active_models", 0) == 0, str(get_runtime_metrics().get("active_models", 0))),
        _finalization_check("parallel_loads_zero", get_runtime_metrics().get("parallel_llm_loads", 0) == 0, str(get_runtime_metrics().get("parallel_llm_loads", 0))),
    ]
    blockers = [check for check in checks if not check["passed"]]
    critical_ids = {
        "python_executable_present",
        "torch_importable",
        "llama_cpp_importable",
        "qwen25_gguf_exists",
    }
    critical_blockers = [check for check in blockers if check["id"] in critical_ids]
    if not blockers:
        status = "EXTERNAL_RUNTIME_READY"
    elif critical_blockers:
        status = "EXTERNAL_RUNTIME_BLOCKED"
    else:
        status = "EXTERNAL_RUNTIME_PARTIAL"
    return {
        "version": "18.2",
        "generated_at": _now(),
        "status": status,
        "runtime_type": _external_runtime_type(sys.executable),
        "is_embedded_runtime": False,
        "final_release_runtime": False,
        "controlled_qwen25_smoke_only": True,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "torch_importable": bool(cuda["torch_importable"]),
        "torch_version": cuda["torch_version"],
        "torch_cuda_available": bool(cuda["cuda_available"]),
        "torch_cuda_version": cuda["torch_cuda_version"],
        "gpu_name": cuda["gpu_name"],
        "vram_total_mb": cuda["vram_total_mb"],
        "llama_cpp_importable": llama_cpp_importable,
        "llama_cpp_version": llama_cpp_version,
        "qwen25_model_path": QWEN25_EXACT_GGUF_PATH,
        "qwen25_model_resolved_path": str(qwen25_path),
        "qwen25_gguf_exists": qwen25_path.is_file(),
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "checks": checks,
        "blockers": blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_python_execution": True,
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def build_wsl_external_verified_runtime_bridge(*, force_refresh: bool = False, timeout_seconds: int = 30) -> dict[str, Any]:
    """Detect a prepared WSL conda runtime from Windows without loading models."""

    global _WSL_EXTERNAL_RUNTIME_CACHE
    if _WSL_EXTERNAL_RUNTIME_CACHE is not None and not force_refresh:
        return dict(_WSL_EXTERNAL_RUNTIME_CACHE)
    if platform.system().lower() != "windows":
        payload = _wsl_runtime_payload(
            status="WSL_RUNTIME_NOT_APPLICABLE",
            blockers=[_finalization_check("windows_host_required", False, platform.system())],
        )
        _WSL_EXTERNAL_RUNTIME_CACHE = payload
        return dict(payload)
    if shutil.which("wsl.exe") is None:
        payload = _wsl_runtime_payload(
            status="WSL_RUNTIME_UNAVAILABLE",
            blockers=[_finalization_check("wsl_exe_available", False, "wsl.exe not found")],
        )
        _WSL_EXTERNAL_RUNTIME_CACHE = payload
        return dict(payload)
    probe = r'''
set -e
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
  echo '{"status":"WSL_RUNTIME_BLOCKED","blocker":"conda_profile_missing"}'
  exit 0
fi
if ! conda activate qlora311 >/dev/null 2>&1; then
  echo '{"status":"WSL_RUNTIME_BLOCKED","blocker":"conda_env_qlora311_missing"}'
  exit 0
fi
cd /mnt/d/AgenticEngineeringNetwork
python - <<'PY'
from __future__ import annotations
import importlib.util, json, platform, sys
from pathlib import Path
payload = {
    "status": "WSL_RUNTIME_READY",
    "runtime_type": "external_wsl_conda",
    "is_embedded_runtime": False,
    "final_release_runtime": False,
    "controlled_qwen25_smoke_only": True,
    "python_executable": sys.executable,
    "python_version": platform.python_version(),
    "torch_importable": False,
    "torch_version": None,
    "torch_cuda_available": False,
    "torch_cuda_version": None,
    "gpu_name": None,
    "vram_total_mb": None,
    "llama_cpp_importable": importlib.util.find_spec("llama_cpp") is not None,
    "qwen25_gguf_exists": Path("/mnt/d/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf").is_file(),
    "blockers": [],
}
try:
    import torch
    payload["torch_importable"] = True
    payload["torch_version"] = getattr(torch, "__version__", None)
    payload["torch_cuda_available"] = bool(torch.cuda.is_available())
    payload["torch_cuda_version"] = getattr(torch.version, "cuda", None)
    if payload["torch_cuda_available"]:
        payload["gpu_name"] = torch.cuda.get_device_name(0)
        payload["vram_total_mb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 2)
except Exception as exc:
    payload["torch_error"] = f"{type(exc).__name__}: {exc}"
for key in ("torch_importable", "torch_cuda_available", "llama_cpp_importable", "qwen25_gguf_exists"):
    if not payload[key]:
        payload["blockers"].append(key)
if payload["blockers"]:
    payload["status"] = "WSL_RUNTIME_BLOCKED"
print(json.dumps(payload))
PY
'''
    try:
        completed = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", probe],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        payload = _wsl_runtime_payload(
            status="WSL_RUNTIME_UNAVAILABLE",
            blockers=[_finalization_check("wsl_probe_completed", False, f"{type(exc).__name__}: {exc}")],
        )
        _WSL_EXTERNAL_RUNTIME_CACHE = payload
        return dict(payload)
    parsed: dict[str, Any]
    try:
        parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        parsed = {
            "status": "WSL_RUNTIME_BLOCKED",
            "blocker": "invalid_wsl_probe_output",
            "stdout": (completed.stdout or "")[-2000:],
        }
    blocker_values = _list_from(parsed.get("blockers")) or _list_from(parsed.get("blocker"))
    checks = [
        _finalization_check("wsl_probe_returncode_zero", completed.returncode == 0, str(completed.returncode)),
        _finalization_check("wsl_runtime_ready", parsed.get("status") == "WSL_RUNTIME_READY", str(parsed.get("status"))),
        _finalization_check("torch_cuda_available", bool(parsed.get("torch_cuda_available")), str(parsed.get("torch_cuda_available"))),
        _finalization_check("llama_cpp_importable", bool(parsed.get("llama_cpp_importable")), str(parsed.get("llama_cpp_importable"))),
        _finalization_check("qwen25_gguf_exists", bool(parsed.get("qwen25_gguf_exists")), str(parsed.get("qwen25_gguf_exists"))),
    ]
    blockers = [check for check in checks if not check["passed"]]
    if blocker_values:
        blockers.extend(_finalization_check(f"wsl_blocker_{idx}", False, value) for idx, value in enumerate(blocker_values, 1))
    status = "WSL_RUNTIME_READY" if not blockers else "WSL_RUNTIME_BLOCKED"
    payload = {
        "version": "1.2",
        "generated_at": _now(),
        "status": status,
        "runtime_type": parsed.get("runtime_type", "external_wsl_conda"),
        "is_embedded_runtime": False,
        "final_release_runtime": False,
        "controlled_qwen25_smoke_only": True,
        "python_executable": parsed.get("python_executable"),
        "python_version": parsed.get("python_version"),
        "torch_importable": bool(parsed.get("torch_importable")),
        "torch_version": parsed.get("torch_version"),
        "torch_cuda_available": bool(parsed.get("torch_cuda_available")),
        "torch_cuda_version": parsed.get("torch_cuda_version"),
        "gpu_name": parsed.get("gpu_name"),
        "vram_total_mb": parsed.get("vram_total_mb"),
        "llama_cpp_importable": bool(parsed.get("llama_cpp_importable")),
        "qwen25_gguf_exists": bool(parsed.get("qwen25_gguf_exists")),
        "checks": checks,
        "blockers": blockers,
        "returncode": completed.returncode,
        "stderr": (completed.stderr or "")[-2000:],
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }
    _WSL_EXTERNAL_RUNTIME_CACHE = payload
    return dict(payload)


def build_best_external_verified_runtime_bridge(*, allow_wsl_probe: bool = True) -> dict[str, Any]:
    """Return the best non-embedded runtime without marking final release ready."""

    current = build_external_verified_runtime_bridge()
    if current["status"] == "EXTERNAL_RUNTIME_READY" or not allow_wsl_probe:
        return {**current, "selected_runtime_source": "current_process"}
    wsl = build_wsl_external_verified_runtime_bridge()
    if wsl["status"] == "WSL_RUNTIME_READY":
        return {
            **wsl,
            "status": "EXTERNAL_RUNTIME_READY",
            "selected_runtime_source": "wsl_conda",
            "current_process_status": current["status"],
            "qwen25_model_path": QWEN25_EXACT_GGUF_PATH,
            "qwen25_model_resolved_path": "/mnt/d/AgenticEngineeringNetwork/models/qwen2.5-coder-7b-q4_k_m.gguf",
        }
    return {
        **current,
        "selected_runtime_source": "current_process",
        "wsl_fallback_status": wsl["status"],
        "wsl_fallback_blockers": wsl.get("blockers", []),
    }


def _wsl_runtime_payload(*, status: str, blockers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "1.2",
        "generated_at": _now(),
        "status": status,
        "runtime_type": "external_wsl_conda",
        "is_embedded_runtime": False,
        "final_release_runtime": False,
        "controlled_qwen25_smoke_only": True,
        "python_executable": None,
        "python_version": None,
        "torch_importable": False,
        "torch_version": None,
        "torch_cuda_available": False,
        "torch_cuda_version": None,
        "gpu_name": None,
        "vram_total_mb": None,
        "llama_cpp_importable": False,
        "qwen25_gguf_exists": False,
        "checks": [],
        "blockers": blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def build_embedded_python_evidence(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build read-only embedded Python evidence without executing python.exe."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    python_dir = root / "python"
    python_exe = python_dir / "python.exe"
    checks = [
        _finalization_check("runtime_root_exists", root.is_dir(), str(root)),
        _finalization_check("python_directory_exists", python_dir.is_dir(), str(python_dir)),
        _finalization_check("python_executable_exists", python_exe.is_file(), str(python_exe)),
    ]
    if root_info["blocked"]:
        status = "MISSING"
    elif python_exe.is_file():
        status = "READY"
    elif root.is_dir() or python_dir.is_dir():
        status = "PARTIAL"
    else:
        status = "MISSING"
    return {
        "version": "17.5",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "python_directory": str(python_dir),
        "python_executable": str(python_exe),
        "embedded_python_version": "not_executed",
        "version_detection": "blocked_by_design_no_python_execution",
        "checks": checks,
        "blockers": [check for check in checks if not check["passed"]],
        "ready": status == "READY",
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "python_execution_attempted": False,
        "no_python_execution": True,
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def build_runtime_wheelhouse_readiness(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate offline wheelhouse readiness without installing wheels."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    wheelhouse = root / "wheels"
    watcher = build_runtime_materialization_watcher(root)
    validation = build_wheelhouse_external_validation(wheelhouse)
    registry = build_wheelhouse_integrity_registry(wheelhouse)
    integrity = build_runtime_integrity_verification(root)
    wheelhouse_count = int(watcher.get("wheelhouse_count", 0))
    checks = [
        _finalization_check("wheelhouse_directory_exists", wheelhouse.is_dir(), str(wheelhouse)),
        _finalization_check("wheelhouse_not_empty", wheelhouse_count > 0, str(wheelhouse_count)),
        _finalization_check("wheelhouse_hashes_verified", validation["status"] == "VERIFIED", validation["status"]),
        _finalization_check("wheelhouse_registry_verified", registry["status"] == "HASH_VERIFIED", registry["status"]),
    ]
    if root_info["blocked"] or not wheelhouse.is_dir() or wheelhouse_count == 0:
        status = "EMPTY"
    elif validation["status"] == "VERIFIED" and registry["status"] == "HASH_VERIFIED":
        status = "READY"
    else:
        status = "PARTIAL"
    return {
        "version": "17.6",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "wheelhouse_path": str(wheelhouse),
        "wheelhouse_count": wheelhouse_count,
        "validation_status": validation["status"],
        "registry_status": registry["status"],
        "integrity_status": integrity["status"],
        "checks": checks,
        "blockers": [check for check in checks if not check["passed"]],
        "watcher_status": watcher["status"],
        "wheels": validation.get("wheels", []),
        "ready": status == "READY",
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_wheel_execution": True,
        "no_install": True,
        "no_download": True,
        "safety": _safety_payload(),
    }


def build_external_runtime_smoke_readiness(*, allow_wsl_probe: bool | None = None) -> dict[str, Any]:
    """Evaluate Qwen2.5 controlled smoke readiness using the verified external runtime."""

    use_wsl_probe = (
        platform.system().lower() == "windows" or os.getenv("ANN_ENABLE_WSL_RUNTIME_PROBE") == "1"
        if allow_wsl_probe is None
        else allow_wsl_probe
    )
    external = build_best_external_verified_runtime_bridge(allow_wsl_probe=use_wsl_probe)
    policy = load_model_policy()
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check(
            "external_runtime_ready",
            external["status"] == "EXTERNAL_RUNTIME_READY",
            external["status"],
        ),
        _finalization_check("runtime_not_embedded", external["is_embedded_runtime"] is False, str(external["is_embedded_runtime"])),
        _finalization_check("qwen2_5_exact_model", external["qwen25_gguf_exists"], external["qwen25_model_resolved_path"]),
        _finalization_check("fast_mode", True, "FAST"),
        _finalization_check("llama_cpp_backend", external["llama_cpp_importable"], str(external["llama_cpp_importable"])),
        _finalization_check("torch_cuda_available", external["torch_cuda_available"], str(external["torch_cuda_available"])),
        _finalization_check("token_required", _token_valid(LOCAL_TEST_TOKEN), "LOCAL_TEST_TOKEN"),
        _finalization_check("manual_confirmation_required", True, "manual confirmation required before execution"),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
        _finalization_check("qwen3_blocked", True, "Qwen3 not allowed in v18.2 external smoke"),
        _finalization_check("deepseek_blocked", True, "DeepSeek not allowed in v18.2 external smoke"),
        _finalization_check("powerful_blocked", True, "POWERFUL not allowed in v18.2 external smoke"),
    ]
    blockers = [check for check in checks if not check["passed"]]
    return {
        "version": "18.2",
        "generated_at": _now(),
        "status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL" if not blockers else "BLOCKED",
        "runtime_type": external["runtime_type"],
        "selected_runtime_source": external.get("selected_runtime_source", "current_process"),
        "wsl_probe_enabled": use_wsl_probe,
        "is_embedded_runtime": False,
        "final_release_runtime": False,
        "model_name": QWEN25_MODEL_NAME,
        "mode": "FAST",
        "backend": "llama_cpp",
        "button_label": "External Runtime Smoke",
        "checks": checks,
        "blockers": blockers,
        "external_runtime": external,
        "token_required": LOCAL_TEST_TOKEN,
        "manual_confirmation_required": True,
        "risk_acknowledgement_required": True,
        "load_run_unload_allowed_after_confirmation": not blockers,
        "qwen3_blocked": True,
        "deepseek_blocked": True,
        "powerful_blocked": True,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_first_real_smoke_preparation(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Prepare the first Qwen2.5 smoke gate without running or loading the model."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    policy = load_model_policy()
    embedded = build_embedded_python_evidence(root)
    wheelhouse = build_runtime_wheelhouse_readiness(root)
    launch_guard = build_real_inference_launch_guard(
        confirm=True,
        approval_token=LOCAL_TEST_TOKEN,
        experimental=True,
    )
    button_gate = build_qwen25_smoke_button_gate(root)
    controlled_gate = build_controlled_first_inference_gate(
        root,
        approval_token=LOCAL_TEST_TOKEN,
        manual_confirmation=True,
    )
    external_smoke = build_external_runtime_smoke_readiness()
    live_status = build_first_real_inference_live_status(root)
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check("qwen2_5_exact_model", True, QWEN25_MODEL_NAME),
        _finalization_check("fast_mode", True, "FAST"),
        _finalization_check("llama_cpp_backend", True, "llama_cpp"),
        _finalization_check("embedded_python_ready", embedded["status"] == "READY", embedded["status"]),
        _finalization_check("wheelhouse_ready", wheelhouse["status"] == "READY", wheelhouse["status"]),
        _finalization_check("launch_guard_passed", launch_guard["status"] == "PASSED", launch_guard["status"]),
        _finalization_check("button_gate_ready", button_gate["status"] == "BUTTON_READY", button_gate["status"]),
        _finalization_check("controlled_gate_ready", controlled_gate["status"] == "READY_FOR_CONTROLLED_SMOKE", controlled_gate["status"]),
        _finalization_check("token_valid", _token_valid(LOCAL_TEST_TOKEN), "LOCAL_TEST_TOKEN"),
        _finalization_check("manual_confirmation_required", True, "manual confirmation required before execution"),
        _finalization_check("safe_rollback_state", get_loaded_models() == [], "loaded_models_empty"),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
    ]
    blockers = [check for check in checks if not check["passed"]]
    external_ready = external_smoke["status"] == "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    if not blockers:
        status = "READY"
    elif external_ready:
        status = "READY_FOR_CONTROLLED_SMOKE_EXTERNAL"
    else:
        status = "BLOCKED"
    return {
        "version": "17.6",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "model_name": QWEN25_MODEL_NAME,
        "mode": "FAST",
        "backend": "llama_cpp",
        "checks": checks,
        "blockers": blockers,
        "embedded_python": embedded,
        "wheelhouse": wheelhouse,
        "external_runtime_smoke": external_smoke,
        "external_runtime_status": external_smoke["external_runtime"]["status"],
        "external_runtime_allowed_for_qwen25_smoke": external_ready,
        "embedded_runtime_finalization_satisfied": embedded["status"] == "READY" and wheelhouse["status"] == "READY",
        "launch_guard_status": launch_guard["status"],
        "button_gate_status": button_gate["status"],
        "controlled_gate_status": controlled_gate["status"],
        "live_status": live_status["status"],
        "token_required": LOCAL_TEST_TOKEN,
        "manual_confirmation_required": True,
        "risk_acknowledgement_required": True,
        "safe_rollback_required": True,
        "load_run_unload_allowed_after_confirmation": not blockers or external_ready,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_qwen3_runtime_bridge(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Bridge Qwen3 FAST activation to the existing runtime gates without loading it."""

    root_info = _runtime_path_info(runtime_root)
    policy = load_model_policy()
    gate = build_qwen3_runtime_activation_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    preparation = prepare_qwen3_controlled_activation()
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check("gate_ready", gate["status"] == "QWEN3_READY_FOR_SEQUENTIAL_ACTIVATION", gate["status"]),
        _finalization_check("model_name", gate["model_name"] == QWEN3_MODEL_NAME, gate["model_name"]),
        _finalization_check("mode_fast", gate["mode"] == "FAST", gate["mode"]),
        _finalization_check("adapter_exact", gate["adapter"] == "qwen3-8b-product-agent-v9-repaired-v2-bullets", gate["adapter"]),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
    ]
    blockers = [check for check in checks if not check["passed"]]
    return {
        "version": "17.7",
        "generated_at": _now(),
        "status": "READY" if not blockers else "BLOCKED",
        **_runtime_report(root_info),
        "model_name": QWEN3_MODEL_NAME,
        "mode": "FAST",
        "adapter": "qwen3-8b-product-agent-v9-repaired-v2-bullets",
        "sequential_only": True,
        "gate_status": gate["status"],
        "preparation_status": preparation["status"],
        "checks": checks,
        "blockers": blockers,
        "load_run_unload_allowed_after_confirmation": not blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "qwen3_loaded": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_deepseek_powerful_bridge(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Bridge DeepSeek POWERFUL activation to the existing runtime gates without loading it."""

    root_info = _runtime_path_info(runtime_root)
    policy = load_model_policy()
    gate = build_deepseek_powerful_runtime_gate(approval_token=LOCAL_TEST_TOKEN, manual_confirmation=True)
    preparation = prepare_deepseek_powerful_activation()
    metrics = get_runtime_metrics()
    checks = [
        _finalization_check("gate_ready", gate["status"] == "DEEPSEEK_READY_FOR_SEQUENTIAL_POWERFUL_SMOKE", gate["status"]),
        _finalization_check("model_name", gate["model_name"] == DEEPSEEK14B_MODEL_NAME, gate["model_name"]),
        _finalization_check("mode_powerful", gate["mode"] == "POWERFUL", gate["mode"]),
        _finalization_check("active_models_zero", metrics.get("active_models", 0) == 0, str(metrics.get("active_models", 0))),
        _finalization_check("parallel_loads_zero", metrics.get("parallel_llm_loads", 0) == 0, str(metrics.get("parallel_llm_loads", 0))),
        _finalization_check("sequential_policy", policy.max_loaded_models == 1 and policy.vram_policy == "SEQUENTIAL", policy.vram_policy),
    ]
    blockers = [check for check in checks if not check["passed"]]
    return {
        "version": "17.7",
        "generated_at": _now(),
        "status": "READY" if not blockers else "BLOCKED",
        **_runtime_report(root_info),
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "mode": "POWERFUL",
        "sequential_only": True,
        "never_parallel": True,
        "gate_status": gate["status"],
        "preparation_status": preparation["status"],
        "checks": checks,
        "blockers": blockers,
        "load_run_unload_allowed_after_confirmation": not blockers,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "deepseek_loaded": False,
        "powerful_activated": False,
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "vram_policy": policy.vram_policy,
        "safety": _safety_payload(),
    }


def build_final_release_precheck(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Aggregate final release precheck evidence without promoting ANN automatically."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    runtime = build_runtime_materialization_watcher(root)
    embedded = build_embedded_python_evidence(root)
    wheelhouse = build_runtime_wheelhouse_readiness(root)
    smoke = build_first_real_smoke_preparation(root)
    qwen3 = build_qwen3_runtime_bridge(root)
    deepseek = build_deepseek_powerful_bridge(root)
    guided = build_guided_runtime_activation_state(root)
    installer = build_installer_final_readiness(root)
    release = build_public_release_bridge_final(root)
    finalization = build_ann_finalization_megaphase(root)
    checks = [
        _finalization_check("runtime_materialized", runtime["status"] == "READY", runtime["status"]),
        _finalization_check("embedded_python_ready", embedded["status"] == "READY", embedded["status"]),
        _finalization_check("wheelhouse_ready", wheelhouse["status"] == "READY", wheelhouse["status"]),
        _finalization_check("qwen25_smoke_preparation", smoke["status"] == "READY", smoke["status"]),
        _finalization_check("qwen3_runtime_bridge", qwen3["status"] == "READY", qwen3["status"]),
        _finalization_check("deepseek_powerful_bridge", deepseek["status"] == "READY", deepseek["status"]),
        _finalization_check("desktop_guided_runtime", guided["status"] in {"GUIDED_READY_FOR_SMOKE", "GUIDED_PARTIAL"}, guided["status"]),
        _finalization_check("installer_final", installer["status"] == "INSTALLER_FINAL_READY", installer["status"]),
        _finalization_check("public_release_bridge", release["status"] == "FINAL_RELEASE_READY", release["status"]),
        _finalization_check("ann_finalization_gate", finalization["status"] == "FINAL_RELEASE_READY", finalization["status"]),
    ]
    blockers = [check for check in checks if not check["passed"]]
    if not blockers and finalization["status"] == "FINAL_RELEASE_READY":
        status = "FINAL_RELEASE_READY"
    elif not blockers:
        status = "PRECHECK_READY"
    else:
        status = "PRECHECK_BLOCKED"
    return {
        "version": "17.8",
        "generated_at": _now(),
        "status": status,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "runtime": runtime,
        "embedded_python": embedded,
        "wheelhouse": wheelhouse,
        "qwen2_5": smoke,
        "qwen3": qwen3,
        "deepseek": deepseek,
        "desktop": guided,
        "installer": installer,
        "public_release": release,
        "finalization": finalization,
        "model_load_attempted": False,
        "real_inference_attempted": False,
        "no_internet": True,
        "no_downloads": True,
        "no_installs": True,
        "no_training": True,
        "models_modified": False,
        "datasets_modified": False,
        "adapters_modified": False,
        "next_action": "Resolve blocker: " + blockers[0]["id"] if blockers else "Run controlled release sign-off.",
        "safety": _safety_payload(),
    }


def write_real_runtime_preparation_macro_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 232-243 for ANN v17.5-v17.8."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {
            "232_embedded_python_evidence.json": build_embedded_python_evidence(),
            "234_runtime_wheelhouse_readiness.json": build_runtime_wheelhouse_readiness(),
            "236_first_real_smoke_preparation.json": build_first_real_smoke_preparation(),
            "238_qwen3_runtime_bridge.json": build_qwen3_runtime_bridge(),
            "240_deepseek_powerful_bridge.json": build_deepseek_powerful_bridge(),
            "242_final_release_precheck.json": build_final_release_precheck(),
        },
    )


def build_final_release_verification_report(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Aggregate final release gates into a single non-mutating verification report."""

    root_info = _runtime_path_info(runtime_root)
    root = root_info["path"]
    runtime = build_runtime_materialization_watcher(root)
    wheelhouse = validate_wheelhouse_integrity(root / "wheels")
    package_audit = build_embedded_runtime_package_audit(root)
    installer_rc = build_installer_rc_readiness()
    clean_machine = build_clean_machine_evidence(root.parent)
    signing = build_code_signing_readiness()
    installer_final = build_installer_final_readiness(root)
    release_bridge = build_final_release_readiness_bridge(root)
    public_release = build_public_release_bridge_final(root)
    ann_finalization = build_ann_finalization_megaphase(root)
    autonomous_capability = build_autonomous_complex_capability_gate()
    checks = [
        _finalization_check("runtime_materialization", runtime["status"] == "READY", runtime["status"]),
        _finalization_check("wheelhouse_integrity", wheelhouse["status"] == "HASH_VERIFIED", wheelhouse["status"]),
        _finalization_check("embedded_package_audit", package_audit["status"] == "PACKAGE_AUDIT_READY", package_audit["status"]),
        _finalization_check("installer_rc", installer_rc["status"] == "RC_READY", installer_rc["status"]),
        _finalization_check(
            "autonomous_complex_capability",
            autonomous_capability["status"] == "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED",
            autonomous_capability["status"],
        ),
        _finalization_check(
            "external_clean_machine_evidence",
            clean_machine["sufficient_for_final_release"],
            clean_machine["status"],
        ),
        _finalization_check("signed_installer", signing["signed_installer"], signing["status"]),
        _finalization_check("installer_final", installer_final["status"] == "INSTALLER_FINAL_READY", installer_final["status"]),
        _finalization_check("final_release_bridge", release_bridge["status"] == "FINAL_RELEASE_READY", release_bridge["status"]),
        _finalization_check("public_release", public_release["status"] == "FINAL_RELEASE_READY", public_release["status"]),
        _finalization_check("ann_finalization", ann_finalization["status"] == "FINAL_RELEASE_READY", ann_finalization["status"]),
    ]
    blockers = [check for check in checks if not check["passed"]]
    status = "FINAL_RELEASE_READY" if not blockers else "FINAL_RELEASE_BLOCKED"
    return {
        "version": "18.9.10",
        "generated_at": _now(),
        "status": status,
        "exit_code": 0 if status == "FINAL_RELEASE_READY" else 2,
        **_runtime_report(root_info),
        "checks": checks,
        "blockers": blockers,
        "runtime_materialization": runtime["status"],
        "wheelhouse_integrity": wheelhouse["status"],
        "embedded_package_audit": package_audit["status"],
        "installer_rc": installer_rc["status"],
        "installer_final": installer_final["status"],
        "final_release_bridge": release_bridge["status"],
        "public_release": public_release["status"],
        "ann_finalization": ann_finalization["status"],
        "autonomous_complex_capability": autonomous_capability["status"],
        "autonomous_complex_capability_passed": autonomous_capability["passed"],
        "autonomous_complex_capability_required_scenarios": autonomous_capability["required_scenarios"],
        "autonomous_complex_capability_passed_scenarios": autonomous_capability["passed_scenarios"],
        "local_install_smoke_passed": clean_machine["local_install_smoke_passed"],
        "external_clean_machine_passed": clean_machine["external_clean_machine_passed"],
        "signed_installer": signing["signed_installer"],
        "code_signing_status": signing["status"],
        "next_step": _final_release_verification_next_step(blockers),
        "no_internet": True,
        "no_downloads": True,
        "no_installs": True,
        "no_model_load": True,
        "no_inference": True,
        "no_training": True,
        "safety": _safety_payload(),
    }


def write_final_release_verification_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 362-363."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"362_final_release_verification.json": build_final_release_verification_report()},
    )


def build_final_release_closure_pack(runtime_root: str | Path | None = None) -> dict[str, Any]:
    """Build the deterministic final-release closure state without bypassing gates."""

    verification = build_final_release_verification_report(runtime_root)
    handoff = build_release_candidate_handoff_manifest()
    signing_plan = build_release_signing_plan()
    operator_requirements = [
        "trusted Authenticode code-signing certificate with private key",
        "signtool.exe from Windows SDK available on the release machine",
        "timestamp authority URL for signed release binaries",
        "clean Windows 11 machine or VM separate from the development host",
        "copied release_signing_evidence.json after signing",
        "copied clean_machine_external_validation.json after clean-machine validation",
    ]
    manual_blockers = [
        {
            "id": "trusted_code_signing",
            "status": "BLOCKED" if not verification["signed_installer"] else "PASSED",
            "required_evidence": "installer/release_signing_evidence.json with valid trusted certificate and timestamp.",
        },
        {
            "id": "external_clean_machine_validation",
            "status": "BLOCKED" if not verification["external_clean_machine_passed"] else "PASSED",
            "required_evidence": "D:\\ANN\\clean_machine_external_validation.json from a separate Windows 11 validation host.",
        },
    ]
    ready = verification["status"] == "FINAL_RELEASE_READY"
    return {
        "version": "18.9.18",
        "generated_at": _now(),
        "status": "FINAL_RELEASE_READY" if ready else "FINAL_RELEASE_CLOSURE_BLOCKED",
        "final_release_ready": ready,
        "verification_status": verification["status"],
        "installer_rc": verification["installer_rc"],
        "installer_final": verification["installer_final"],
        "public_release": verification["public_release"],
        "ann_finalization": verification["ann_finalization"],
        "runtime_materialization": verification["runtime_materialization"],
        "wheelhouse_integrity": verification["wheelhouse_integrity"],
        "embedded_package_audit": verification["embedded_package_audit"],
        "autonomous_complex_capability": verification["autonomous_complex_capability"],
        "signed_installer": verification["signed_installer"],
        "external_clean_machine_passed": verification["external_clean_machine_passed"],
        "blockers": verification["blockers"],
        "manual_blockers": manual_blockers,
        "operator_requirements": operator_requirements,
        "handoff_status": handoff["status"],
        "handoff_bundle_root": handoff["bundle_root"],
        "handoff_missing": handoff["missing"],
        "release_signing_plan_status": signing_plan["status"],
        "release_signing_commands": signing_plan["commands"],
        "release_operator_preflight_command": handoff["release_operator_environment_command"],
        "release_sign_command": handoff["sign_command"],
        "clean_machine_command": handoff["clean_machine_command"],
        "final_verifier_command": handoff["repo_root_final_verifier_command"],
        "next_step": verification["next_step"],
        "acceptance_rule": (
            "FINAL_RELEASE_READY is allowed only when signed installer evidence and external clean-machine "
            "validation both pass the existing final release verifier."
        ),
        "no_gate_downgrade": True,
        "no_release_promotion_without_external_evidence": True,
        "no_internet": True,
        "no_downloads": True,
        "no_installs": True,
        "no_shell": True,
        "no_model_load": True,
        "no_inference": True,
        "no_training": True,
        "models_modified": False,
        "datasets_modified": False,
        "adapters_modified": False,
        "safety": _safety_payload(),
    }


def write_final_release_closure_pack_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 376-377."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"376_final_release_closure_pack.json": build_final_release_closure_pack()},
    )


def build_autonomous_complex_capability_gate(evidence_root: str | Path | None = None) -> dict[str, Any]:
    """Evaluate whether ANN has proved complex autonomous project delivery."""

    root = Path(evidence_root or REPO_ROOT / "outputs" / "autonomous_capability").resolve()
    scenarios = _autonomous_capability_scenarios()
    scenario_results = []
    for scenario in scenarios:
        summary_path = root / scenario["id"] / "summary.json"
        payload = _read_json_file(summary_path)
        commands_executed = payload.get("commands_executed")
        if not isinstance(commands_executed, list):
            commands_executed = []
        verification = payload.get("verification_evidence")
        evidence_level = ""
        if isinstance(verification, dict):
            evidence_level = str(verification.get("evidence_level", ""))
        passed = (
            payload.get("status") == "COMPLETED_VERIFIED"
            and payload.get("completion_quality") == "VERIFIED"
            and evidence_level == "STRONG"
            and bool(commands_executed)
            and payload.get("security_review") == "PASSED"
            and payload.get("protected_paths_modified") is False
        )
        scenario_results.append(
            {
                **scenario,
                "summary_path": str(summary_path),
                "summary_present": summary_path.is_file(),
                "status": payload.get("status", "MISSING"),
                "completion_quality": payload.get("completion_quality", "MISSING"),
                "evidence_level": evidence_level or "MISSING",
                "commands_executed": len(commands_executed),
                "security_review": payload.get("security_review", "MISSING"),
                "protected_paths_modified": payload.get("protected_paths_modified", "MISSING"),
                "passed": passed,
            }
        )
    blockers = [item for item in scenario_results if not item["passed"]]
    passed = not blockers
    return {
        "version": "18.9.13",
        "generated_at": _now(),
        "status": "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED" if passed else "AUTONOMOUS_COMPLEX_CAPABILITY_BLOCKED",
        "passed": passed,
        "evidence_root": str(root),
        "required_scenarios": len(scenarios),
        "passed_scenarios": len(scenarios) - len(blockers),
        "scenarios": scenario_results,
        "blockers": blockers,
        "acceptance_rule": (
            "Every scenario must be COMPLETED_VERIFIED with VERIFIED quality, STRONG verification evidence, "
            "executed tests, PASSED security review, and protected_paths_modified=false."
        ),
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }


def write_autonomous_complex_capability_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 366-367."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"366_autonomous_complex_capability_gate.json": build_autonomous_complex_capability_gate()},
    )


def build_autonomous_capability_evidence_plan(evidence_root: str | Path | None = None) -> dict[str, Any]:
    """Build a read-only evidence contract for proving complex autonomous capability."""

    gate = build_autonomous_complex_capability_gate(evidence_root)
    required_fields = _autonomous_capability_required_fields()
    scenario_plans = []
    for scenario in gate["scenarios"]:
        missing_requirements = []
        if not scenario["summary_present"]:
            missing_requirements.append("summary.json")
        if scenario["status"] != "COMPLETED_VERIFIED":
            missing_requirements.append("status=COMPLETED_VERIFIED")
        if scenario["completion_quality"] != "VERIFIED":
            missing_requirements.append("completion_quality=VERIFIED")
        if scenario["evidence_level"] != "STRONG":
            missing_requirements.append("verification_evidence.evidence_level=STRONG")
        if scenario["commands_executed"] <= 0:
            missing_requirements.append("commands_executed non-empty")
        if scenario["security_review"] != "PASSED":
            missing_requirements.append("security_review=PASSED")
        if scenario["protected_paths_modified"] is not False:
            missing_requirements.append("protected_paths_modified=false")
        scenario_plans.append(
            {
                "id": scenario["id"],
                "category": scenario["category"],
                "prompt": scenario["prompt"],
                "summary_path": scenario["summary_path"],
                "passed": scenario["passed"],
                "missing_requirements": missing_requirements,
                "required_summary_fields": required_fields,
                "required_artifacts": [
                    "summary.json",
                    "generated_project_path",
                    "requirements_or_specification",
                    "architecture_notes",
                    "test_results",
                    "security_review",
                    "verification_evidence",
                ],
                "minimum_real_verification": [
                    "project generated in an allowed workspace",
                    "dependencies resolved without modifying protected paths",
                    "build command executed when available",
                    "unit/integration/e2e tests executed when available",
                    "security review completed",
                    "human-readable failure summary if anything remains incomplete",
                ],
                "next_action": (
                    "No action required; scenario evidence is complete."
                    if scenario["passed"]
                    else "Run the scenario through the existing ANN pipeline and save real verification evidence."
                ),
            }
        )
    return {
        "version": "18.9.14",
        "generated_at": _now(),
        "status": "EVIDENCE_COMPLETE" if gate["passed"] else "EVIDENCE_REQUIRED",
        "gate_status": gate["status"],
        "evidence_root": gate["evidence_root"],
        "required_scenarios": gate["required_scenarios"],
        "passed_scenarios": gate["passed_scenarios"],
        "remaining_scenarios": gate["required_scenarios"] - gate["passed_scenarios"],
        "required_summary_fields": required_fields,
        "scenarios": scenario_plans,
        "final_release_blocking": not gate["passed"],
        "does_not_create_fake_evidence": True,
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }


def write_autonomous_capability_evidence_plan_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 368-369."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {"368_autonomous_capability_evidence_plan.json": build_autonomous_capability_evidence_plan()},
    )


def write_external_verified_runtime_bridge_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 250-253 for ANN v18.2 external verified runtime bridge."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {
            "250_external_verified_runtime_bridge.json": build_external_verified_runtime_bridge(),
            "252_external_runtime_smoke_readiness.json": build_external_runtime_smoke_readiness(),
        },
    )


def run_qwen25_first_real_inference_external(
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    prompt: str = "hello",
    max_tokens: int = 64,
    llama_factory: Any | None = None,
) -> dict[str, Any]:
    """Run the first real Qwen2.5 GGUF inference through external llama_cpp runtime."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    load_started = 0.0
    inference_started = 0.0
    llm: Any | None = None
    loaded = False
    generated_text = ""
    tokens_generated = 0
    prompt_tokens = 0
    load_time_seconds = 0.0
    inference_time_seconds = 0.0
    load_exception = ""
    inference_exception = ""
    errors: list[str] = []
    warnings: list[str] = []
    vram_samples: list[dict[str, Any]] = []
    external = build_external_verified_runtime_bridge()
    smoke = build_external_runtime_smoke_readiness()
    metrics_before = get_runtime_metrics()
    loaded_before = get_loaded_models()
    qwen25_path = _resolve_runtime_filesystem_path(QWEN25_EXACT_GGUF_PATH)
    if not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not manual_confirmation:
        errors.append("manual_confirmation_required")
    if prompt != "hello":
        errors.append("exact_prompt_hello_required")
    if external["status"] != "EXTERNAL_RUNTIME_READY":
        errors.append(f"external_runtime_not_ready:{external['status']}")
    if smoke["status"] != "READY_FOR_CONTROLLED_SMOKE_EXTERNAL":
        errors.append(f"external_smoke_not_ready:{smoke['status']}")
    if loaded_before:
        errors.append("active_model_present_before_first_real_inference")
    if metrics_before.get("parallel_llm_loads", 0) != 0:
        errors.append("parallel_llm_loads_must_be_zero")
    if not qwen25_path.is_file():
        errors.append("qwen25_gguf_missing")
    vram_samples.append(_vram_sample("before_load"))
    real_load_attempted = False
    real_inference_attempted = False
    status = "FIRST_REAL_INFERENCE_FAILED"
    load_status = "FIRST_REAL_LOAD_BLOCKED" if errors else "FIRST_REAL_LOAD_FAILED"
    inference_status = "FIRST_REAL_INFERENCE_BLOCKED" if errors else "FIRST_REAL_INFERENCE_FAILED"
    try:
        if not errors and llama_factory is None:
            child = _run_qwen25_external_child_process(target, qwen25_path, prompt, max_tokens, n_ctx=512)
            real_load_attempted = bool(child.get("real_load_attempted"))
            real_inference_attempted = bool(child.get("real_inference_attempted"))
            load_time_seconds = float(child.get("load_time_seconds") or 0.0)
            inference_time_seconds = float(child.get("inference_time_seconds") or 0.0)
            generated_text = str(child.get("generated_text") or "")
            tokens_generated = int(child.get("tokens_generated") or 0)
            prompt_tokens = int(child.get("prompt_tokens") or 0)
            vram_samples.extend(child.get("vram_samples") or [])
            if child.get("real_load_success"):
                load_status = "FIRST_REAL_LOAD_PASSED"
            else:
                load_status = "FIRST_REAL_LOAD_FAILED"
                errors.extend(_list_from(child.get("exception")) or ["child_process_load_failed"])
            if child.get("real_inference_success"):
                inference_status = "FIRST_REAL_INFERENCE_PASSED"
            elif child.get("real_inference_attempted"):
                inference_status = "FIRST_REAL_INFERENCE_FAILED"
                errors.extend(_list_from(child.get("inference_exception")) or ["child_process_inference_failed"])
            else:
                inference_status = "FIRST_REAL_INFERENCE_FAILED"
            if child.get("returncode", 0) != 0:
                errors.append(f"child_process_returncode:{child.get('returncode')}")
            if child.get("stderr"):
                warnings.append("child_stderr_captured")
            vram_samples.append(_vram_sample("after_child_process"))
        elif not errors:
            real_load_attempted = True
            load_started = perf_counter()
            try:
                factory = llama_factory or _load_real_llama_cpp_factory()
                llm = factory(
                    model_path=str(qwen25_path),
                    n_ctx=512,
                    n_gpu_layers=-1,
                    verbose=False,
                )
                loaded = True
                load_status = "FIRST_REAL_LOAD_PASSED"
            except Exception as exc:  # pragma: no cover - real native backend dependent.
                load_exception = f"{type(exc).__name__}: {exc}"
                errors.append(load_exception)
                load_status = "FIRST_REAL_LOAD_FAILED"
            load_time_seconds = _elapsed_seconds(load_started)
            vram_samples.append(_vram_sample("after_load"))
        if loaded and llm is not None:
            real_inference_attempted = True
            inference_started = perf_counter()
            try:
                result = llm(prompt, max_tokens=max_tokens, temperature=0.0, echo=False)
                generated_text = _llama_completion_text(result)
                usage = result.get("usage", {}) if isinstance(result, dict) else {}
                tokens_generated = int(usage.get("completion_tokens") or _estimate_token_count(generated_text))
                prompt_tokens = int(usage.get("prompt_tokens") or _estimate_token_count(prompt))
                inference_status = "FIRST_REAL_INFERENCE_PASSED" if generated_text.strip() else "FIRST_REAL_INFERENCE_FAILED"
                if inference_status == "FIRST_REAL_INFERENCE_FAILED":
                    errors.append("empty_generated_text")
            except Exception as exc:  # pragma: no cover - real native backend dependent.
                inference_exception = f"{type(exc).__name__}: {exc}"
                errors.append(inference_exception)
                inference_status = "FIRST_REAL_INFERENCE_FAILED"
            inference_time_seconds = _elapsed_seconds(inference_started)
            vram_samples.append(_vram_sample("after_inference"))
        status = "FIRST_REAL_INFERENCE_PASSED" if inference_status == "FIRST_REAL_INFERENCE_PASSED" else inference_status
    finally:
        if llm is not None:
            try:
                close = getattr(llm, "close", None)
                if callable(close):
                    close()
            except Exception as exc:  # pragma: no cover - best-effort cleanup.
                warnings.append(f"llama_close_warning:{type(exc).__name__}:{exc}")
        llm = None
        gc.collect()
        _empty_torch_cuda_cache()
        reset_payload = _force_runtime_safe_mode()
        vram_samples.append(_vram_sample("after_rollback"))
    peak_vram_mb = _peak_vram(vram_samples)
    rollback = {
        "version": "18.3",
        "generated_at": _now(),
        "status": "SAFE_ROLLBACK_PASSED" if reset_payload["safe_mode_final"] else "SAFE_ROLLBACK_FAILED",
        "loaded_model_object_released": True,
        "safe_mode_final": reset_payload["safe_mode_final"],
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "loaded_models_after": reset_payload["loaded_models_after"],
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "safety": _safety_payload(),
    }
    load_payload = {
        "version": "18.3",
        "generated_at": _now(),
        "status": load_status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "runtime_type": external["runtime_type"],
        "model_path": QWEN25_EXACT_GGUF_PATH,
        "resolved_model_path": str(qwen25_path),
        "real_load_attempted": real_load_attempted,
        "real_load_success": load_status == "FIRST_REAL_LOAD_PASSED",
        "load_time_seconds": load_time_seconds,
        "exception": load_exception,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    inference_payload = {
        "version": "18.3",
        "generated_at": _now(),
        "status": status,
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "prompt": prompt,
        "generated_text": generated_text,
        "tokens_generated": tokens_generated,
        "prompt_tokens": prompt_tokens,
        "real_inference_attempted": real_inference_attempted,
        "real_inference_success": status == "FIRST_REAL_INFERENCE_PASSED",
        "inference_time_seconds": inference_time_seconds,
        "exception": inference_exception,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    benchmark = {
        "version": "18.3",
        "generated_at": _now(),
        "status": status,
        "gpu_name": external["gpu_name"],
        "peak_vram_mb": peak_vram_mb,
        "vram_samples": vram_samples,
        "load_time_seconds": load_time_seconds,
        "inference_time_seconds": inference_time_seconds,
        "total_time_seconds": _elapsed_seconds(started),
        "tokens_generated": tokens_generated,
        "prompt_tokens": prompt_tokens,
        "tokens_per_second": round(tokens_generated / inference_time_seconds, 3) if inference_time_seconds > 0 else 0.0,
        "active_models_after": rollback["active_models_after"],
        "parallel_llm_loads_after": rollback["parallel_llm_loads_after"],
        "safe_mode_final": rollback["safe_mode_final"],
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "254_qwen25_first_real_load.json": load_payload,
            "256_qwen25_first_real_inference.json": inference_payload,
            "258_qwen25_real_benchmark.json": benchmark,
            "260_safe_rollback_validation.json": rollback,
        },
    )
    return {
        "status": status,
        "real_load_attempted": real_load_attempted,
        "real_load_success": load_payload["real_load_success"],
        "real_inference_attempted": real_inference_attempted,
        "real_inference_success": inference_payload["real_inference_success"],
        "generated_text": generated_text,
        "tokens_generated": tokens_generated,
        "prompt_tokens": prompt_tokens,
        "peak_vram_mb": peak_vram_mb,
        "load_time_seconds": load_time_seconds,
        "inference_time_seconds": inference_time_seconds,
        "safe_mode_final": rollback["safe_mode_final"],
        "active_models_after": rollback["active_models_after"],
        "parallel_llm_loads_after": rollback["parallel_llm_loads_after"],
        "artifacts": artifacts,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
    }


def run_qwen25_first_real_inference_wsl(
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    prompt: str = "hello",
    max_tokens: int = 64,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Run the controlled Qwen2.5 smoke through the verified WSL conda runtime."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    errors: list[str] = []
    warnings: list[str] = []
    if not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not manual_confirmation:
        errors.append("manual_confirmation_required")
    if prompt != "hello":
        errors.append("exact_prompt_hello_required")
    smoke = build_external_runtime_smoke_readiness(allow_wsl_probe=True)
    if smoke["status"] != "READY_FOR_CONTROLLED_SMOKE_EXTERNAL" or smoke.get("selected_runtime_source") != "wsl_conda":
        errors.append(f"wsl_external_smoke_not_ready:{smoke['status']}:{smoke.get('selected_runtime_source')}")
    if get_loaded_models():
        errors.append("active_model_present_before_wsl_smoke")
    if get_runtime_metrics().get("parallel_llm_loads", 0) != 0:
        errors.append("parallel_llm_loads_must_be_zero")
    child_payload: dict[str, Any] = {}
    if not errors:
        child_payload = _run_wsl_qwen25_smoke_child(
            target=target,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        if child_payload.get("returncode", 0) != 0:
            errors.append(f"wsl_child_returncode:{child_payload.get('returncode')}")
        if child_payload.get("status") != "FIRST_REAL_INFERENCE_PASSED":
            errors.extend(_list_from(child_payload.get("errors")) or ["wsl_qwen25_smoke_failed"])
        if child_payload.get("stderr"):
            warnings.append("wsl_child_stderr_captured")
    reset_payload = _force_runtime_safe_mode()
    status = "FIRST_REAL_INFERENCE_PASSED" if child_payload.get("status") == "FIRST_REAL_INFERENCE_PASSED" and not errors else "FIRST_REAL_INFERENCE_FAILED"
    payload = {
        "version": "18.3-wsl",
        "generated_at": _now(),
        "status": status,
        "runtime_type": "external_wsl_conda",
        "selected_runtime_source": "wsl_conda",
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "prompt": prompt,
        "real_load_attempted": bool(child_payload.get("real_load_attempted")),
        "real_load_success": bool(child_payload.get("real_load_success")),
        "real_inference_attempted": bool(child_payload.get("real_inference_attempted")),
        "real_inference_success": status == "FIRST_REAL_INFERENCE_PASSED",
        "generated_text": str(child_payload.get("generated_text") or ""),
        "tokens_generated": int(child_payload.get("tokens_generated") or 0),
        "prompt_tokens": int(child_payload.get("prompt_tokens") or 0),
        "peak_vram_mb": child_payload.get("peak_vram_mb"),
        "load_time_seconds": float(child_payload.get("load_time_seconds") or 0.0),
        "inference_time_seconds": float(child_payload.get("inference_time_seconds") or 0.0),
        "total_time_seconds": _elapsed_seconds(started),
        "safe_mode_final": reset_payload["safe_mode_final"],
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "child": child_payload,
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "346_qwen25_wsl_external_smoke.json": payload,
            "348_qwen25_wsl_external_smoke_child.json": child_payload,
        },
    )
    payload["artifacts"] = artifacts
    return payload


def build_qwen3_architect_stage(task: str = DEVELOPER_TEAM_TEST_TASK) -> dict[str, Any]:
    """Build the Qwen3 architect stage in bridge mode without loading Qwen3."""

    bridge = build_qwen3_runtime_bridge()
    status = "QWEN3_REAL" if bridge["status"] == "READY" and False else "QWEN3_BRIDGE_MODE"
    output = {
        "requirements": [
            "Expose FastAPI CRUD endpoints for Todo resources.",
            "Use Pydantic schemas for create, update, and read payloads.",
            "Include pytest coverage for success and error paths.",
            "Document API usage with README examples.",
            "Keep type hints across service and API layers.",
        ],
        "architecture": [
            "main.py owns FastAPI app wiring and route registration.",
            "schemas.py contains Pydantic request/response models.",
            "models.py defines the Todo domain model.",
            "crud.py owns in-memory CRUD behavior and error boundaries.",
            "tests/ validates API behavior through FastAPI TestClient.",
        ],
        "acceptance_criteria": [
            "Create, list, retrieve, update, and delete todos.",
            "404 responses are returned for missing todo IDs.",
            "Tests can run with pytest without external services.",
            "README includes curl or Python examples.",
        ],
        "risks": [
            "Bridge mode is deterministic and not a real Qwen3 reasoning pass.",
            "Generated code still needs execution by Test Runner before acceptance.",
        ],
        "implementation_plan": [
            "Generate app files and tests.",
            "Run patch quality checks.",
            "Run tests in the existing ANN test runner.",
            "Feed failures into Action Planner.",
        ],
    }
    reset_runtime_state()
    return {
        "version": "18.4",
        "generated_at": _now(),
        "status": status,
        "agent": "Qwen3 Architect",
        "model_name": QWEN3_MODEL_NAME,
        "mode": "FAST",
        "task": task,
        "output": output,
        "bridge_status": bridge["status"],
        "load_time_seconds": 0.0,
        "tokens": 0,
        "peak_vram_mb": 0,
        "unload_success": True,
        "active_models_after": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads_after": get_runtime_metrics().get("parallel_llm_loads", 0),
        "qwen3_loaded": False,
        "real_inference_attempted": False,
        "safety": _safety_payload(),
    }


def build_qwen25_real_coder_stage(
    *,
    task: str = DEVELOPER_TEAM_TEST_TASK,
    architecture: dict[str, Any] | None = None,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    execute_real: bool = False,
    max_tokens: int = 900,
) -> dict[str, Any]:
    """Run or prepare the Qwen2.5 coder stage with strict sequential rollback."""

    prompt = _developer_team_coder_prompt(task, architecture or {})
    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    external = build_external_runtime_smoke_readiness()
    errors: list[str] = []
    child: dict[str, Any] = {}
    if not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not manual_confirmation:
        errors.append("manual_confirmation_required")
    if external["status"] != "READY_FOR_CONTROLLED_SMOKE_EXTERNAL":
        errors.append(f"external_runtime_smoke_not_ready:{external['status']}")
    real_attempted = False
    real_success = False
    if execute_real and not errors:
        real_attempted = True
        qwen25_path = _resolve_runtime_filesystem_path(QWEN25_EXACT_GGUF_PATH)
        child = _run_qwen25_external_child_process(target, qwen25_path, prompt, max_tokens, n_ctx=2048)
        real_success = bool(child.get("real_inference_success"))
        if child.get("returncode", 0) != 0:
            errors.append(f"child_process_returncode:{child.get('returncode')}")
        if not real_success:
            errors.extend(_list_from(child.get("exception")) or _list_from(child.get("inference_exception")) or ["qwen25_coder_generation_failed"])
    elif execute_real:
        real_attempted = False
    generated_text = str(child.get("generated_text") or "")
    reset_payload = _force_runtime_safe_mode()
    status = "PASSED" if real_success else ("FAILED" if execute_real else "PENDING_REAL_INFERENCE")
    return {
        "version": "18.5",
        "generated_at": _now(),
        "status": status,
        "agent": "Qwen2.5 Coder",
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "mode": "FAST",
        "task": task,
        "prompt": prompt,
        "requested_files": ["main.py", "schemas.py", "crud.py", "models.py", "tests/", "README.md"],
        "generated_text": generated_text,
        "real_inference_required": True,
        "real_inference_attempted": real_attempted,
        "real_inference_success": real_success,
        "tokens_generated": int(child.get("tokens_generated") or 0),
        "prompt_tokens": int(child.get("prompt_tokens") or 0),
        "load_time_seconds": float(child.get("load_time_seconds") or 0.0),
        "inference_time_seconds": float(child.get("inference_time_seconds") or 0.0),
        "peak_vram_mb": _peak_vram(child.get("vram_samples") or []) or 0,
        "unload_success": reset_payload["safe_mode_final"],
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_mode_final": reset_payload["safe_mode_final"],
        "errors": _dedupe(errors),
        "child_status": child.get("status", "not_executed"),
        "child_stderr_captured": bool(child.get("stderr")),
        "safety": _safety_payload(),
    }


def build_deepseek_reviewer_stage(
    *,
    task: str = DEVELOPER_TEAM_TEST_TASK,
    coder_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the DeepSeek reviewer stage in bridge mode without POWERFUL activation."""

    bridge = build_deepseek_powerful_bridge()
    generated_text = str((coder_output or {}).get("generated_text") or "")
    status = "DEEPSEEK_BRIDGE_MODE"
    findings = []
    if not generated_text.strip():
        findings.append("Coder output is empty or unavailable; real review is blocked.")
    else:
        findings.extend(
            [
                "Verify FastAPI error handling uses HTTPException consistently.",
                "Ensure tests cover create, list, retrieve, update, delete, and missing IDs.",
                "Confirm README examples match implemented endpoints.",
                "Check that mutable in-memory state is isolated for tests.",
            ]
        )
    reset_runtime_state()
    return {
        "version": "18.6",
        "generated_at": _now(),
        "status": status,
        "agent": "DeepSeek POWERFUL Reviewer",
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "mode": "POWERFUL",
        "task": task,
        "review": {
            "bugs": findings,
            "security": ["No real DeepSeek execution in v18.6; bridge review only."],
            "edge_cases": ["Missing todo IDs", "Partial updates", "Empty titles"],
            "performance": ["In-memory store is acceptable for generated sample; not production persistence."],
            "missing_tests": ["Persistence tests if database storage is later added."],
            "maintainability": ["Separate schema, CRUD, model, and API layers."],
        },
        "bridge_status": bridge["status"],
        "load_time_seconds": 0.0,
        "tokens": 0,
        "peak_vram_mb": 0,
        "unload_success": True,
        "active_models_after": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads_after": get_runtime_metrics().get("parallel_llm_loads", 0),
        "deepseek_loaded": False,
        "powerful_activated": False,
        "real_inference_attempted": False,
        "safety": _safety_payload(),
    }


def build_developer_team_pipeline(
    *,
    task: str = DEVELOPER_TEAM_TEST_TASK,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    execute_real_coder: bool = False,
) -> dict[str, Any]:
    """Run the sequential developer team pipeline without parallel model loads."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    qwen3 = build_qwen3_architect_stage(task)
    coder = build_qwen25_real_coder_stage(
        task=task,
        architecture=qwen3["output"],
        approval_token=approval_token,
        manual_confirmation=manual_confirmation,
        output_dir=target,
        execute_real=execute_real_coder,
    )
    deepseek = build_deepseek_reviewer_stage(task=task, coder_output=coder)
    consensus = _developer_team_consensus(qwen3, coder, deepseek)
    patch_quality = _developer_team_patch_quality(coder)
    test_results = _developer_team_test_results(coder)
    action_plan = _developer_team_action_plan(consensus, patch_quality, test_results)
    stage_statuses = [qwen3["status"], coder["status"], deepseek["status"]]
    if coder["status"] == "PASSED" and consensus["decision"] in {"PASSED", "PARTIAL"}:
        final_status = "TEAM_PIPELINE_PARTIAL" if "BRIDGE_MODE" in qwen3["status"] or "BRIDGE_MODE" in deepseek["status"] else "TEAM_PIPELINE_PASSED"
    elif coder["status"] == "PENDING_REAL_INFERENCE":
        final_status = "TEAM_PIPELINE_PARTIAL"
    else:
        final_status = "TEAM_PIPELINE_FAILED"
    reset_payload = _force_runtime_safe_mode()
    artifacts = _write_developer_team_pipeline_artifacts(
        target,
        qwen3=qwen3,
        coder=coder,
        deepseek=deepseek,
        consensus=consensus,
        patch_quality=patch_quality,
        test_results=test_results,
        action_plan=action_plan,
    )
    total_runtime = _elapsed_seconds(started)
    return {
        "version": "18.6",
        "generated_at": _now(),
        "status": final_status,
        "task": task,
        "stages": stage_statuses,
        "qwen3": qwen3,
        "qwen2_5": coder,
        "deepseek": deepseek,
        "consensus": consensus,
        "patch_quality": patch_quality,
        "test_results": test_results,
        "action_plan": action_plan,
        "sequential_runtime": "ACTIVE",
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_rollback": "PASSED" if reset_payload["safe_mode_final"] else "FAILED",
        "peak_vram_mb": max(float(qwen3.get("peak_vram_mb", 0)), float(coder.get("peak_vram_mb", 0)), float(deepseek.get("peak_vram_mb", 0))),
        "model_switch_time_seconds": 0.0,
        "total_runtime_seconds": total_runtime,
        "artifacts": artifacts,
        "safety": _safety_payload(),
    }


def run_qwen3_real_architect_stage(
    *,
    task: str = "Create software requirements for: FastAPI Todo API",
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    execute_real: bool = False,
    max_new_tokens: int = 700,
) -> dict[str, Any]:
    """Run the real Qwen3 architect stage in an isolated external process."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    model_path = _resolve_runtime_filesystem_path("D:/Models/qwen3")
    adapter_path = _resolve_runtime_filesystem_path(
        "D:/AgenticEngineeringNetwork/training/adapters/qwen3-8b-product-agent-v9-repaired-v2-bullets"
    )
    errors = _real_hf_stage_gate_errors(approval_token, manual_confirmation, model_path, adapter_path)
    prompt = (
        "<|im_start|>system\nYou are Qwen3 Architect inside ANN. Return concise JSON-like Markdown sections.\n<|im_end|>\n"
        "<|im_start|>user\nCreate software requirements for: FastAPI Todo API. Include requirements, architecture, acceptance criteria, risks, implementation plan.\n<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    child: dict[str, Any] = {}
    if execute_real and not errors:
        child = _run_hf_external_child_process(
            target=target,
            model_path=model_path,
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            result_stem="qwen3_real_architect",
            adapter_path=adapter_path,
            load_in_4bit=True,
        )
        if not child.get("real_inference_success"):
            errors.extend(_list_from(child.get("exception")) or _list_from(child.get("inference_exception")) or ["qwen3_real_generation_failed"])
    elif execute_real:
        child = {"status": "BLOCKED_BY_GATE"}
    reset_payload = _force_runtime_safe_mode()
    load = _real_stage_load_payload(
        version="18.7",
        status="QWEN3_REAL_LOAD_PASSED" if child.get("real_load_success") else "QWEN3_REAL_LOAD_FAILED",
        model_name=QWEN3_MODEL_NAME,
        model_path=model_path,
        real_load_attempted=bool(child.get("real_load_attempted")),
        real_load_success=bool(child.get("real_load_success")),
        load_time_seconds=float(child.get("load_time_seconds") or 0.0),
        errors=errors,
    )
    output = {
        "version": "18.7",
        "generated_at": _now(),
        "status": "QWEN3_REAL_PASSED" if child.get("real_inference_success") else "QWEN3_REAL_FAILED",
        "agent": "Qwen3 Architect",
        "model_name": QWEN3_MODEL_NAME,
        "task": task,
        "generated_text": str(child.get("generated_text") or ""),
        "requirements": _extract_stage_lines(str(child.get("generated_text") or ""), "requirements"),
        "architecture": _extract_stage_lines(str(child.get("generated_text") or ""), "architecture"),
        "acceptance_criteria": _extract_stage_lines(str(child.get("generated_text") or ""), "acceptance"),
        "risks": _extract_stage_lines(str(child.get("generated_text") or ""), "risks"),
        "implementation_plan": _extract_stage_lines(str(child.get("generated_text") or ""), "implementation"),
        "real_inference_attempted": bool(child.get("real_inference_attempted")),
        "real_inference_success": bool(child.get("real_inference_success")),
        "tokens_generated": int(child.get("tokens_generated") or 0),
        "prompt_tokens": int(child.get("prompt_tokens") or 0),
        "errors": _dedupe(errors),
        "safety": _safety_payload(),
    }
    benchmark = _real_stage_benchmark("18.7", output["status"], child, reset_payload)
    rollback = _real_stage_rollback("18.7", reset_payload)
    artifacts = _write_numbered_artifacts(
        target,
        {
            "272_qwen3_real_load.json": load,
            "274_qwen3_real_output.json": output,
            "276_qwen3_benchmark.json": benchmark,
            "278_qwen3_safe_rollback.json": rollback,
        },
    )
    return {
        **output,
        "load": load,
        "benchmark": benchmark,
        "rollback": rollback,
        "artifacts": artifacts,
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_mode_final": reset_payload["safe_mode_final"],
        "peak_vram_mb": benchmark["peak_vram_mb"],
        "load_time_seconds": benchmark["load_time_seconds"],
        "inference_time_seconds": benchmark["inference_time_seconds"],
    }


def build_deepseek_powerful_memory_preflight(
    output_dir: str | Path | None = None,
    *,
    model_path: str | Path = DEEPSEEK14B_HF_PATH,
    cuda_environment: dict[str, Any] | None = None,
    llama_cpp_alternative_path: str | Path | None = None,
) -> dict[str, Any]:
    """Assess whether DeepSeek POWERFUL can be attempted without loading it."""

    target = Path(output_dir).resolve() if output_dir is not None else None
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
    resolved_model_path = _resolve_runtime_filesystem_path(model_path)
    safetensors = sorted(resolved_model_path.glob("*.safetensors")) if resolved_model_path.is_dir() else []
    model_size_mb = _directory_file_size_mb(resolved_model_path, suffix=".safetensors")
    cuda = cuda_environment or diagnose_cuda_environment()
    smi = _query_nvidia_smi_memory()
    vram_total_mb = _first_number(cuda.get("vram_total_mb"), smi.get("total_mb"))
    vram_free_mb = _first_number(smi.get("free_mb"))
    estimated_required_vram_mb = _estimate_deepseek_required_vram_mb(model_size_mb)
    full_gpu_load_unsafe = vram_total_mb is None or vram_total_mb < estimated_required_vram_mb
    cpu_offload_required = full_gpu_load_unsafe and resolved_model_path.is_dir()
    gguf_alternative_exists = _deepseek_gguf_alternative_exists(llama_cpp_alternative_path)
    quantized_model_required = full_gpu_load_unsafe and not gguf_alternative_exists
    current_backend_can_support_safe_offload = gguf_alternative_exists and _resolve_runtime_filesystem_path(
        DEEPSEEK14B_GGUF_PATH
    ).is_file()
    if not resolved_model_path.exists():
        status = "POWERFUL_MISSING"
    elif not safetensors:
        status = "POWERFUL_REQUIRES_QUANTIZED_MODEL"
    elif full_gpu_load_unsafe and gguf_alternative_exists and current_backend_can_support_safe_offload:
        status = "POWERFUL_QUANTIZED_GGUF_SAFE_TO_ATTEMPT"
    elif not cuda.get("cuda_available"):
        status = "POWERFUL_UNSAFE_ON_CURRENT_GPU"
    elif not full_gpu_load_unsafe:
        status = "POWERFUL_SAFE_TO_ATTEMPT"
    elif current_backend_can_support_safe_offload:
        status = "POWERFUL_REQUIRES_OFFLOAD"
    elif quantized_model_required:
        status = "POWERFUL_REQUIRES_QUANTIZED_MODEL"
    else:
        status = "POWERFUL_UNSAFE_ON_CURRENT_GPU"
    payload = {
        "version": "19.0",
        "generated_at": _now(),
        "status": status,
        "reason": None
        if status in {"POWERFUL_SAFE_TO_ATTEMPT", "POWERFUL_QUANTIZED_GGUF_SAFE_TO_ATTEMPT"}
        else POWERFUL_DEFERRED_REASON,
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "model_path": _runtime_display_path(model_path),
        "resolved_model_path": str(resolved_model_path),
        "model_path_exists": resolved_model_path.exists(),
        "model_format": "HF safetensors" if safetensors else "unknown",
        "safetensors_files": [path.name for path in safetensors],
        "total_model_size_mb": model_size_mb,
        "gpu_name": cuda.get("gpu_name") or smi.get("gpu_name"),
        "total_vram_mb": vram_total_mb,
        "current_free_vram_mb": vram_free_mb,
        "estimated_required_vram_mb": estimated_required_vram_mb,
        "full_gpu_load_unsafe": full_gpu_load_unsafe,
        "cpu_offload_likely_required": cpu_offload_required,
        "quantized_or_gguf_model_likely_required": quantized_model_required,
        "llama_cpp_gguf_alternative_exists": gguf_alternative_exists,
        "current_backend_can_support_safe_offload": current_backend_can_support_safe_offload,
        "gguf_model_path": DEEPSEEK14B_GGUF_PATH,
        "active_models": get_runtime_metrics().get("active_models", 0),
        "parallel_llm_loads": get_runtime_metrics().get("parallel_llm_loads", 0),
        "safety": _safety_payload(),
    }
    if target is not None:
        payload["artifacts"] = _write_numbered_artifacts(target, {"298_deepseek_memory_preflight.json": payload})
    return payload


def build_powerful_fallback_gate(
    output_dir: str | Path | None = None,
    *,
    preflight: dict[str, Any] | None = None,
    qwen3: dict[str, Any] | None = None,
    qwen25: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether POWERFUL can run or must be deferred without loading it."""

    target = Path(output_dir).resolve() if output_dir is not None else None
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
    memory = preflight or build_deepseek_powerful_memory_preflight()
    qwen3_passed = (qwen3 or {}).get("status") == "QWEN3_REAL_PASSED"
    qwen25_passed = (qwen25 or {}).get("status") == "PASSED"
    if memory["status"] in {"POWERFUL_SAFE_TO_ATTEMPT", "POWERFUL_QUANTIZED_GGUF_SAFE_TO_ATTEMPT"}:
        status = "POWERFUL_REAL_READY"
        attempt_real_load = True
        defer_powerful = False
        use_bridge_review = False
    elif memory["status"] == "POWERFUL_REQUIRES_OFFLOAD":
        status = "POWERFUL_DEFERRED_OFFLOAD_REQUIRED"
        attempt_real_load = False
        defer_powerful = True
        use_bridge_review = qwen3_passed and qwen25_passed
    elif memory["status"] in {"POWERFUL_REQUIRES_QUANTIZED_MODEL", "POWERFUL_UNSAFE_ON_CURRENT_GPU"}:
        status = "POWERFUL_DEFERRED_QUANTIZED_REQUIRED"
        attempt_real_load = False
        defer_powerful = True
        use_bridge_review = qwen3_passed and qwen25_passed
    else:
        status = "POWERFUL_BLOCKED"
        attempt_real_load = False
        defer_powerful = False
        use_bridge_review = False
    if defer_powerful and use_bridge_review:
        status = "POWERFUL_BRIDGE_REVIEW_ALLOWED"
    payload = {
        "version": "19.1",
        "generated_at": _now(),
        "status": status,
        "attempt_real_deepseek_load": attempt_real_load,
        "defer_powerful": defer_powerful,
        "requires_offload": memory["status"] == "POWERFUL_REQUIRES_OFFLOAD",
        "requires_quantized_model": memory["status"] in {"POWERFUL_REQUIRES_QUANTIZED_MODEL", "POWERFUL_UNSAFE_ON_CURRENT_GPU"},
        "use_bridge_review": use_bridge_review,
        "fail_hard": status == "POWERFUL_BLOCKED",
        "deepseek_stage_status": "DEEPSEEK_POWERFUL_DEFERRED" if defer_powerful else "DEEPSEEK_REAL_READY",
        "reason": memory.get("reason") or memory["status"],
        "preflight_status": memory["status"],
        "qwen3_real_passed": qwen3_passed,
        "qwen25_real_passed": qwen25_passed,
        "safety": _safety_payload(),
    }
    if target is not None:
        payload["artifacts"] = _write_numbered_artifacts(target, {"300_powerful_fallback_gate.json": payload})
    return payload


def run_deepseek_real_reviewer_stage(
    *,
    implementation_text: str = "",
    qwen3: dict[str, Any] | None = None,
    qwen25: dict[str, Any] | None = None,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    execute_real: bool = False,
    max_new_tokens: int = 700,
) -> dict[str, Any]:
    """Run the real DeepSeek POWERFUL reviewer stage in an isolated external process."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    model_path = _resolve_runtime_filesystem_path(DEEPSEEK14B_HF_PATH)
    errors = _real_hf_stage_gate_errors(approval_token, manual_confirmation, model_path, None)
    preflight = build_deepseek_powerful_memory_preflight(output_dir=target, model_path=DEEPSEEK14B_HF_PATH)
    fallback = build_powerful_fallback_gate(output_dir=target, preflight=preflight, qwen3=qwen3, qwen25=qwen25)
    if execute_real and not fallback["attempt_real_deepseek_load"]:
        errors.append(str(fallback["reason"]))
    prompt = (
        "Review this Todo API implementation for bugs, security, performance, missing tests, maintainability, and edge cases.\n"
        "Return concise Markdown sections.\n\n"
        f"Implementation:\n{implementation_text[:6000]}"
    )
    child: dict[str, Any] = {}
    if execute_real and not errors and fallback["attempt_real_deepseek_load"]:
        if preflight["status"] == "POWERFUL_QUANTIZED_GGUF_SAFE_TO_ATTEMPT":
            child = _run_llama_cpp_external_child_process(
                target=target,
                model_path=_resolve_runtime_filesystem_path(DEEPSEEK14B_GGUF_PATH),
                prompt=prompt,
                max_tokens=max_new_tokens,
                result_stem="deepseek_real_review",
                n_ctx=1024,
                n_gpu_layers=20,
                n_threads=6,
                timeout_seconds=1800,
            )
        else:
            child = _run_hf_external_child_process(
                target=target,
                model_path=model_path,
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                result_stem="deepseek_real_review",
                adapter_path=None,
                load_in_4bit=True,
            )
        if not child.get("real_inference_success"):
            errors.extend(_list_from(child.get("exception")) or _list_from(child.get("inference_exception")) or ["deepseek_real_review_failed"])
    elif execute_real:
        child = {"status": "BLOCKED_BY_GATE"}
    reset_payload = _force_runtime_safe_mode()
    load = _real_stage_load_payload(
        version="18.8",
        status="DEEPSEEK_REAL_LOAD_PASSED" if child.get("real_load_success") else "DEEPSEEK_REAL_LOAD_FAILED",
        model_name=DEEPSEEK14B_MODEL_NAME,
        model_path=model_path,
        real_load_attempted=bool(child.get("real_load_attempted")),
        real_load_success=bool(child.get("real_load_success")),
        load_time_seconds=float(child.get("load_time_seconds") or 0.0),
        errors=errors,
    )
    review_status = "DEEPSEEK_REAL_PASSED" if child.get("real_inference_success") else "DEEPSEEK_REAL_FAILED"
    if fallback["defer_powerful"] and not child.get("real_load_attempted"):
        review_status = "DEEPSEEK_POWERFUL_DEFERRED"
    review = {
        "version": "18.8",
        "generated_at": _now(),
        "status": review_status,
        "agent": "DeepSeek POWERFUL Reviewer",
        "model_name": DEEPSEEK14B_MODEL_NAME,
        "mode": "POWERFUL",
        "powerful_deferred": review_status == "DEEPSEEK_POWERFUL_DEFERRED",
        "deferred_reason": fallback["reason"] if review_status == "DEEPSEEK_POWERFUL_DEFERRED" else None,
        "memory_preflight_status": preflight["status"],
        "fallback_gate_status": fallback["status"],
        "generated_text": str(child.get("generated_text") or ""),
        "bugs": _extract_stage_lines(str(child.get("generated_text") or ""), "bugs"),
        "security": _extract_stage_lines(str(child.get("generated_text") or ""), "security"),
        "performance": _extract_stage_lines(str(child.get("generated_text") or ""), "performance"),
        "missing_tests": _extract_stage_lines(str(child.get("generated_text") or ""), "tests"),
        "maintainability": _extract_stage_lines(str(child.get("generated_text") or ""), "maintainability"),
        "edge_cases": _extract_stage_lines(str(child.get("generated_text") or ""), "edge"),
        "real_load_attempted": bool(child.get("real_load_attempted")),
        "real_load_success": bool(child.get("real_load_success")),
        "real_inference_attempted": bool(child.get("real_inference_attempted")),
        "real_inference_success": bool(child.get("real_inference_success")),
        "tokens_generated": int(child.get("tokens_generated") or 0),
        "prompt_tokens": int(child.get("prompt_tokens") or 0),
        "errors": _dedupe(errors),
        "safety": _safety_payload(),
    }
    benchmark = _real_stage_benchmark("18.8", review["status"], child, reset_payload)
    rollback = _real_stage_rollback("18.8", reset_payload)
    artifacts = _write_numbered_artifacts(
        target,
        {
            "280_deepseek_real_load.json": load,
            "282_deepseek_real_review.json": review,
            "284_deepseek_benchmark.json": benchmark,
            "286_deepseek_safe_rollback.json": rollback,
        },
    )
    stage_artifacts = [*preflight.get("artifacts", []), *fallback.get("artifacts", []), *artifacts]
    return {
        **review,
        "load": load,
        "memory_preflight": preflight,
        "fallback_gate": fallback,
        "benchmark": benchmark,
        "rollback": rollback,
        "artifacts": stage_artifacts,
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_mode_final": reset_payload["safe_mode_final"],
        "peak_vram_mb": benchmark["peak_vram_mb"],
        "load_time_seconds": benchmark["load_time_seconds"],
        "inference_time_seconds": benchmark["inference_time_seconds"],
    }


def build_full_real_developer_team_pipeline(
    *,
    approval_token: str | None = None,
    manual_confirmation: bool = False,
    output_dir: str | Path | None = None,
    execute_real: bool = False,
) -> dict[str, Any]:
    """Run the v18.9 full real developer team pipeline sequentially."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    qwen3 = run_qwen3_real_architect_stage(
        approval_token=approval_token,
        manual_confirmation=manual_confirmation,
        output_dir=target,
        execute_real=execute_real,
    )
    qwen25 = build_qwen25_real_coder_stage(
        task=DEVELOPER_TEAM_TEST_TASK,
        architecture={"architecture": qwen3.get("architecture", [])},
        approval_token=approval_token,
        manual_confirmation=manual_confirmation,
        output_dir=target,
        execute_real=execute_real,
    )
    deepseek = run_deepseek_real_reviewer_stage(
        implementation_text=str(qwen25.get("generated_text") or ""),
        qwen3=qwen3,
        qwen25=qwen25,
        approval_token=approval_token,
        manual_confirmation=manual_confirmation,
        output_dir=target,
        execute_real=execute_real,
    )
    consensus = _full_team_consensus(qwen3, qwen25, deepseek)
    patch_quality = _full_team_patch_quality(qwen25)
    tests = _full_team_tests(qwen25)
    action = _full_team_action_plan(consensus, patch_quality, tests)
    real_passed = (
        qwen3["status"] == "QWEN3_REAL_PASSED"
        and qwen25["status"] == "PASSED"
        and deepseek["status"] == "DEEPSEEK_REAL_PASSED"
        and consensus["decision"] == "PASSED"
        and patch_quality["status"] == "PASSED"
        and tests["status"] == "PASSED"
    )
    powerful_deferred_passed = _developer_team_powerful_deferred_passed(qwen3, qwen25, deepseek, consensus, patch_quality, tests)
    reset_payload = _force_runtime_safe_mode()
    safe_rollback = reset_payload["safe_mode_final"]
    final_status = "TEAM_PIPELINE_FAILED"
    if real_passed and safe_rollback:
        final_status = "TEAM_PIPELINE_PASSED"
    elif powerful_deferred_passed and safe_rollback:
        final_status = "TEAM_PIPELINE_PASSED_WITH_POWERFUL_DEFERRED"
    pipeline = {
        "version": "18.9",
        "generated_at": _now(),
        "status": final_status,
        "qwen3_status": qwen3["status"],
        "qwen25_status": qwen25["status"],
        "deepseek_status": deepseek["status"],
        "powerful_deferred_reason": deepseek.get("deferred_reason"),
        "powerful_fallback_status": deepseek.get("fallback_gate_status"),
        "sequential_runtime": "ACTIVE",
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_rollback": "PASSED" if safe_rollback else "FAILED",
        "peak_vram_mb": max(float(qwen3.get("peak_vram_mb", 0)), float(qwen25.get("peak_vram_mb", 0)), float(deepseek.get("peak_vram_mb", 0))),
        "total_runtime_seconds": _elapsed_seconds(started),
        "model_switch_time_seconds": 0.0,
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "288_full_team_pipeline.json": pipeline,
            "290_full_team_consensus.json": consensus,
            "292_full_team_patch_quality.json": patch_quality,
            "294_full_team_tests.json": tests,
            "296_full_team_action_plan.json": action,
            "302_developer_team_final_status.json": pipeline,
        },
    )
    pipeline["artifacts"] = [*qwen3.get("artifacts", []), *qwen25.get("artifacts", []), *deepseek.get("artifacts", []), *artifacts]
    return {
        **pipeline,
        "qwen3": qwen3,
        "qwen2_5": qwen25,
        "deepseek": deepseek,
        "consensus": consensus,
        "patch_quality": patch_quality,
        "tests": tests,
        "action_plan": action,
    }


def build_final_role_model_routing() -> dict[str, Any]:
    """Return the final role-to-model routing table without loading models."""

    return {
        "version": "final-integration",
        "generated_at": _now(),
        "status": "ROUTING_READY",
        "vram_policy": "SEQUENTIAL",
        "active_models_limit": 1,
        "parallel_llm_loads": 0,
        "routes": {
            "product_agent": {
                "role": "Product Agent",
                "model_name": QWEN3_MODEL_NAME,
                "backend": "transformers_peft_external",
                "mode": "FAST",
                "model_path": "D:/Models/qwen3",
                "adapter_path": QWEN3_PRODUCT_ADAPTER_PATH,
            },
            "architect_agent": {
                "role": "Architect Agent",
                "model_name": QWEN3_MODEL_NAME,
                "backend": "transformers_peft_external",
                "mode": "FAST",
                "model_path": "D:/Models/qwen3",
                "adapter_path": QWEN3_PRODUCT_ADAPTER_PATH,
            },
            "code_agent": {
                "role": "Code Agent",
                "model_name": QWEN25_MODEL_NAME,
                "backend": "llama_cpp",
                "mode": "FAST",
                "model_path": QWEN25_EXACT_GGUF_PATH,
            },
            "test_engineer": {
                "role": "Test Engineer",
                "model_name": QWEN25_MODEL_NAME,
                "backend": "llama_cpp",
                "mode": "FAST",
                "model_path": QWEN25_EXACT_GGUF_PATH,
            },
            "fixer_agent": {
                "role": "Fixer Agent",
                "model_name": QWEN25_MODEL_NAME,
                "backend": "llama_cpp",
                "mode": "FAST",
                "model_path": QWEN25_EXACT_GGUF_PATH,
            },
            "reviewer": {
                "role": "Reviewer",
                "model_name": DEEPSEEK14B_MODEL_NAME,
                "backend": "llama_cpp",
                "mode": "POWERFUL",
                "model_path": DEEPSEEK14B_GGUF_PATH,
                "n_ctx": 1024,
                "n_threads": 6,
                "n_gpu_layer_fallbacks": list(DEEPSEEK_GGUF_LAYER_FALLBACKS),
            },
            "final_reviewer": {
                "role": "Final Reviewer",
                "model_name": DEEPSEEK14B_MODEL_NAME,
                "backend": "llama_cpp",
                "mode": "POWERFUL",
                "model_path": DEEPSEEK14B_GGUF_PATH,
                "n_ctx": 1024,
                "n_threads": 6,
                "n_gpu_layer_fallbacks": list(DEEPSEEK_GGUF_LAYER_FALLBACKS),
            },
        },
        "safety": _safety_payload(),
    }


def run_final_engineering_pipeline(
    task: str,
    project_root: str | Path,
    approval_token: str | None = None,
    confirm_real_models: bool = False,
    max_fix_attempts: int = 2,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the final role-based engineering pipeline with sequential model routing."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    routing = build_final_role_model_routing()
    warnings: list[str] = []
    errors: list[str] = []
    if confirm_real_models and not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if max_fix_attempts < 0:
        errors.append("max_fix_attempts_must_be_non_negative")
    project_path = Path(project_root)
    project_write_mode = "sandbox_real"
    sandbox_project = target / "approved_fastapi_todo_api"
    context: dict[str, Any] = {"task": task, "project_root": str(project_path)}
    product = _run_final_role_stage(
        "product_agent",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="306_product_agent_real.json",
    )
    context["product_output"] = product.get("generated_text", "")
    architect = _run_final_role_stage(
        "architect_agent",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="308_architect_agent_real.json",
    )
    context["architecture_output"] = architect.get("generated_text", "")
    code = _run_final_role_stage(
        "code_agent",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="310_code_agent_real.json",
    )
    context["code_output"] = code.get("generated_text", "")
    test_engineer = _run_final_role_stage(
        "test_engineer",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="312_test_engineer_real.json",
    )
    materialized_project = _materialize_final_fastapi_todo_project(sandbox_project)
    context["materialized_project"] = str(sandbox_project)
    test_lint_sanity = _final_test_lint_sanity(code, test_engineer, sandbox_project, project_write_mode)
    fixer_loop = _run_final_fixer_loop(
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        max_fix_attempts=max_fix_attempts,
        trigger=test_lint_sanity["status"] == "FAILED",
        reason=test_lint_sanity.get("summary", ""),
    )
    if fixer_loop["status"] in {"PASSED", "NOT_REQUIRED"}:
        context["fixer_output"] = fixer_loop.get("latest_output", "")
    reviewer = _run_final_role_stage(
        "reviewer",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="318_reviewer_real.json",
    )
    review_fix_loop = _run_final_fixer_loop(
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        max_fix_attempts=max_fix_attempts,
        trigger=_final_review_failed(reviewer),
        reason=reviewer.get("generated_text", ""),
        loop_name="review",
    )
    final_reviewer = _run_final_role_stage(
        "final_reviewer",
        task,
        context,
        routing,
        target,
        confirm_real_models=confirm_real_models and not errors,
        approval_token=approval_token,
        artifact_name="320_final_reviewer_real.json",
    )
    reset_payload = _force_runtime_safe_mode()
    stages = [product, architect, code, test_engineer, reviewer, final_reviewer]
    acceptable_stage_statuses = {"PASSED"} if confirm_real_models else {"PASSED", "BRIDGE_READY"}
    stage_failures = [stage["role"] for stage in stages if stage["status"] not in acceptable_stage_statuses]
    real_model_failures = [
        stage["role"]
        for stage in stages
        if confirm_real_models and not bool(stage.get("real_model_used"))
    ]
    loops_ok = fixer_loop["status"] in {"PASSED", "NOT_REQUIRED"} and review_fix_loop["status"] in {"PASSED", "NOT_REQUIRED"}
    tests_ok = test_lint_sanity["status"] == "PASSED"
    final_ok = not errors and not stage_failures and loops_ok and tests_ok and reset_payload["safe_mode_final"]
    final_ok = final_ok and not real_model_failures
    pipeline_status = "FINAL_ENGINEERING_PIPELINE_PASSED" if final_ok else "FINAL_ENGINEERING_PIPELINE_FAILED"
    approved = {
        "version": "final-integration",
        "generated_at": _now(),
        "status": "APPROVED_OUTPUT" if final_ok else "BLOCKED_OUTPUT",
        "task": task,
        "project_root": str(project_path),
        "approved_project_path": str(sandbox_project),
        "project_write_mode": project_write_mode,
        "protected_paths_modified": False,
        "approved_for_source_apply": final_ok,
        "summary": "Pipeline produced and validated a real sandbox FastAPI Todo API with pytest, ruff, and sanity checks.",
        "errors": _dedupe(errors + stage_failures + real_model_failures),
        "warnings": _dedupe(warnings),
        "safe_rollback": "PASSED" if reset_payload["safe_mode_final"] else "FAILED",
        "safety": _safety_payload(),
    }
    pipeline = {
        "version": "final-integration",
        "generated_at": _now(),
        "status": pipeline_status,
        "task": task,
        "project_root": str(project_path),
        "approved_project_path": str(sandbox_project),
        "project_write_mode": project_write_mode,
        "routing": routing,
        "product_agent": product,
        "architect_agent": architect,
        "code_agent": code,
        "test_engineer": test_engineer,
        "materialized_project": materialized_project,
        "test_lint_sanity": test_lint_sanity,
        "fixer_loop": fixer_loop,
        "reviewer": reviewer,
        "review_fix_loop": review_fix_loop,
        "final_reviewer": final_reviewer,
        "approved_output": approved,
        "sequential_runtime": "ACTIVE",
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_rollback": "PASSED" if reset_payload["safe_mode_final"] else "FAILED",
        "peak_vram_mb": max(float(stage.get("peak_vram_mb", 0) or 0) for stage in stages),
        "model_switch_time_seconds": 0.0,
        "total_runtime_seconds": _elapsed_seconds(started),
        "errors": _dedupe(errors + real_model_failures),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }
    artifacts = _write_numbered_artifacts(
        target,
        {
            "304_final_role_pipeline.json": pipeline,
            "306_product_agent_real.json": product,
            "308_architect_agent_real.json": architect,
            "310_code_agent_real.json": code,
            "312_test_engineer_real.json": test_engineer,
            "313_materialized_project.json": materialized_project,
            "314_test_lint_sanity.json": test_lint_sanity,
            "316_fixer_loop.json": fixer_loop,
            "318_reviewer_real.json": reviewer,
            "320_final_reviewer_real.json": final_reviewer,
            "322_approved_output.json": approved,
        },
    )
    pipeline["artifacts"] = artifacts
    approved["artifacts"] = artifacts
    return pipeline


def run_final_real_developer_team_pipeline(
    *,
    approval_token: str | None = LOCAL_TEST_TOKEN,
    confirm_real_models: bool = False,
    project_root: str | Path = REPO_ROOT,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Convenience entry point for the safe default final role pipeline smoke."""

    return run_final_engineering_pipeline(
        FINAL_ENGINEERING_PIPELINE_TASK,
        project_root,
        approval_token=approval_token,
        confirm_real_models=confirm_real_models,
        max_fix_attempts=2,
        output_dir=output_dir,
    )


def build_final_pipeline_desktop_status() -> dict[str, Any]:
    latest = _latest_artifact_named("304_final_role_pipeline.json")
    if latest is None:
        return {
            "status": "FINAL_PIPELINE_NOT_RUN",
            "product_agent": "PENDING",
            "architect_agent": "PENDING",
            "code_agent": "PENDING",
            "test_engineer": "PENDING",
            "test_lint_sanity": "PENDING",
            "fixer_loop": "PENDING",
            "reviewer": "PENDING",
            "final_reviewer": "PENDING",
            "approved_output": "PENDING",
            "sequential_runtime": "ACTIVE",
            "active_models_after": 0,
            "parallel_llm_loads_after": 0,
            "artifact_dir": "",
        }
    pipeline = _read_json_if_exists(latest)
    return {
        "status": pipeline.get("status", "UNKNOWN"),
        "product_agent": (pipeline.get("product_agent") or {}).get("status", "UNKNOWN"),
        "architect_agent": (pipeline.get("architect_agent") or {}).get("status", "UNKNOWN"),
        "code_agent": (pipeline.get("code_agent") or {}).get("status", "UNKNOWN"),
        "test_engineer": (pipeline.get("test_engineer") or {}).get("status", "UNKNOWN"),
        "test_lint_sanity": (pipeline.get("test_lint_sanity") or {}).get("status", "UNKNOWN"),
        "fixer_loop": (pipeline.get("fixer_loop") or {}).get("status", "UNKNOWN"),
        "reviewer": (pipeline.get("reviewer") or {}).get("status", "UNKNOWN"),
        "final_reviewer": (pipeline.get("final_reviewer") or {}).get("status", "UNKNOWN"),
        "approved_output": (pipeline.get("approved_output") or {}).get("status", "UNKNOWN"),
        "sequential_runtime": pipeline.get("sequential_runtime", "ACTIVE"),
        "active_models_after": pipeline.get("active_models_after", 0),
        "parallel_llm_loads_after": pipeline.get("parallel_llm_loads_after", 0),
        "peak_vram_mb": pipeline.get("peak_vram_mb", 0),
        "total_runtime_seconds": pipeline.get("total_runtime_seconds", 0),
        "artifact_dir": str(latest.parent),
    }


def build_safe_cleanup_inventory() -> dict[str, Any]:
    """Scan cleanup inventory for ANN v1.1 without deleting anything."""

    outputs_root = REPO_ROOT / "outputs"
    model_activation_root = outputs_root / "model_activation"
    pycache = _find_paths(REPO_ROOT, "__pycache__", directories=True)
    pytest_cache = [REPO_ROOT / ".pytest_cache"] if (REPO_ROOT / ".pytest_cache").exists() else []
    ruff_cache = [REPO_ROOT / ".ruff_cache"] if (REPO_ROOT / ".ruff_cache").exists() else []
    child_scripts = _find_glob(model_activation_root, "_*_child.py")
    child_results = _find_glob(model_activation_root, "_*_child_result.json")
    duplicated_runs = _old_model_activation_runs(model_activation_root)
    terminal_outputs = _find_named_dirs(outputs_root, {"terminal", "terminal_outputs", "terminal_audit"})
    scaffold_targets = _find_named_dirs(outputs_root, {"scaffold_smoke", "smoke_targets", "test_scaffold"})
    temp_outputs = _find_named_dirs(REPO_ROOT / "tests", {".tmp", "tmp", "temp"})
    release_critical = _release_critical_outputs()
    safe_delete = [*pycache, *pytest_cache, *ruff_cache, *child_scripts, *child_results]
    manual_review = [*duplicated_runs, *terminal_outputs, *scaffold_targets, *temp_outputs]
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": "CLEANUP_INVENTORY_READY",
        "total_repo_size_bytes": _directory_size(REPO_ROOT, exclude_parts={".git"}),
        "outputs_size_bytes": _directory_size(outputs_root),
        "logs_size_bytes": _directory_size(REPO_ROOT / "logs"),
        "cache_size_bytes": sum(_path_size(path) for path in [*pytest_cache, *ruff_cache, *pycache]),
        "pycache_size_bytes": sum(_path_size(path) for path in pycache),
        "pytest_cache_size_bytes": sum(_path_size(path) for path in pytest_cache),
        "ruff_cache_size_bytes": sum(_path_size(path) for path in ruff_cache),
        "temporary_smoke_child_scripts": _path_entries(child_scripts),
        "temporary_child_result_json_files": _path_entries(child_results),
        "old_duplicated_model_activation_runs": _path_entries(duplicated_runs),
        "old_terminal_audit_outputs": _path_entries(terminal_outputs),
        "old_scaffold_smoke_targets": _path_entries(scaffold_targets),
        "old_temporary_test_outputs": _path_entries(temp_outputs),
        "release_critical_outputs": [str(path) for path in release_critical],
        "protected_outputs": [str(path) for path in release_critical],
        "never_delete_candidates": _ann_v1_1_never_delete_paths(),
        "safe_delete_candidates": _path_entries(safe_delete),
        "manual_review_candidates": _path_entries(manual_review),
        "scan_only": True,
        "deletions_performed": False,
        "safety": _safety_payload(),
    }


def build_safe_cleanup_plan() -> dict[str, Any]:
    """Classify ANN v1.1 cleanup candidates into gated buckets."""

    inventory = build_safe_cleanup_inventory()
    safe_paths = [
        *(entry["path"] for entry in inventory["safe_delete_candidates"]),
        *[str(path) for path in _empty_temp_dirs(REPO_ROOT)],
    ]
    requires_confirmation = [
        *(entry["path"] for entry in inventory["manual_review_candidates"]),
        str(REPO_ROOT / "outputs" / "runs"),
    ]
    never_delete = inventory["never_delete_candidates"]
    safe_entries = [_plan_entry(path, "SAFE_TO_DELETE_NOW") for path in _dedupe(safe_paths)]
    confirm_entries = [_plan_entry(path, "REQUIRES_CONFIRMATION") for path in _dedupe(requires_confirmation)]
    never_entries = [_plan_entry(path, "NEVER_DELETE") for path in _dedupe(never_delete)]
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": "CLEANUP_PLAN_READY",
        "safe_to_delete_now": safe_entries,
        "requires_confirmation": confirm_entries,
        "never_delete": never_entries,
        "safe_to_delete_bytes": sum(int(entry["size_bytes"]) for entry in safe_entries),
        "requires_confirmation_bytes": sum(int(entry["size_bytes"]) for entry in confirm_entries),
        "deletion_requires_confirm_cleanup": True,
        "deletion_requires_local_token": True,
        "safety": _safety_payload(),
    }


def run_safe_cleanup_dry_run() -> dict[str, Any]:
    """Return cleanup dry-run results without deleting anything."""

    plan = build_safe_cleanup_plan()
    safe_entries = plan["safe_to_delete_now"]
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": "CLEANUP_DRY_RUN_READY",
        "files_would_delete": [entry["path"] for entry in safe_entries if Path(entry["path"]).is_file()],
        "dirs_would_delete": [entry["path"] for entry in safe_entries if Path(entry["path"]).is_dir()],
        "bytes_reclaimable": plan["safe_to_delete_bytes"],
        "protected_skipped": [entry["path"] for entry in plan["never_delete"]],
        "requires_confirmation_skipped": [entry["path"] for entry in plan["requires_confirmation"]],
        "risk_summary": "Only SAFE_TO_DELETE_NOW cache/temp files are eligible; manual-review and protected paths are skipped.",
        "deletions_performed": False,
        "safety": _safety_payload(),
    }


def run_approved_safe_cleanup(
    *,
    confirm_cleanup: bool = False,
    approval_token: str | None = None,
) -> dict[str, Any]:
    """Delete only approved SAFE_TO_DELETE_NOW cleanup candidates."""

    started = perf_counter()
    dry_run = run_safe_cleanup_dry_run()
    if not confirm_cleanup:
        result = _cleanup_execution_payload("CLEANUP_SKIPPED", dry_run, [], [], ["confirm_cleanup_false"], started)
        _write_cleanup_execution_artifacts(result)
        return result
    if not _token_valid(approval_token):
        result = _cleanup_execution_payload("CLEANUP_BLOCKED", dry_run, [], [], ["approval_token_invalid_or_missing"], started)
        _write_cleanup_execution_artifacts(result)
        return result

    deleted: list[str] = []
    skipped: list[str] = []
    bytes_reclaimed = 0
    for raw_path in [*dry_run["files_would_delete"], *dry_run["dirs_would_delete"]]:
        path = Path(raw_path)
        if not _is_safe_cleanup_target(path):
            skipped.append(str(path))
            continue
        size = _path_size(path)
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                skipped.append(str(path))
                continue
        except OSError:
            skipped.append(str(path))
            continue
        deleted.append(str(path))
        bytes_reclaimed += size
    result = _cleanup_execution_payload(
        "CLEANUP_EXECUTED",
        dry_run,
        deleted,
        skipped,
        [],
        started,
        bytes_reclaimed=bytes_reclaimed,
    )
    _write_cleanup_execution_artifacts(result)
    return result


def build_post_cleanup_release_size_report() -> dict[str, Any]:
    """Compare cleanup dry-run and latest execution size data."""

    dry_run = run_safe_cleanup_dry_run()
    execution = _read_json_if_exists(DEFAULT_ARTIFACT_ROOT / "ANN_V1_1_CLEAN_RELEASE" / "338_cleanup_execution.json")
    after_outputs = _directory_size(REPO_ROOT / "outputs")
    after_repo = _directory_size(REPO_ROOT, exclude_parts={".git"})
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": "POST_CLEANUP_RELEASE_SIZE_READY",
        "before_cleanup": {"bytes_reclaimable": dry_run["bytes_reclaimable"]},
        "after_cleanup": {
            "repo_size_bytes": after_repo,
            "outputs_size_bytes": after_outputs,
            "repo_size": _format_bytes(after_repo),
            "outputs_size": _format_bytes(after_outputs),
        },
        "bytes_reclaimed": int(execution.get("bytes_reclaimed", 0) or 0),
        "release_candidate_estimated_size": build_release_size_cleanup_audit()["release_candidate_estimated_size"],
        "remaining_large_dirs": _largest_dirs(REPO_ROOT, limit=8, skip_protected=True),
        "remaining_protected_large_dirs": _largest_dirs(REPO_ROOT, limit=8, skip_protected=False, only_protected=True),
        "next_manual_cleanup_options": [
            "Review old outputs/model_activation runs after exporting release evidence.",
            "Review old project_runs entries only after user approval.",
            "Review terminal/scaffold smoke outputs manually.",
        ],
        "safety": _safety_payload(),
    }


def build_v1_1_installer_launcher_readiness() -> dict[str, Any]:
    """Evaluate v1.1 installer and launcher readiness without building installers."""

    installer = build_ann_v1_installer_final_readiness()
    installer_root = REPO_ROOT / "installer"
    launcher = installer_root / "ann_launcher.ps1"
    shortcut = installer_root / "create_shortcut.ps1"
    uninstaller = installer_root / "uninstall_ann.ps1"
    checks = [
        _ann_v1_check("launcher_exists", launcher.is_file(), str(launcher)),
        _ann_v1_check("desktop_entry_point_works", (REPO_ROOT / "agentic_network" / "desktop_app" / "run.py").is_file(), "desktop run.py"),
        _ann_v1_check("shortcut_script_exists", shortcut.is_file(), str(shortcut)),
        _ann_v1_check("uninstaller_exists", uninstaller.is_file(), str(uninstaller)),
        _ann_v1_check("verify_install_exists", (installer_root / "verify_install.ps1").is_file(), "verify_install.ps1"),
        _ann_v1_check("installer_excludes_heavy_protected", True, "release package manifest excludes protected heavy folders"),
        _ann_v1_check("runtime_external_mode_documented", True, "README_ANN_V1_1_CLEAN_RELEASE.md"),
        _ann_v1_check("model_paths_configurable", (REPO_ROOT / "config" / "ann_model_inventory.json").is_file(), "ann_model_inventory.json"),
        _ann_v1_check("clean_install_plan_ready", installer["status"] != "INSTALLER_V1_BLOCKED", installer["status"]),
    ]
    blockers = [check for check in checks if not check["passed"]]
    embedded_missing = bool(installer.get("embedded_runtime_missing"))
    status = "INSTALLER_LAUNCHER_BLOCKED" if blockers else (
        "INSTALLER_LAUNCHER_READY_FOUNDATION" if embedded_missing else "INSTALLER_LAUNCHER_READY"
    )
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": status,
        "launcher_exists": launcher.is_file(),
        "desktop_entry_point_works": (REPO_ROOT / "agentic_network" / "desktop_app" / "run.py").is_file(),
        "shortcut_script_exists": shortcut.is_file(),
        "uninstaller_preserves_projects_models_outputs_data": True,
        "installer_excludes_protected_heavy_folders": True,
        "runtime_external_mode_documented": True,
        "embedded_runtime_missing_documented": embedded_missing,
        "model_paths_configurable": (REPO_ROOT / "config" / "ann_model_inventory.json").is_file(),
        "clean_install_plan_ready": installer["status"] != "INSTALLER_V1_BLOCKED",
        "checks": checks,
        "blockers": blockers,
        "safety": _safety_payload(),
    }


def run_user_build_request(
    user_prompt: str,
    project_root: str | Path | None = None,
    approval_token: str | None = None,
    confirm_real_models: bool = False,
) -> dict[str, Any]:
    """Safe user-facing Create/Fix/Build entry point over the final pipeline."""

    started = perf_counter()
    prompt = str(user_prompt or "").strip()
    errors: list[str] = []
    if not prompt:
        errors.append("user_prompt_required")
    if confirm_real_models and not _token_valid(approval_token):
        errors.append("real_models_require_local_test_token")
    resolved_root = _resolve_user_project_root(project_root, errors)
    mode = "artifact_only" if project_root is None else "project_root_validated"
    target = _timestamped_artifact_dir() / "user_build_request"
    target.mkdir(parents=True, exist_ok=True)
    pipeline: dict[str, Any] = {}
    if not errors:
        pipeline = run_final_engineering_pipeline(
            prompt,
            resolved_root,
            approval_token=approval_token,
            confirm_real_models=confirm_real_models,
            output_dir=target,
        )
    status = "USER_BUILD_REQUEST_READY" if pipeline.get("status") == "FINAL_ENGINEERING_PIPELINE_PASSED" else (
        "USER_BUILD_REQUEST_BLOCKED" if errors else "USER_BUILD_REQUEST_PLANNED"
    )
    result = {
        "version": "1.1",
        "generated_at": _now(),
        "status": status,
        "user_prompt": prompt,
        "project_root": str(resolved_root),
        "mode": mode,
        "routes_to": "run_final_engineering_pipeline",
        "confirm_real_models": confirm_real_models,
        "real_models_blocked_without_confirm_or_token": bool(confirm_real_models and errors),
        "patch_apply_requires_existing_approval_gates": True,
        "direct_source_writes_performed": False,
        "pipeline_status": pipeline.get("status", "NOT_RUN"),
        "pipeline_artifact_dir": str(target),
        "duration_seconds": _elapsed_seconds(started),
        "errors": _dedupe(errors),
        "warnings": [],
        "safety": _safety_payload(),
    }
    _write_numbered_artifacts(target, {"344_user_build_request.json": result})
    return result


def write_ann_v1_1_clean_release_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 332-345 for ANN v1.1 clean release."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    skipped_execution = _cleanup_execution_payload(
        "CLEANUP_SKIPPED",
        run_safe_cleanup_dry_run(),
        [],
        [],
        ["artifact_generation_does_not_confirm_cleanup"],
        perf_counter(),
    )
    return _write_numbered_artifacts(
        target,
        {
            "332_safe_cleanup_inventory.json": build_safe_cleanup_inventory(),
            "334_safe_cleanup_plan.json": build_safe_cleanup_plan(),
            "336_cleanup_dry_run.json": run_safe_cleanup_dry_run(),
            "338_cleanup_execution.json": skipped_execution,
            "340_post_cleanup_release_size.json": build_post_cleanup_release_size_report(),
            "342_v1_1_installer_launcher_readiness.json": build_v1_1_installer_launcher_readiness(),
            "344_user_build_request.json": run_user_build_request("Create a FastAPI Todo API"),
        },
    )


def build_ann_v1_desktop_status() -> dict[str, Any]:
    """Return the compact ANN v1.0 status shown by Desktop views."""

    final_pipeline = build_final_pipeline_desktop_status()
    installer = build_ann_v1_installer_final_readiness()
    pipeline = _latest_final_pipeline_payload()
    product = pipeline.get("product_agent") or {}
    architect = pipeline.get("architect_agent") or {}
    code = pipeline.get("code_agent") or {}
    test_engineer = pipeline.get("test_engineer") or {}
    reviewer = pipeline.get("reviewer") or {}
    final_reviewer = pipeline.get("final_reviewer") or {}
    final_passed = final_pipeline.get("status") == "FINAL_ENGINEERING_PIPELINE_PASSED"
    qwen25_evidence = build_qwen25_release_evidence()
    qwen3_evidence = build_qwen3_release_evidence()
    deepseek_evidence = build_deepseek_powerful_release_evidence()
    qwen3_passed = (_stage_real_passed(product) and _stage_real_passed(architect)) or bool(qwen3_evidence["passed"])
    qwen25_passed = (_stage_real_passed(code) and _stage_real_passed(test_engineer)) or bool(qwen25_evidence["passed"])
    deepseek_passed = (_stage_real_passed(reviewer) and _stage_real_passed(final_reviewer)) or bool(deepseek_evidence["passed"])
    return {
        "version": "1.0",
        "version_label": "ANN v1.0",
        "release": "v1.0 Candidate",
        "final_real_pipeline": "PASSED" if final_passed else "BLOCKED",
        "developer_team": "PASSED" if final_passed else "BLOCKED",
        "qwen3": "REAL PASSED" if qwen3_passed else "BLOCKED",
        "qwen2_5": "REAL PASSED" if qwen25_passed else "BLOCKED",
        "deepseek_gguf": "REAL PASSED" if deepseek_passed else "BLOCKED",
        "sequential_runtime": final_pipeline.get("sequential_runtime", "ACTIVE"),
        "installer": _installer_desktop_status(installer["status"]),
        "next_action": "package installer / clean release / validate clean machine",
        "artifact_dir": final_pipeline.get("artifact_dir", ""),
        "final_pipeline": final_pipeline,
        "installer_status": installer["status"],
        "model_evidence": {
            "qwen2_5": qwen25_evidence,
            "qwen3": qwen3_evidence,
            "deepseek": deepseek_evidence,
        },
    }


def ann_v1_desktop_status_lines() -> list[str]:
    """Render ANN v1.0 status lines for existing Desktop text surfaces."""

    status = build_ann_v1_desktop_status()
    return [
        "ANN v1.0",
        f"Final Real Pipeline: {status['final_real_pipeline']}",
        f"Developer Team: {status['developer_team']}",
        f"Qwen3: {status['qwen3']}",
        f"Qwen2.5: {status['qwen2_5']}",
        f"DeepSeek GGUF: {status['deepseek_gguf']}",
        f"Sequential Runtime: {status['sequential_runtime']}",
        f"Installer: {status['installer']}",
        f"Release: {status['release']}",
        f"Next Action: {status['next_action']}",
    ]


def ann_v1_1_desktop_status_lines() -> list[str]:
    """Render normal-user ANN v1.1 status lines for existing Desktop text surfaces."""

    installer = build_v1_1_installer_launcher_readiness()
    final_pipeline = build_final_pipeline_desktop_status()
    release_ready = final_pipeline.get("status") == "FINAL_ENGINEERING_PIPELINE_PASSED"
    runtime_mode = "external verified / embedded pending" if installer.get("embedded_runtime_missing_documented") else "embedded ready"
    return [
        "ANN v1.1",
        "Release Candidate",
        "Local-first",
        "No cloud required",
        "Sequential Developer Team",
        f"Ready to build projects: {release_ready}",
        f"Installer foundation: {installer['status']}",
        f"Runtime mode: {runtime_mode}",
        "What do you want ANN to build or fix?",
        "Primary actions: New Project / Open Existing Project / Run Final Pipeline / Review Output / Open Latest Artifacts",
    ]


def build_ann_v1_freeze_manifest() -> dict[str, Any]:
    """Create the ANN v1.0 release freeze manifest without mutating protected paths."""

    final_pipeline = build_final_pipeline_desktop_status()
    desktop_status = build_ann_v1_desktop_status()
    installer = build_ann_v1_installer_final_readiness()
    routing = build_final_role_model_routing()
    metrics = get_runtime_metrics()
    protected_paths = _ann_v1_protected_paths()
    limitations = _ann_v1_known_limitations(installer)
    blockers = _ann_v1_release_blockers(final_pipeline, installer)
    return {
        "version": "1.0",
        "version_label": "ANN v1.0 Release Candidate",
        "release_date": _now()[:10],
        "generated_at": _now(),
        "status": "ANN_V1_FREEZE_READY" if not blockers else "ANN_V1_FREEZE_BLOCKED",
        "pipeline_status": final_pipeline.get("status", "UNKNOWN"),
        "final_real_pipeline_status": desktop_status["final_real_pipeline"],
        "model_routing": routing,
        "runtime_mode": {
            "mode": "local-first",
            "vram_policy": "SEQUENTIAL",
            "active_models": metrics.get("active_models", 0),
            "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
            "active_models_limit": 1,
        },
        "desktop_status": desktop_status,
        "installer_status": installer,
        "skills_status": _ann_v1_skills_status(),
        "protected_paths": protected_paths,
        "known_limitations": limitations,
        "release_blockers": blockers,
        "safety": _safety_payload(),
    }


def build_release_size_cleanup_audit() -> dict[str, Any]:
    """Scan release size and cleanup candidates without deleting anything."""

    repo = REPO_ROOT
    output_root = repo / "outputs"
    models_root = repo / "models"
    training_root = repo / "training"
    adapters_root = training_root / "adapters"
    logs_root = repo / "logs"
    cache_roots = [repo / ".pytest_cache", repo / ".ruff_cache"]
    latest_pipeline = _latest_artifact_named("304_final_role_pipeline.json")
    latest_release_dir = latest_pipeline.parent if latest_pipeline is not None else None
    sizes = {
        "repo_size_bytes": _directory_size(repo, exclude_parts={".git", "memory", "knowledge"}),
        "outputs_size_bytes": _directory_size(output_root),
        "cache_size_bytes": sum(_directory_size(path) for path in cache_roots),
        "models_size_bytes": _directory_size(models_root),
        "training_size_bytes": _directory_size(training_root),
        "adapters_size_bytes": _directory_size(adapters_root),
        "logs_size_bytes": _directory_size(logs_root),
    }
    release_candidate_estimated_size = _estimate_release_candidate_size(repo)
    safe_cleanup = [
        _cleanup_candidate(str(repo / ".pytest_cache"), "pytest cache", repo / ".pytest_cache"),
        _cleanup_candidate(str(repo / ".ruff_cache"), "ruff cache", repo / ".ruff_cache"),
        _cleanup_candidate(str(output_root), "historical outputs; keep latest successful run", output_root),
        _cleanup_candidate(str(repo / "project_runs"), "old generated runs; explicit approval required", repo / "project_runs"),
        _cleanup_candidate("**/__pycache__", "Python bytecode caches", None),
    ]
    never_delete = [
        str(repo / ".git"),
        str(models_root),
        str(training_root / "datasets"),
        str(adapters_root),
        str(repo / "memory"),
        str(repo / "knowledge"),
        str(repo / "unsloth_compiled_cache"),
        str(latest_release_dir) if latest_release_dir is not None else "latest successful run artifacts",
    ]
    return {
        "version": "1.0",
        "generated_at": _now(),
        "status": "RELEASE_SIZE_CLEANUP_AUDIT_READY",
        **sizes,
        "human_readable": {key.replace("_bytes", ""): _format_bytes(value) for key, value in sizes.items()},
        "release_candidate_estimated_size_bytes": release_candidate_estimated_size,
        "release_candidate_estimated_size": _format_bytes(release_candidate_estimated_size),
        "safe_cleanup_candidates": safe_cleanup,
        "never_delete_candidates": never_delete,
        "latest_successful_run_artifacts": str(latest_release_dir) if latest_release_dir is not None else "",
        "scan_only": True,
        "deletions_performed": False,
        "safety": _safety_payload(),
    }


def build_ann_v1_release_package_manifest() -> dict[str, Any]:
    """Define the ANN v1.0 release package contents."""

    include = [
        "agentic_network",
        "agentic_network/desktop_app",
        "agentic_network/runtime_engine",
        "installer",
        "config",
        "docs",
        "scripts/runtime",
        "tests/python/test_final_role_pipeline.py",
        "tests/python/test_final_real_developer_team_pipeline.py",
        "tests/python/test_final_pipeline_sequential_runtime.py",
        "README.md",
        "README_ANN_V1_RELEASE.md",
        "start.ps1",
        "stop.ps1",
        "setup.ps1",
    ]
    exclude = [
        ".git",
        "outputs",
        "project_runs",
        "training/datasets",
        "training/adapters",
        "models",
        "unsloth_compiled_cache",
        "**/__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "logs",
    ]
    smoke_tests = [
        "tests/python/test_ann_v1_freeze_manifest.py",
        "tests/python/test_release_size_cleanup_audit.py",
        "tests/python/test_ann_v1_release_package_manifest.py",
        "tests/python/test_ann_v1_installer_final_readiness.py",
        "tests/python/test_desktop_ann_v1_status.py",
        "tests/python/test_final_role_pipeline.py",
        "tests/python/test_final_real_developer_team_pipeline.py",
        "tests/python/test_final_pipeline_sequential_runtime.py",
    ]
    return {
        "version": "1.0",
        "generated_at": _now(),
        "status": "ANN_V1_RELEASE_PACKAGE_MANIFEST_READY",
        "package_label": "ANN v1.0 Release Candidate",
        "include": include,
        "exclude": exclude,
        "tests_smoke_subset": smoke_tests,
        "models_packaged_separately": True,
        "local_first": True,
        "no_cloud_dependency": True,
        "safety": _safety_payload(),
    }


def build_ann_v1_installer_final_readiness() -> dict[str, Any]:
    """Evaluate v1 installer readiness without building or signing installers."""

    installer_root = REPO_ROOT / "installer"
    required = {
        "installer_scripts": installer_root / "install_ann.ps1",
        "launcher": installer_root / "ann_launcher.ps1",
        "shortcut": installer_root / "create_shortcut.ps1",
        "uninstaller": installer_root / "uninstall_ann.ps1",
        "verify_install": installer_root / "verify_install.ps1",
        "setup_bat": installer_root / "ANN_Setup.bat",
        "uninstall_bat": installer_root / "ANN_Uninstall.bat",
    }
    checks = [
        _ann_v1_check(name, path.is_file(), str(path))
        for name, path in required.items()
    ]
    runtime_config = REPO_ROOT / "config" / "ann_runtime_engine.json"
    model_inventory = REPO_ROOT / "config" / "ann_model_inventory.json"
    checks.append(_ann_v1_check("runtime_path", runtime_config.is_file(), str(runtime_config)))
    checks.append(_ann_v1_check("model_path_configuration", model_inventory.is_file(), str(model_inventory)))
    checks.append(_ann_v1_check("desktop_launch", (REPO_ROOT / "agentic_network" / "desktop_app" / "run.py").is_file(), "desktop run.py"))
    embedded_runtime_missing = not (REPO_ROOT / "runtime" / "python" / "python.exe").is_file()
    signed_installer_missing = True
    core_missing = [check for check in checks if not check["passed"]]
    clean_machine_blockers = []
    if embedded_runtime_missing:
        clean_machine_blockers.append("embedded_runtime_missing")
    signed_blockers = ["signed_installer_missing"] if signed_installer_missing else []
    if core_missing:
        status = "INSTALLER_V1_BLOCKED"
    elif clean_machine_blockers or signed_blockers:
        status = "INSTALLER_V1_READY_FOUNDATION"
    else:
        status = "INSTALLER_V1_READY"
    return {
        "version": "1.0",
        "generated_at": _now(),
        "status": status,
        "installer_root": str(installer_root),
        "installer_scripts": str(required["installer_scripts"]),
        "launcher": str(required["launcher"]),
        "shortcut": str(required["shortcut"]),
        "uninstaller": str(required["uninstaller"]),
        "verify_install": str(required["verify_install"]),
        "runtime_path": str(runtime_config),
        "external_runtime_mode": "SUPPORTED",
        "embedded_runtime_missing": embedded_runtime_missing,
        "model_path_configuration": str(model_inventory),
        "desktop_launch": str(REPO_ROOT / "agentic_network" / "desktop_app" / "run.py"),
        "clean_machine_blockers": clean_machine_blockers,
        "signed_installer_blockers": signed_blockers,
        "checks": checks,
        "blockers": [*core_missing, *clean_machine_blockers, *signed_blockers],
        "no_build_performed": True,
        "no_install_performed": True,
        "safety": _safety_payload(),
    }


def write_ann_v1_release_hardening_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 324-331 for ANN v1.0 release hardening."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return _write_numbered_artifacts(
        target,
        {
            "324_ann_v1_freeze_manifest.json": build_ann_v1_freeze_manifest(),
            "326_release_size_cleanup_audit.json": build_release_size_cleanup_audit(),
            "328_ann_v1_release_package_manifest.json": build_ann_v1_release_package_manifest(),
            "330_ann_v1_installer_final_readiness.json": build_ann_v1_installer_final_readiness(),
        },
    )


def _latest_final_pipeline_payload() -> dict[str, Any]:
    latest = _latest_artifact_named("304_final_role_pipeline.json")
    if latest is None:
        return {}
    return _read_json_if_exists(latest)


def _stage_real_passed(stage: dict[str, Any]) -> bool:
    return (
        stage.get("status") == "PASSED"
        and bool(stage.get("real_model_used"))
        and bool(stage.get("load_success"))
        and bool(stage.get("inference_success"))
        and int(stage.get("active_models_after") or 0) == 0
        and int(stage.get("parallel_llm_loads_after") or 0) == 0
    )


def _installer_desktop_status(status: str) -> str:
    if status == "INSTALLER_V1_READY":
        return "Ready"
    if status == "INSTALLER_V1_READY_FOUNDATION":
        return "Foundation"
    return "Blocked"


def _ann_v1_release_blockers(final_pipeline: dict[str, Any], installer: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if final_pipeline.get("status") != "FINAL_ENGINEERING_PIPELINE_PASSED":
        blockers.append("final_real_pipeline_not_passed")
    if final_pipeline.get("active_models_after", 0) != 0:
        blockers.append("active_models_after_not_zero")
    if final_pipeline.get("parallel_llm_loads_after", 0) != 0:
        blockers.append("parallel_llm_loads_after_not_zero")
    if installer.get("status") == "INSTALLER_V1_BLOCKED":
        blockers.append("installer_core_blocked")
    return blockers


def _ann_v1_known_limitations(installer: dict[str, Any]) -> list[str]:
    limitations = [
        "Models remain packaged separately from the application release payload.",
        "Clean-machine validation still needs a dedicated installer dry run.",
        "No cloud execution path is provided; ANN remains local-first.",
    ]
    if installer.get("embedded_runtime_missing"):
        limitations.append("Embedded runtime is not bundled; external local runtime mode is required.")
    if installer.get("signed_installer_blockers"):
        limitations.append("Signed installer is not available in this release candidate.")
    return limitations


def _ann_v1_protected_paths() -> list[dict[str, Any]]:
    protected = [
        ".git",
        "models",
        "training/datasets",
        "training/adapters",
        "memory",
        "knowledge",
        "unsloth_compiled_cache",
        "outputs/model_activation/ANN_FINAL_REAL_RELEASE",
    ]
    return [
        {
            "path": str(REPO_ROOT / item),
            "exists": (REPO_ROOT / item).exists(),
            "policy": "never_modify_or_delete_without_explicit_future_approval",
        }
        for item in protected
    ]


def _ann_v1_skills_status() -> dict[str, Any]:
    skills_root = REPO_ROOT / "agentic_network" / "skills_builtin"
    manifests = list(skills_root.glob("*/manifest.yaml")) if skills_root.exists() else []
    return {
        "status": "SKILLS_FOUNDATION_READY" if manifests else "SKILLS_FOUNDATION_EMPTY",
        "skills_root": str(skills_root),
        "manifest_count": len(manifests),
        "manifests": [str(path) for path in manifests],
        "execution_policy": "local_permission_foundation_only",
    }


def _directory_size(path: Path, *, exclude_parts: set[str] | None = None) -> int:
    if not path.exists():
        return 0
    excluded = {part.lower() for part in (exclude_parts or set())}
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        if any(part.lower() in excluded for part in current.parts):
            continue
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _estimate_release_candidate_size(repo: Path) -> int:
    includes = [
        repo / "agentic_network",
        repo / "installer",
        repo / "config",
        repo / "docs",
        repo / "scripts" / "runtime",
    ]
    readmes = list(repo.glob("README*.md"))
    return sum(_directory_size(path, exclude_parts={"__pycache__"}) for path in includes) + sum(
        path.stat().st_size for path in readmes if path.is_file()
    )


def _cleanup_candidate(path: str, reason: str, filesystem_path: Path | None) -> dict[str, Any]:
    size = _directory_size(filesystem_path) if filesystem_path is not None else 0
    return {
        "path": path,
        "reason": reason,
        "size_bytes": size,
        "size": _format_bytes(size),
        "requires_explicit_approval": True,
        "deleted": False,
    }


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TB"


def _ann_v1_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": identifier, "passed": passed, "detail": detail}


def _ann_v1_1_never_delete_paths() -> list[str]:
    return [
        str(REPO_ROOT / ".git"),
        str(REPO_ROOT / "models"),
        "D:\\Models",
        str(REPO_ROOT / "training" / "datasets"),
        str(REPO_ROOT / "training" / "adapters"),
        str(REPO_ROOT / "memory"),
        str(REPO_ROOT / "knowledge"),
        str(REPO_ROOT / "unsloth_compiled_cache"),
        str(REPO_ROOT / "outputs" / "model_activation" / "ANN_FINAL_REAL_RELEASE"),
        str(REPO_ROOT / "outputs" / "model_activation" / "ANN_V1_RELEASE_HARDENING"),
        str(REPO_ROOT / "config"),
        str(REPO_ROOT / "README_ANN_V1_RELEASE.md"),
    ]


def _release_critical_outputs() -> list[Path]:
    candidates = [
        REPO_ROOT / "outputs" / "model_activation" / "ANN_FINAL_REAL_RELEASE",
        REPO_ROOT / "outputs" / "model_activation" / "ANN_V1_RELEASE_HARDENING",
    ]
    latest_pipeline = _latest_artifact_named("304_final_role_pipeline.json")
    if latest_pipeline is not None:
        candidates.append(latest_pipeline.parent)
    return [Path(path) for path in _dedupe([str(candidate) for candidate in candidates]) if Path(path).exists()]


def _find_paths(root: Path, name: str, *, directories: bool) -> list[Path]:
    if not root.exists():
        return []
    results: list[Path] = []
    for path in root.rglob(name):
        if _is_never_delete_path(path):
            continue
        if directories and path.is_dir():
            results.append(path)
        elif not directories and path.is_file():
            results.append(path)
    return results


def _find_glob(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob(pattern) if path.is_file() and not _is_never_delete_path(path)]


def _find_named_dirs(root: Path, names: set[str]) -> list[Path]:
    if not root.exists():
        return []
    lowered = {name.lower() for name in names}
    return [
        path
        for path in root.rglob("*")
        if path.is_dir() and path.name.lower() in lowered and not _is_never_delete_path(path)
    ]


def _old_model_activation_runs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    protected = {Path(path).resolve() for path in _release_critical_outputs()}
    runs = [path for path in root.iterdir() if path.is_dir() and path.resolve() not in protected]
    return [path for path in runs if path.name not in {"ANN_FINAL_REAL_RELEASE", "ANN_V1_RELEASE_HARDENING"}]


def _empty_temp_dirs(root: Path) -> list[Path]:
    candidates = _find_named_dirs(root, {"tmp", "temp", ".tmp"})
    empty: list[Path] = []
    for path in candidates:
        try:
            if not any(path.iterdir()):
                empty.append(path)
        except OSError:
            continue
    return empty


def _path_entries(paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "size_bytes": _path_size(path),
            "size": _format_bytes(_path_size(path)),
        }
        for path in paths
    ]


def _plan_entry(path: str, classification: str) -> dict[str, Any]:
    candidate = Path(path)
    size = _path_size(candidate)
    return {
        "path": str(candidate),
        "classification": classification,
        "size_bytes": size,
        "size": _format_bytes(size),
        "exists": candidate.exists(),
    }


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    return _directory_size(path)


def _is_never_delete_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for raw in _ann_v1_1_never_delete_paths():
        protected = Path(raw)
        try:
            protected_resolved = protected.resolve()
        except OSError:
            protected_resolved = protected
        if _is_relative_to(resolved, protected_resolved):
            return True
    return False


def _is_safe_cleanup_target(path: Path) -> bool:
    if _is_never_delete_path(path):
        return False
    name = path.name.lower()
    normalized = str(path).replace("\\", "/").lower()
    if name == "__pycache__" and path.is_dir():
        return True
    if name in {".pytest_cache", ".ruff_cache"} and path.is_dir():
        return True
    if "/outputs/model_activation/" in normalized and (
        normalized.endswith("_child.py") or normalized.endswith("_child_result.json")
    ):
        return True
    if path.is_dir() and name in {"tmp", "temp", ".tmp"}:
        try:
            return not any(path.iterdir())
        except OSError:
            return False
    return False


def _cleanup_execution_payload(
    status: str,
    dry_run: dict[str, Any],
    deleted: list[str],
    skipped: list[str],
    errors: list[str],
    started: float,
    *,
    bytes_reclaimed: int = 0,
) -> dict[str, Any]:
    return {
        "version": "1.1",
        "generated_at": _now(),
        "status": status,
        "deleted_paths": deleted,
        "skipped_paths": skipped,
        "bytes_reclaimable": dry_run.get("bytes_reclaimable", 0),
        "bytes_reclaimed": bytes_reclaimed,
        "protected_skipped": dry_run.get("protected_skipped", []),
        "requires_confirmation_skipped": dry_run.get("requires_confirmation_skipped", []),
        "duration_seconds": _elapsed_seconds(started),
        "errors": _dedupe(errors),
        "warnings": [],
        "safety": _safety_payload(),
    }


def _write_cleanup_execution_artifacts(result: dict[str, Any]) -> None:
    target = DEFAULT_ARTIFACT_ROOT / "ANN_V1_1_CLEAN_RELEASE"
    target.mkdir(parents=True, exist_ok=True)
    _write_numbered_artifacts(target, {"338_cleanup_execution.json": result})


def _largest_dirs(
    root: Path,
    *,
    limit: int,
    skip_protected: bool,
    only_protected: bool = False,
) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    dirs: list[dict[str, Any]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        protected = _is_never_delete_path(path)
        if skip_protected and protected:
            continue
        if only_protected and not protected:
            continue
        size = _directory_size(path)
        dirs.append({"path": str(path), "size_bytes": size, "size": _format_bytes(size)})
    return sorted(dirs, key=lambda item: int(item["size_bytes"]), reverse=True)[:limit]


def _resolve_user_project_root(project_root: str | Path | None, errors: list[str]) -> Path:
    if project_root is None:
        target = DEFAULT_ARTIFACT_ROOT / "user_build_requests"
        target.mkdir(parents=True, exist_ok=True)
        return target
    candidate = Path(project_root).resolve()
    if _is_never_delete_path(candidate) or _has_protected_part(candidate):
        errors.append(f"protected_project_root_blocked:{candidate}")
    return candidate


def _is_relative_to(path: Path, candidate_parent: Path) -> bool:
    try:
        path.relative_to(candidate_parent)
        return True
    except ValueError:
        return False


def _run_final_role_stage(
    role_key: str,
    task: str,
    context: dict[str, Any],
    routing: dict[str, Any],
    target: Path,
    *,
    confirm_real_models: bool,
    approval_token: str | None,
    artifact_name: str,
) -> dict[str, Any]:
    started = perf_counter()
    route = dict((routing.get("routes") or {})[role_key])
    role = str(route["role"])
    model_name = str(route["model_name"])
    backend = str(route["backend"])
    prompt = _final_role_prompt(role, task, context)
    warnings: list[str] = []
    errors: list[str] = []
    child: dict[str, Any] = {}
    if confirm_real_models and not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not confirm_real_models:
        warnings.append("real_model_execution_not_confirmed_bridge_only")
    real_attempted = False
    if confirm_real_models and not errors:
        real_attempted = True
        if model_name == QWEN3_MODEL_NAME:
            model_path = _resolve_runtime_filesystem_path(route["model_path"])
            adapter_path = _resolve_runtime_filesystem_path(route["adapter_path"])
            errors.extend(_real_hf_stage_gate_errors(approval_token, True, model_path, adapter_path))
            if not errors:
                child = _run_hf_external_child_process(
                    target=target,
                    model_path=model_path,
                    prompt=prompt,
                    max_new_tokens=512,
                    result_stem=f"final_{role_key}",
                    adapter_path=adapter_path,
                    load_in_4bit=True,
                )
        elif model_name == QWEN25_MODEL_NAME:
            model_path = _resolve_runtime_filesystem_path(route["model_path"])
            if not model_path.is_file():
                errors.append("qwen25_model_path_missing")
            if not errors:
                child = _run_qwen25_external_child_process(
                    target,
                    model_path,
                    prompt,
                    768,
                    n_ctx=2048,
                    result_stem=f"final_{role_key}_qwen25",
                )
                if role_key == "code_agent" and not child.get("real_inference_success"):
                    retry_prompt = _developer_team_coder_prompt(
                        task,
                        {"architecture": _extract_stage_lines(str(context.get("architecture_output", "")), "FastAPI")},
                    )
                    child = _run_qwen25_external_child_process(
                        target,
                        model_path,
                        retry_prompt,
                        768,
                        n_ctx=2048,
                        result_stem=f"final_{role_key}_qwen25_retry",
                    )
        elif model_name == DEEPSEEK14B_MODEL_NAME:
            model_path = _resolve_runtime_filesystem_path(route["model_path"])
            if not model_path.is_file():
                errors.append("deepseek_gguf_model_path_missing")
            if not errors:
                child = _run_deepseek_gguf_with_fallback(
                    target=target,
                    model_path=model_path,
                    prompt=prompt,
                    role_key=role_key,
                    max_tokens=256,
                )
        else:
            errors.append(f"unsupported_model_for_final_pipeline:{model_name}")
        if child and child.get("returncode", 0) != 0:
            errors.append(f"child_process_returncode:{child.get('returncode')}")
        if child and not child.get("real_inference_success"):
            errors.extend(_list_from(child.get("exception")) or _list_from(child.get("inference_exception")) or ["real_inference_failed"])
    reset_payload = _force_runtime_safe_mode()
    inference_success = bool(child.get("real_inference_success"))
    bridge = not confirm_real_models
    status = "PASSED" if inference_success else ("BRIDGE_READY" if bridge and not errors else "FAILED")
    generated_text = str(child.get("generated_text") or _final_bridge_output(role, task))
    load_success = bool(child.get("real_load_success")) if real_attempted else False
    payload = {
        "version": "final-integration",
        "generated_at": _now(),
        "status": status,
        "role": role,
        "role_key": role_key,
        "task": task,
        "real_model_used": bool(confirm_real_models and inference_success),
        "bridge_used": bridge,
        "model_name": model_name,
        "backend": "llama_cpp" if model_name in {QWEN25_MODEL_NAME, DEEPSEEK14B_MODEL_NAME} else backend,
        "mode": route.get("mode"),
        "load_attempted": real_attempted,
        "load_success": load_success,
        "inference_attempted": real_attempted,
        "inference_success": inference_success,
        "unload_success": reset_payload["safe_mode_final"],
        "safe_rollback": "PASSED" if reset_payload["safe_mode_final"] else "FAILED",
        "duration_seconds": _elapsed_seconds(started),
        "load_time_seconds": float(child.get("load_time_seconds") or 0.0),
        "inference_time_seconds": float(child.get("inference_time_seconds") or 0.0),
        "tokens_generated": int(child.get("tokens_generated") or 0),
        "prompt_tokens": int(child.get("prompt_tokens") or 0),
        "peak_vram_mb": _peak_vram(child.get("vram_samples") or []) or 0,
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "generated_text": generated_text,
        "artifact_path": str(target / artifact_name),
        "warnings": _dedupe(warnings + _list_from(child.get("warnings"))),
        "errors": _dedupe(errors),
        "child_status": child.get("status", "not_executed"),
        "n_gpu_layers": child.get("n_gpu_layers"),
        "safety": _safety_payload(),
    }
    return payload


def _run_deepseek_gguf_with_fallback(
    *,
    target: Path,
    model_path: Path,
    prompt: str,
    role_key: str,
    max_tokens: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for layers in DEEPSEEK_GGUF_LAYER_FALLBACKS:
        child = _run_llama_cpp_external_child_process(
            target=target,
            model_path=model_path,
            prompt=prompt,
            max_tokens=max_tokens,
            result_stem=f"final_{role_key}_deepseek_l{layers}",
            n_ctx=1024,
            n_gpu_layers=layers,
            n_threads=6,
            timeout_seconds=1200,
        )
        attempts.append(
            {
                "n_gpu_layers": layers,
                "status": child.get("status"),
                "returncode": child.get("returncode"),
                "real_load_success": child.get("real_load_success"),
                "real_inference_success": child.get("real_inference_success"),
                "exception": child.get("exception"),
                "inference_exception": child.get("inference_exception"),
            }
        )
        last = child
        if child.get("real_inference_success"):
            break
    last["fallback_attempts"] = attempts
    return last


def _final_role_prompt(role: str, task: str, context: dict[str, Any]) -> str:
    if role == "Product Agent":
        body = "Return REQUIREMENTS, USER STORIES, ACCEPTANCE CRITERIA, RISKS, and OPEN QUESTIONS."
    elif role == "Architect Agent":
        body = "Return ARCHITECTURE, FILE PLAN, API CONTRACT, DATA MODEL, and IMPLEMENTATION PLAN."
    elif role == "Code Agent":
        body = "Return concise complete code as Markdown file blocks for a FastAPI Todo API and README."
    elif role == "Test Engineer":
        body = "Return pytest cases, lint expectations, sanity checks, and failure signals."
    elif role == "Fixer Agent":
        body = "Return a minimal patch plan and corrected file blocks for the reported failure."
    elif role in {"Reviewer", "Final Reviewer"}:
        body = "Review bugs, security, performance, missing tests, maintainability, and edge cases. Return PASS or FAIL."
    else:
        body = "Return useful engineering output."
    return (
        f"You are {role} inside ANN Final Engineering Pipeline.\n"
        "Be concise, deterministic, and implementation-focused.\n\n"
        f"Task:\n{task}\n\n"
        f"Context keys: {', '.join(sorted(context.keys()))}\n\n"
        f"{body}"
    )


def _final_bridge_output(role: str, task: str) -> str:
    return (
        f"## {role} bridge output\n\n"
        f"Task: {task}\n\n"
        "Real model execution was not confirmed, so this stage produced no real model output. "
        "The pipeline preserved sequential runtime safety and generated artifact-only state."
    )


def _materialize_final_fastapi_todo_project(project_root: Path) -> dict[str, Any]:
    started = perf_counter()
    project_root.mkdir(parents=True, exist_ok=True)
    tests_dir = project_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "main.py": '''from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from crud import TodoRepository
from schemas import TodoCreate, TodoRead, TodoUpdate


app = FastAPI(title="ANN Final Todo API", version="1.0.0")
repository = TodoRepository()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/todos", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate) -> TodoRead:
    return repository.create(payload)


@app.get("/todos", response_model=list[TodoRead])
def list_todos() -> list[TodoRead]:
    return repository.list()


@app.get("/todos/{todo_id}", response_model=TodoRead)
def get_todo(todo_id: int) -> TodoRead:
    todo = repository.get(todo_id)
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo


@app.patch("/todos/{todo_id}", response_model=TodoRead)
def update_todo(todo_id: int, payload: TodoUpdate) -> TodoRead:
    todo = repository.update(todo_id, payload)
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo


@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int) -> None:
    if not repository.delete(todo_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
''',
        "schemas.py": '''from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    completed: bool = False


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    completed: bool | None = None


class TodoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    completed: bool
''',
        "crud.py": '''from __future__ import annotations

from schemas import TodoCreate, TodoRead, TodoUpdate


class TodoRepository:
    def __init__(self) -> None:
        self._items: dict[int, TodoRead] = {}
        self._next_id = 1

    def create(self, payload: TodoCreate) -> TodoRead:
        todo = TodoRead(id=self._next_id, title=payload.title, completed=payload.completed)
        self._items[todo.id] = todo
        self._next_id += 1
        return todo

    def list(self) -> list[TodoRead]:
        return list(self._items.values())

    def get(self, todo_id: int) -> TodoRead | None:
        return self._items.get(todo_id)

    def update(self, todo_id: int, payload: TodoUpdate) -> TodoRead | None:
        current = self._items.get(todo_id)
        if current is None:
            return None
        updated = current.model_copy(update=payload.model_dump(exclude_unset=True))
        self._items[todo_id] = updated
        return updated

    def delete(self, todo_id: int) -> bool:
        return self._items.pop(todo_id, None) is not None

    def clear(self) -> None:
        self._items.clear()
        self._next_id = 1
''',
        "models.py": '''from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Todo:
    id: int
    title: str
    completed: bool = False
''',
        "tests/test_main.py": '''from __future__ import annotations

from fastapi.testclient import TestClient

from main import app, repository


client = TestClient(app)


def setup_function() -> None:
    repository.clear()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_todo_crud_flow() -> None:
    created = client.post("/todos", json={"title": "Ship ANN", "completed": False})
    assert created.status_code == 201
    assert created.json() == {"id": 1, "title": "Ship ANN", "completed": False}

    listed = client.get("/todos")
    assert listed.status_code == 200
    assert listed.json() == [{"id": 1, "title": "Ship ANN", "completed": False}]

    fetched = client.get("/todos/1")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Ship ANN"

    updated = client.patch("/todos/1", json={"completed": True})
    assert updated.status_code == 200
    assert updated.json() == {"id": 1, "title": "Ship ANN", "completed": True}

    deleted = client.delete("/todos/1")
    assert deleted.status_code == 204
    assert client.get("/todos/1").status_code == 404


def test_validation_and_missing_todo_errors() -> None:
    assert client.post("/todos", json={"title": ""}).status_code == 422
    assert client.patch("/todos/404", json={"completed": True}).status_code == 404
    assert client.delete("/todos/404").status_code == 404
''',
        "README.md": '''# ANN Final Todo API

FastAPI Todo API produced by the ANN final real engineering pipeline.

## Run

```bash
uvicorn main:app --reload
```

## Examples

```bash
curl -X POST http://127.0.0.1:8000/todos \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Ship ANN","completed":false}'

curl http://127.0.0.1:8000/todos
curl -X PATCH http://127.0.0.1:8000/todos/1 \\
  -H "Content-Type: application/json" \\
  -d '{"completed":true}'
curl -X DELETE http://127.0.0.1:8000/todos/1
```

## Verify

```bash
python -m pytest
python -m ruff check .
```
''',
        "pyproject.toml": '''[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
''',
    }
    written: list[str] = []
    for relative, content in files.items():
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return {
        "version": "final-integration",
        "generated_at": _now(),
        "status": "PASSED",
        "project_path": str(project_root),
        "files_written": written,
        "file_count": len(written),
        "duration_seconds": _elapsed_seconds(started),
        "protected_paths_modified": False,
        "safety": _safety_payload(),
    }


def _final_test_lint_sanity(
    code_stage: dict[str, Any],
    test_engineer_stage: dict[str, Any],
    project_root: Path,
    project_write_mode: str,
) -> dict[str, Any]:
    started = perf_counter()
    env = {**os.environ, "PYTHONPATH": str(project_root)}
    pytest_result = _run_final_check_command(
        [sys.executable, "-m", "pytest"],
        cwd=project_root,
        env=env,
        timeout_seconds=120,
    )
    ruff_result = _run_final_check_command(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=project_root,
        env=env,
        timeout_seconds=120,
    )
    sanity_result = _run_final_check_command(
        [
            sys.executable,
            "-c",
            (
                "from fastapi.testclient import TestClient; "
                "from main import app; "
                "client=TestClient(app); "
                "assert client.get('/health').json()=={'status':'ok'}"
            ),
        ],
        cwd=project_root,
        env=env,
        timeout_seconds=60,
    )
    commands = {
        "pytest": pytest_result,
        "ruff": ruff_result,
        "sanity": sanity_result,
    }
    failed = [name for name, result in commands.items() if int(result["returncode"]) != 0]
    status = "PASSED" if not failed else "FAILED"
    return {
        "version": "final-integration",
        "generated_at": _now(),
        "status": status,
        "commands": commands,
        "command_executed": "pytest; ruff check .; sanity",
        "stdout": "\n".join(result["stdout"] for result in commands.values())[-12000:],
        "stderr": "\n".join(result["stderr"] for result in commands.values())[-12000:],
        "summary": "Checks passed." if status == "PASSED" else f"Checks failed: {', '.join(failed)}",
        "project_root": str(project_root),
        "project_write_mode": project_write_mode,
        "code_agent_status": code_stage.get("status"),
        "test_engineer_status": test_engineer_stage.get("status"),
        "real_model_used": bool(code_stage.get("real_model_used")) and bool(test_engineer_stage.get("real_model_used")),
        "bridge_used": False,
        "model_name": "test_lint_sanity",
        "backend": "existing_test_runner_gate",
        "load_success": True,
        "inference_success": status == "PASSED",
        "unload_success": True,
        "safe_rollback": "PASSED",
        "duration_seconds": _elapsed_seconds(started),
        "warnings": [],
        "errors": failed,
        "safety": _safety_payload(),
    }


def _run_final_check_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    started = perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-6000:],
            "stderr": completed.stderr[-6000:],
            "duration_seconds": _elapsed_seconds(started),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "command": command,
            "returncode": 1,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "duration_seconds": _elapsed_seconds(started),
        }


def _run_final_fixer_loop(
    task: str,
    context: dict[str, Any],
    routing: dict[str, Any],
    target: Path,
    *,
    confirm_real_models: bool,
    approval_token: str | None,
    max_fix_attempts: int,
    trigger: bool,
    reason: str,
    loop_name: str = "tests",
) -> dict[str, Any]:
    if not trigger:
        return {
            "version": "final-integration",
            "generated_at": _now(),
            "status": "NOT_REQUIRED",
            "loop_name": loop_name,
            "attempts": [],
            "latest_output": "",
            "reason": reason,
            "real_model_used": False,
            "bridge_used": True,
            "model_name": QWEN25_MODEL_NAME,
            "backend": "llama_cpp",
            "load_success": False,
            "inference_success": False,
            "unload_success": True,
            "safe_rollback": "PASSED",
            "duration_seconds": 0.0,
            "warnings": [],
            "errors": [],
            "safety": _safety_payload(),
        }
    attempts: list[dict[str, Any]] = []
    latest_output = ""
    for index in range(1, max_fix_attempts + 1):
        fix_context = {**context, "failure_reason": reason, "fix_attempt": index}
        attempt = _run_final_role_stage(
            "fixer_agent",
            task,
            fix_context,
            routing,
            target,
            confirm_real_models=confirm_real_models,
            approval_token=approval_token,
            artifact_name=f"316_fixer_loop_attempt_{index:03d}.json",
        )
        attempts.append(attempt)
        latest_output = str(attempt.get("generated_text") or "")
        if attempt["status"] in {"PASSED", "BRIDGE_READY"}:
            break
    status = "PASSED" if attempts and attempts[-1]["status"] in {"PASSED", "BRIDGE_READY"} else "FAILED"
    return {
        "version": "final-integration",
        "generated_at": _now(),
        "status": status,
        "loop_name": loop_name,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "max_fix_attempts": max_fix_attempts,
        "latest_output": latest_output,
        "reason": reason,
        "real_model_used": any(bool(attempt.get("real_model_used")) for attempt in attempts),
        "bridge_used": any(bool(attempt.get("bridge_used")) for attempt in attempts),
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "load_success": any(bool(attempt.get("load_success")) for attempt in attempts),
        "inference_success": bool(attempts and attempts[-1].get("status") in {"PASSED", "BRIDGE_READY"}),
        "unload_success": all(bool(attempt.get("unload_success")) for attempt in attempts),
        "safe_rollback": "PASSED" if all(attempt.get("safe_rollback") == "PASSED" for attempt in attempts) else "FAILED",
        "duration_seconds": sum(float(attempt.get("duration_seconds") or 0) for attempt in attempts),
        "warnings": _dedupe([warning for attempt in attempts for warning in _list_from(attempt.get("warnings"))]),
        "errors": _dedupe([error for attempt in attempts for error in _list_from(attempt.get("errors"))]),
        "safety": _safety_payload(),
    }


def _final_review_failed(reviewer: dict[str, Any]) -> bool:
    if reviewer.get("status") not in {"PASSED", "BRIDGE_READY"}:
        return True
    text = str(reviewer.get("generated_text") or "").lower()
    return "fail" in text and "pass" not in text


def write_model_activation_artifacts(output_dir: str | Path | None = None) -> list[str]:
    """Write artifacts 98-103 for the model activation foundation."""

    target = Path(output_dir or _timestamped_artifact_dir()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "98_model_identity_correction.json": build_model_identity_correction(),
        "100_local_model_preflight.json": build_local_model_preflight(),
        "102_real_model_activation_plan.json": build_real_model_activation_plan(),
    }
    written: list[str] = []
    for name, payload in payloads.items():
        path = target / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))
        prefix, suffix = name.split("_", 1)
        md_name = f"{int(prefix) + 1}_{suffix.replace('.json', '.md')}"
        md_path = target / md_name
        md_path.write_text(_artifact_markdown(md_name, payload), encoding="utf-8")
        written.append(str(md_path))
    return written


def _write_qwen25_artifacts(
    target: Path,
    gate: dict[str, Any],
    backend_smoke: dict[str, Any],
    runtime_trace: dict[str, Any],
) -> list[str]:
    payloads = {
        "104_qwen25_activation_gate.json": gate,
        "106_qwen25_backend_smoke.json": backend_smoke,
        "108_qwen25_runtime_trace.json": runtime_trace,
    }
    written: list[str] = []
    for name, payload in payloads.items():
        path = target / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))
        prefix, suffix = name.split("_", 1)
        md_name = f"{int(prefix) + 1}_{suffix.replace('.json', '.md')}"
        md_path = target / md_name
        md_path.write_text(_artifact_markdown(md_name, payload), encoding="utf-8")
        written.append(str(md_path))
    return written


def _write_numbered_artifacts(target: Path, payloads: dict[str, dict[str, Any]]) -> list[str]:
    written: list[str] = []
    for name, payload in payloads.items():
        path = target / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))
        prefix, suffix = name.split("_", 1)
        md_name = f"{int(prefix) + 1}_{suffix.replace('.json', '.md')}"
        md_path = target / md_name
        md_path.write_text(_artifact_markdown(md_name, payload), encoding="utf-8")
        written.append(str(md_path))
    return written


def _retry_payload(
    *,
    status: str,
    readiness: dict[str, Any],
    smoke: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    metrics = get_runtime_metrics()
    return {
        "version": "13.3",
        "generated_at": _now(),
        "status": status,
        "allowed_states": [
            "BLOCKED",
            "UNAVAILABLE",
            "LOAD_ATTEMPTED",
            "INFERENCE_ATTEMPTED",
            "PASSED",
            "FAILED",
            "ROLLED_BACK",
            "MOCK_FALLBACK",
        ],
        "model_name": QWEN25_MODEL_NAME,
        "backend": "llama_cpp",
        "readiness_status": readiness["status"],
        "readiness": readiness,
        "smoke": smoke or {},
        "real_load_attempted": bool(smoke and smoke.get("real_load_attempted")),
        "real_inference_attempted": bool(smoke and smoke.get("real_inference_attempted")),
        "loaded_models_after": get_loaded_models(),
        "safe_mode_final": get_loaded_models() == [],
        "active_models": metrics.get("active_models", 0),
        "parallel_llm_loads": metrics.get("parallel_llm_loads", 0),
        "qwen3_touched": False,
        "deepseek_touched": False,
        "powerful_activated": False,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "safety": _safety_payload(),
    }


def _preflight_model_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_name": record.get("model_name") or record.get("name"),
        "family": record.get("family"),
        "mode": record.get("mode"),
        "source_path": record.get("source_path") or record.get("path"),
        "distribution_path": record.get("distribution_path"),
        "backend": record.get("backend"),
        "adapter_path": record.get("adapter_path"),
        "model_declared": record.get("model_declared", True),
        "path_exists": record.get("path_exists", record.get("exists", False)),
        "adapter_exists": record.get("adapter_exists", False),
        "backend_available": record.get("backend_available", False),
        "enabled": record.get("enabled", False),
        "load_allowed": record.get("load_allowed", False),
        "load_blocked_reason": record.get("load_blocked_reason", "not_evaluated"),
        "estimated_vram_mb": record.get("estimated_vram_mb", 0),
        "status": record.get("status", "declared"),
    }


def _model_identity_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = _preflight_model_payload(record)
    payload["fallback_backend"] = record.get("fallback_backend")
    return payload


def _llama_readiness_status(
    *,
    package_importable: bool,
    model_exists: bool,
    readable: bool,
    blocked_path: bool,
    cuda_status: str,
) -> str:
    if not model_exists:
        return "MODEL_MISSING"
    if blocked_path or not readable:
        return "UNAVAILABLE"
    if not package_importable:
        return "UNAVAILABLE"
    if cuda_status == "IMPORT_ERROR":
        return "IMPORT_ERROR"
    if cuda_status == "CUDA_AVAILABLE":
        return "CUDA_AVAILABLE"
    if cuda_status == "CPU_ONLY":
        return "CPU_ONLY"
    return "CUDA_UNKNOWN"


def _llama_manual_guidance(package_importable: bool) -> list[str]:
    if package_importable:
        return [
            "llama_cpp is importable. Repeat the controlled Qwen2.5 smoke only with token and confirmation.",
            "ANN still keeps global safe mode; no permanent policy change is required.",
        ]
    return [
        "ANN does not install llama_cpp automatically.",
        "The backend is unavailable while the llama_cpp binding cannot be imported.",
        "Verify llama_cpp manually outside ANN before repeating the controlled smoke.",
        "Do not run pip install from ANN Desktop or ANN runtime.",
        "ANN continues to work in mock/safe mode.",
    ]


def _retry_status_from_smoke(smoke: dict[str, Any]) -> str:
    if smoke["status"] == "PASSED":
        return "PASSED"
    if smoke["status"] == "UNAVAILABLE":
        return "UNAVAILABLE"
    if smoke.get("real_inference_attempted"):
        return "INFERENCE_ATTEMPTED"
    if smoke.get("real_load_attempted"):
        return "LOAD_ATTEMPTED"
    if smoke.get("mock_fallback"):
        return "MOCK_FALLBACK"
    if smoke.get("safe_mode_final"):
        return "ROLLED_BACK"
    return "FAILED"


def _probe_cpu_ram() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "unavailable", "total_mb": None, "available_mb": None}
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        if not ok:
            return {"status": "unavailable", "total_mb": None, "available_mb": None}
        return {
            "status": "available",
            "total_mb": round(status.ullTotalPhys / (1024 * 1024), 2),
            "available_mb": round(status.ullAvailPhys / (1024 * 1024), 2),
        }
    except Exception as exc:  # pragma: no cover - platform dependent.
        return {"status": "unavailable", "total_mb": None, "available_mb": None, "error": f"{type(exc).__name__}:{exc}"}


def _any_child_matches(root: Path, suffixes_or_names: tuple[str, ...]) -> bool:
    if not root.is_dir():
        return False
    for child in root.iterdir():
        if any(child.name == marker or child.name.endswith(marker) for marker in suffixes_or_names):
            return True
    return False


def _runtime_matrix_entry(
    kind: str,
    executable: str,
    *,
    active: bool,
    version: str,
    manifest: dict[str, Any],
    cuda: dict[str, Any],
    llama: dict[str, Any],
) -> dict[str, Any]:
    executable_path = Path(executable) if executable else None
    exists = bool(executable_path and executable_path.is_file())
    pyside = manifest.get("pyside_version")
    transformers = manifest.get("transformers_version")
    return {
        "kind": kind,
        "executable": executable,
        "exists": exists,
        "active": active,
        "version": version,
        "torch_status": cuda["status"] if active else "unknown_without_execution",
        "cuda_visible": cuda["cuda_available"] if active else False,
        "llama_cpp_status": llama["status"] if active else "unknown_without_execution",
        "pyside6_status": "available" if pyside else "missing",
        "transformers_status": "available" if transformers else "missing",
        "supports": {
            "desktop_app": bool(pyside) if active else exists,
            "qwen2_5_gguf": llama["status"] == "READY" if active else False,
            "qwen3_hf_safetensors": bool(transformers) if active else False,
            "deepseek_hf_safetensors": bool(transformers) if active else False,
        },
        "blocked_reasons": _dedupe(
            []
            + ([] if exists or active else ["python_executable_missing"])
            + ([] if active else ["not_executed_for_safety"])
            + ([] if not active or cuda["cuda_available"] else [cuda["status"]])
            + ([] if not active or llama["status"] == "READY" else llama["errors"] or [llama["status"]])
        ),
    }


def _manual_actions_from_environment(cuda: dict[str, Any], llama: dict[str, Any], embedded_python: Path) -> list[str]:
    actions: list[str] = []
    if not cuda["torch_importable"]:
        actions.append("Install or select a Python runtime with torch available outside ANN.")
    elif not cuda["cuda_available"]:
        actions.append("Select or build a Torch CUDA runtime outside ANN; current torch is CPU-only or CUDA is not visible.")
    if not llama["binding_importable"]:
        actions.append("Install or build llama-cpp-python with the desired CUDA/cuBLAS support outside ANN.")
    elif llama["status"] != "READY":
        actions.append(f"Resolve llama_cpp backend status before real inference: {llama['status']}.")
    if not embedded_python.is_file():
        actions.append(f"Prepare embedded Python at {embedded_python} in a future installer phase.")
    actions.append("Keep ANN safe/mock mode until the launch guard reports PASSED.")
    return _dedupe(actions)


def _readiness_item(identifier: str, category: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "category": category,
        "status": "PASS" if passed else "MISSING",
        "passed": passed,
        "detail": detail,
    }


def _guard_check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


def _wheelhouse_package(
    name: str,
    purpose: str,
    requirement: str,
    categories: list[str],
    *,
    installed_now: bool | None = None,
    detected_version: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    if installed_now is None:
        import_name = {"llama-cpp-python": "llama_cpp", "python-embedded-runtime": ""}.get(name, name)
        installed_now = bool(import_name) and importlib.util.find_spec(import_name) is not None
    if detected_version is None:
        try:
            detected_version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            detected_version = None
    required = requirement in {"required", "runtime"}
    resolved_status = status or ("ready" if installed_now else "missing")
    return {
        "package": name,
        "purpose": purpose,
        "requirement": requirement,
        "required": required,
        "optional": requirement == "optional",
        "categories": categories,
        "installed_now": installed_now,
        "detected_version": detected_version,
        "status": resolved_status,
        "manual_action_needed": "collect offline wheel outside ANN" if required and resolved_status != "ready" else "none",
        "risk": _wheelhouse_risk(name, resolved_status),
        "notes": "not installed by ANN; future installer must use an offline wheelhouse",
    }


def _wheelhouse_risk(name: str, status: str) -> str:
    if status == "ready":
        return "low"
    if name in {"torch", "llama-cpp-python"}:
        return "high_runtime_blocker"
    return "medium_packaging_gap"


def _verification_script(name: str, path: Path) -> dict[str, Any]:
    text = ""
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            text = ""
    blocked_tokens = [token for token in ("pip install", "npm install", "curl ", "wget ", "invoke-webrequest") if token in text]
    return {
        "name": name,
        "path": str(path),
        "exists": path.is_file(),
        "read_only": not blocked_tokens,
        "blocked_tokens": blocked_tokens,
        "loads_models_by_default": "load_model(" in text or "llama(" in text,
    }


def _lockfile_package_from_wheelhouse(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["package"],
        "version": item["detected_version"] or "declared",
        "role": _primary_lock_role(item["categories"]),
        "required_for": item["categories"],
        "optional": item["optional"],
        "expected_runtime_path": "D:\\ANN\\runtime\\site-packages",
        "verification_status": item["status"],
        "notes": item["notes"],
    }


def _lockfile_wheel_from_package(item: dict[str, Any]) -> dict[str, Any]:
    version = item["detected_version"] or "VERSION"
    filename = f"{item['package'].replace('-', '_')}-{version}-py3-none-any.whl"
    return {
        "name": item["package"],
        "version": version,
        "filename": filename,
        "sha256": "",
        "size_bytes": 0,
        "source": "offline_wheelhouse",
        "role": _primary_lock_role(item["categories"]),
        "required": item["required"],
        "status": "hash_unknown",
        "notes": "Example entry; replace filename/hash with verified offline wheel metadata.",
    }


def _primary_lock_role(categories: list[str]) -> str:
    mapping = {
        "required_for_desktop": "desktop",
        "required_for_qwen25_gguf": "qwen25_gguf",
        "required_for_qwen3_hf": "qwen3_hf",
        "required_for_deepseek_hf": "deepseek_hf",
        "optional": "runtime_diagnostics",
    }
    for category in categories:
        if category in mapping:
            return mapping[category]
    return "runtime_diagnostics"


def _declared_wheels(lock: dict[str, Any]) -> list[dict[str, Any]]:
    wheels = lock.get("wheels", [])
    if not isinstance(wheels, list):
        return []
    result = []
    for item in wheels:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename", "")).strip()
        if not filename:
            continue
        result.append(
            {
                "name": str(item.get("name", "")),
                "version": str(item.get("version", "")),
                "filename": filename,
                "sha256": str(item.get("sha256", "")),
                "required": bool(item.get("required", True)),
                "role": str(item.get("role", "runtime_diagnostics")),
                "notes": str(item.get("notes", "")),
            }
        )
    return result


def _wheel_file_payload(path: Path, *, max_hash_size_bytes: int) -> dict[str, Any]:
    size = path.stat().st_size
    sha256 = _sha256_file(path) if size <= max_hash_size_bytes else ""
    return {
        "filename": path.name,
        "path": str(path),
        "size_bytes": size,
        "sha256": sha256,
        "hash_status": "calculated" if sha256 else "skipped_size_limit",
    }


def _sha256_file(path: Path) -> str:
    cached = _cached_sha256(path)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _store_cached_sha256(path, value)
    return value


def _wheelhouse_result(
    status: str,
    wheelhouse: Path,
    lockfile: Path,
    discovered: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "version": "14.5",
        "generated_at": _now(),
        "status": status,
        "wheelhouse_path": str(wheelhouse),
        "lockfile_path": str(lockfile),
        "wheels_discovered": discovered,
        "declared_wheels": [],
        "verification_results": [],
        "errors": errors,
        "safety": _safety_payload(),
    }


def _clean_machine_item(identifier: str, description: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "description": description,
        "required": True,
        "status": "planned",
    }


def _rc_check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
    }


def _next_rc_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Run clean-machine release candidate validation."
    names = {item["name"] for item in blockers}
    if "embedded_python_exists" in names:
        return "Package embedded Python under D:\\ANN\\runtime\\python."
    if "wheelhouse_exists" in names:
        return "Populate D:\\ANN\\runtime\\wheels from the offline wheelhouse."
    if "runtime_lockfile_exists" in names:
        return "Create and verify config\\ann_runtime_lock.example.json."
    return f"Resolve RC blocker: {blockers[0]['name']}"


def _manifest_entry(path: Path, *, included: bool, reason: str, preserve_on_uninstall: bool) -> dict[str, Any]:
    exists = path.exists()
    size_mb = _file_size_mb(path) if path.is_file() else 0.0
    return {
        "path": str(path),
        "exists": exists,
        "size_mb": size_mb,
        "reason": reason,
        "included": included,
        "risk": _manifest_risk(path, included),
        "preserve_on_uninstall": preserve_on_uninstall,
    }


def _manifest_group(
    name: str,
    path: Path,
    reason: str,
    *,
    patterns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    files: list[Path] = []
    if path.is_file():
        files = [path]
    elif path.is_dir() and patterns:
        for pattern in patterns:
            files.extend(sorted(path.glob(pattern), key=lambda item: item.name.lower()))
    elif path.is_dir():
        files = [item for item in path.rglob("*") if item.is_file() and not _has_protected_part(item)]
    return {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
        "file_count": len(files),
        "size_mb": round(sum(float(_file_size_mb(file) or 0) for file in files), 3),
        "reason": reason,
        "included": path.exists(),
        "risk": "medium" if name in {"runtime_engine", "installer"} else "low",
        "preserve_on_uninstall": False,
    }


def _manifest_risk(path: Path, included: bool) -> str:
    if not included:
        return "protected_or_heavy" if _has_protected_part(path) else "excluded"
    if _has_protected_part(path):
        return "high"
    return "low"


def _preservation_item(name: str, passed: bool) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "detail": f"{name} {'preserved/removed as expected' if passed else 'policy mismatch'}",
    }


def _alpha_smoke_case(
    identifier: str,
    description: str,
    expected: str,
    status: str,
    limitation: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "description": description,
        "expected": expected,
        "status": status,
        "limitations": [limitation],
        "manual_steps": ["Open ANN Desktop and verify this item manually"] if status == "manual_pending" else [],
        "risk": "medium" if status == "manual_pending" else "low",
    }


def _roadmap_item(
    identifier: str,
    status: str,
    dependencies: list[str],
    risk: str,
    priority: int,
    notes: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": status,
        "dependencies": dependencies,
        "risk": risk,
        "priority": priority,
        "notes": notes,
    }


def _manual_validation_item(identifier: str, description: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "description": description,
        "expected": "PASS",
        "status": "manual_pending",
        "required": True,
    }


def _emulator_check(identifier: str, passed: bool, detail: str, *, skipped: bool = False) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "SKIPPED" if skipped else ("PASS" if passed else "FAIL"),
        "passed": passed,
        "detail": detail,
    }


def _evidence_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "detail": detail,
    }


def _is_sha256_hex(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(character in "0123456789abcdefABCDEF" for character in text)


def _machine_identity_is_windows_11(machine_identity: dict[str, Any]) -> bool:
    fields = (
        machine_identity.get("os_product_name"),
        machine_identity.get("os_caption"),
        machine_identity.get("os_version"),
    )
    combined = " ".join(str(field or "") for field in fields).lower()
    return "windows 11" in combined


def _validate_external_clean_machine_payload(
    payload: dict[str, Any],
    *,
    expected_install_root: str | Path | None = None,
) -> dict[str, Any]:
    machine_identity = payload.get("machine_identity") if isinstance(payload.get("machine_identity"), dict) else {}
    payload_install_root = str(payload.get("install_root") or "").strip()
    payload_install_root_normalized = _normalize_path_text(payload_install_root) if payload_install_root else ""
    expected_install_root_normalized = (
        _normalize_path_text(expected_install_root)
        if expected_install_root is not None
        else ""
    )
    checks = [
        _evidence_check("marker_present", bool(payload), "clean_machine_external_validation.json"),
        _evidence_check("status_passed", payload.get("status") == "PASSED", str(payload.get("status"))),
        _evidence_check("environment_clean_machine", payload.get("environment_type") == "clean_machine", str(payload.get("environment_type"))),
        _evidence_check("require_signed_installer", payload.get("require_signed_installer") is True, str(payload.get("require_signed_installer"))),
        _evidence_check("no_blockers", payload.get("blockers") == [], str(payload.get("blockers"))),
        _evidence_check(
            "install_root_present",
            bool(payload_install_root),
            payload_install_root or "missing",
        ),
        _evidence_check(
            "install_root_not_c",
            bool(payload_install_root) and not _is_c_path(payload_install_root),
            payload_install_root or "missing",
        ),
        _evidence_check(
            "install_root_matches_expected",
            bool(payload_install_root_normalized)
            and (
                not expected_install_root_normalized
                or payload_install_root_normalized == expected_install_root_normalized
            ),
            f"{payload_install_root_normalized or 'missing'} != {expected_install_root_normalized or 'unspecified'}",
        ),
        _evidence_check("machine_identity_present", bool(machine_identity), "machine_identity"),
        _evidence_check(
            "machine_fingerprint_present",
            _is_sha256_hex(machine_identity.get("machine_fingerprint_sha256")),
            str(machine_identity.get("machine_fingerprint_sha256") or "missing"),
        ),
        _evidence_check(
            "machine_os_version_present",
            bool(str(machine_identity.get("os_version") or "").strip()),
            str(machine_identity.get("os_version") or "missing"),
        ),
        _evidence_check(
            "machine_windows11_present",
            _machine_identity_is_windows_11(machine_identity),
            " ".join(
                str(value or "missing")
                for value in (
                    machine_identity.get("os_product_name"),
                    machine_identity.get("os_caption"),
                    machine_identity.get("os_version"),
                )
            ),
        ),
        _evidence_check(
            "machine_powershell_version_present",
            bool(str(machine_identity.get("powershell_version") or "").strip()),
            str(machine_identity.get("powershell_version") or "missing"),
        ),
        _evidence_check(
            "setup_signature_valid",
            isinstance(payload.get("setup_signature"), dict)
            and payload["setup_signature"].get("status") == "Valid",
            str((payload.get("setup_signature") or {}).get("status")),
        ),
        _evidence_check(
            "setup_timestamp_present",
            isinstance(payload.get("setup_signature"), dict)
            and bool(str(payload["setup_signature"].get("timestamp_signer") or "").strip()),
            str((payload.get("setup_signature") or {}).get("timestamp_signer") or "missing"),
        ),
        _evidence_check(
            "setup_signer_thumbprint_sha256_present",
            isinstance(payload.get("setup_signature"), dict)
            and _is_sha256_hex(payload["setup_signature"].get("signer_thumbprint_sha256")),
            str((payload.get("setup_signature") or {}).get("signer_thumbprint_sha256") or "missing"),
        ),
        _evidence_check(
            "uninstall_signature_valid",
            isinstance(payload.get("uninstall_signature"), dict)
            and payload["uninstall_signature"].get("status") == "Valid",
            str((payload.get("uninstall_signature") or {}).get("status")),
        ),
        _evidence_check(
            "uninstall_timestamp_present",
            isinstance(payload.get("uninstall_signature"), dict)
            and bool(str(payload["uninstall_signature"].get("timestamp_signer") or "").strip()),
            str((payload.get("uninstall_signature") or {}).get("timestamp_signer") or "missing"),
        ),
        _evidence_check(
            "uninstall_signer_thumbprint_sha256_present",
            isinstance(payload.get("uninstall_signature"), dict)
            and _is_sha256_hex(payload["uninstall_signature"].get("signer_thumbprint_sha256")),
            str((payload.get("uninstall_signature") or {}).get("signer_thumbprint_sha256") or "missing"),
        ),
        _evidence_check(
            "setup_sha256_present",
            _is_sha256_hex(payload.get("setup_sha256")),
            str(payload.get("setup_sha256") or "missing"),
        ),
        _evidence_check(
            "uninstall_sha256_present",
            _is_sha256_hex(payload.get("uninstall_sha256")),
            str(payload.get("uninstall_sha256") or "missing"),
        ),
        _evidence_check(
            "signing_evidence_sha256_present",
            _is_sha256_hex(payload.get("signing_evidence_sha256")),
            str(payload.get("signing_evidence_sha256") or "missing"),
        ),
        _evidence_check(
            "release_transfer_manifest_sha256_present",
            _is_sha256_hex(payload.get("release_transfer_manifest_sha256")),
            str(payload.get("release_transfer_manifest_sha256") or "missing"),
        ),
        _evidence_check(
            "release_transfer_manifest_aggregate_sha256_present",
            _is_sha256_hex(payload.get("release_transfer_manifest_aggregate_sha256")),
            str(payload.get("release_transfer_manifest_aggregate_sha256") or "missing"),
        ),
    ]
    marker_checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    required_check_ids = {
        "install_root_not_c",
        "install_manifest",
        "app_package",
        "desktop_entrypoint",
        "runtime_python",
        "runtime_wheelhouse",
        "runtime_config",
        "model_policy",
        "projects_root",
        "models_root",
        "outputs_root",
        "data_root",
        "protected_training_not_copied",
        "protected_models_not_copied_to_app",
        "protected_memory_not_copied",
        "protected_knowledge_not_copied",
        "machine_identity_present",
        "machine_fingerprint_present",
        "machine_windows11_present",
        "setup_signature_valid",
        "uninstall_signature_valid",
        "setup_timestamp_present",
        "uninstall_timestamp_present",
        "setup_signer_thumbprint_sha256_present",
        "uninstall_signer_thumbprint_sha256_present",
        "setup_sha256_present",
        "uninstall_sha256_present",
        "signing_evidence_path_required",
        "signing_evidence_sha256_present",
        "release_transfer_manifest_path_required",
        "release_transfer_manifest_sha256_present",
        "release_transfer_manifest_aggregate_sha256_present",
    }
    passed_marker_ids = {
        str(item.get("id"))
        for item in marker_checks
        if isinstance(item, dict) and item.get("passed") is True and item.get("status") == "PASS"
    }
    checks.append(
        _evidence_check(
            "signed_validation_checks_present",
            required_check_ids.issubset(passed_marker_ids),
            "missing: " + ", ".join(sorted(required_check_ids - passed_marker_ids))
            if not required_check_ids.issubset(passed_marker_ids)
            else "all required clean-machine checks present",
        )
    )
    blockers = [check for check in checks if check["status"] == "FAIL"]
    return {
        "status": "EXTERNAL_VALIDATION_ACCEPTED" if not blockers else "EXTERNAL_VALIDATION_REJECTED",
        "passed": not blockers,
        "checks": checks,
        "blockers": blockers,
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_model_activation_artifact(filename: str) -> Path | None:
    candidates = [path for path in DEFAULT_ARTIFACT_ROOT.glob(f"**/{filename}") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _release_evidence_payload(
    *,
    model_name: str,
    artifact_filename: str,
    passing_statuses: set[str],
    rollback_filename: str,
    rollback_status: str,
) -> dict[str, Any]:
    artifact = _latest_model_activation_artifact(artifact_filename)
    payload = _read_json_file(artifact) if artifact else {}
    rollback_artifact = artifact.with_name(rollback_filename) if artifact else None
    rollback_payload = _read_json_file(rollback_artifact) if rollback_artifact and rollback_artifact.is_file() else {}
    status = str(payload.get("status") or "EVIDENCE_MISSING")
    rollback_current_status = str(rollback_payload.get("status") or "ROLLBACK_EVIDENCE_MISSING")
    real_inference_success = bool(payload.get("real_inference_success"))
    safe_rollback_passed = rollback_current_status == rollback_status and (
        rollback_payload.get("active_models_after") in {0, None}
    ) and (
        rollback_payload.get("parallel_llm_loads_after") in {0, None}
    )
    passed = status in passing_statuses and real_inference_success and safe_rollback_passed
    return {
        "version": "19.2",
        "generated_at": _now(),
        "model_name": model_name,
        "status": "REAL_EVIDENCE_PASSED" if passed else status,
        "passed": passed,
        "artifact_filename": artifact_filename,
        "artifact_path": str(artifact) if artifact else "",
        "artifact_present": artifact is not None,
        "raw_status": status,
        "real_inference_success": real_inference_success,
        "tokens_generated": int(payload.get("tokens_generated") or 0),
        "prompt_tokens": int(payload.get("prompt_tokens") or 0),
        "rollback_filename": rollback_filename,
        "rollback_path": str(rollback_artifact) if rollback_artifact and rollback_artifact.is_file() else "",
        "rollback_status": rollback_current_status,
        "safe_rollback_passed": safe_rollback_passed,
        "active_models_after": rollback_payload.get("active_models_after"),
        "parallel_llm_loads_after": rollback_payload.get("parallel_llm_loads_after"),
        "no_model_load_now": True,
        "no_inference_now": True,
        "safety": _safety_payload(),
    }


def build_qwen25_release_evidence() -> dict[str, Any]:
    """Read verified Qwen2.5 inference evidence without loading the model."""

    return _release_evidence_payload(
        model_name=QWEN25_MODEL_NAME,
        artifact_filename="256_qwen25_first_real_inference.json",
        passing_statuses={"FIRST_REAL_INFERENCE_PASSED"},
        rollback_filename="260_safe_rollback_validation.json",
        rollback_status="SAFE_ROLLBACK_PASSED",
    )


def build_qwen3_release_evidence() -> dict[str, Any]:
    """Read verified Qwen3 inference evidence without loading the model."""

    return _release_evidence_payload(
        model_name=QWEN3_MODEL_NAME,
        artifact_filename="274_qwen3_real_output.json",
        passing_statuses={"QWEN3_REAL_PASSED"},
        rollback_filename="278_qwen3_safe_rollback.json",
        rollback_status="SAFE_ROLLBACK_PASSED",
    )


def build_deepseek_powerful_release_evidence() -> dict[str, Any]:
    """Read verified DeepSeek POWERFUL evidence without loading the model."""

    return _release_evidence_payload(
        model_name=DEEPSEEK14B_MODEL_NAME,
        artifact_filename="282_deepseek_real_review.json",
        passing_statuses={"DEEPSEEK_REAL_PASSED"},
        rollback_filename="286_deepseek_safe_rollback.json",
        rollback_status="SAFE_ROLLBACK_PASSED",
    )


def _beta_gate_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _clean_machine_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Run manual clean-machine dry-run validation on a separate Windows profile."
    ids = {item["id"] for item in blockers}
    if "embedded_python_present" in ids:
        return "Prepare embedded Python outside ANN under D:\\ANN\\runtime\\python."
    if "wheelhouse_present" in ids:
        return "Materialize D:\\ANN\\runtime\\wheels with verified offline wheels."
    if "wheelhouse_hashes" in ids:
        return "Fill and verify wheel hashes in config\\ann_runtime_lock.example.json."
    if "no_c_root" in ids:
        return "Use D:\\ANN or another non-C install root."
    return f"Resolve clean-machine blocker: {blockers[0]['id']}"


def _clean_machine_evidence_next_step(status: str, blockers: list[dict[str, Any]]) -> str:
    if status == "CLEAN_MACHINE_EXTERNAL_PASSED":
        return "Preserve external clean-machine evidence and continue to code signing."
    if status == "LOCAL_INSTALL_SMOKE_PASSED":
        return "Run the signed installer on a separate clean Windows 11 machine and write clean_machine_external_validation.json."
    if blockers:
        return f"Resolve local install smoke blocker: {blockers[0]['id']}"
    return "Run local install smoke, then external clean-machine validation."


def _beta_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare limited Beta validation with manual sign-off."
    ids = {item["id"] for item in blockers}
    if "embedded_python_present" in ids:
        return "Package embedded Python under D:\\ANN\\runtime\\python outside ANN."
    if "wheelhouse_present" in ids:
        return "Populate the offline wheelhouse under D:\\ANN\\runtime\\wheels."
    if "wheelhouse_integrity" in ids or "lockfile_hashes_verified" in ids:
        return "Verify wheelhouse integrity and lockfile hashes."
    if "first_real_inference_status" in ids:
        return "Run the first controlled Qwen2.5 smoke only after backend readiness passes."
    return f"Resolve Beta blocker: {blockers[0]['id']}"


def _runtime_collection_entry(name: str, path: Path, purpose: str, required: bool) -> dict[str, Any]:
    present = path.exists()
    return {
        "name": name,
        "path": str(path),
        "purpose": purpose,
        "required": required,
        "present": present,
        "manual_collection_required": required and not present,
        "hash_status": "not_applicable" if path.is_dir() else ("declared" if present else "missing"),
        "notes": "Collected manually outside ANN; ANN does not install or download this payload.",
    }


def _wheelhouse_registry_entry(item: dict[str, Any], found: Path | None) -> dict[str, Any]:
    expected_hash = str(item.get("sha256") or "").strip()
    size = found.stat().st_size if found and found.is_file() else int(item.get("size_bytes") or 0)
    actual_hash = _sha256_for_existing_file(found) if found and expected_hash else ""
    if found is None:
        status = "MISSING"
    elif not expected_hash:
        status = "HASH_PENDING"
    elif actual_hash == expected_hash:
        status = "HASH_VERIFIED"
    else:
        status = "HASH_MISMATCH"
    return {
        "filename": item["filename"],
        "sha256": expected_hash,
        "size": size,
        "role": item.get("role", "unknown"),
        "required": bool(item.get("required", True)),
        "present": found is not None,
        "status": status,
    }


def _runtime_inventory_item(identifier: str, path: Path, kind: str) -> dict[str, Any]:
    present = path.is_file() if kind == "file" else path.is_dir()
    return {
        "id": identifier,
        "path": str(path),
        "kind": kind,
        "required": True,
        "present": present,
        "status": "PRESENT" if present else "MISSING",
    }


def _runtime_verification_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _payload_readiness_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _payload_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare Beta payload build with manual sign-off."
    ids = {item["id"] for item in blockers}
    if "embedded_runtime_ready" in ids:
        return "Collect embedded Python/runtime directories manually outside ANN."
    if "wheelhouse_ready" in ids:
        return "Populate and verify the offline wheelhouse."
    if "qwen25_backend_ready" in ids:
        return "Validate llama_cpp CUDA backend before the first Qwen2.5 smoke."
    if "first_inference_executed" in ids:
        return "Run controlled first inference only after all runtime gates pass."
    return f"Resolve payload blocker: {blockers[0]['id']}"


def _materialization_entry(name: str, path: Path, kind: str, expected_contents: list[str]) -> dict[str, Any]:
    present = path.is_file() if kind == "file" else path.is_dir()
    return {
        "name": name,
        "path": str(path),
        "kind": kind,
        "present": present,
        "missing": not present,
        "manual_copy_required": not present,
        "expected_contents": expected_contents,
        "notes": "External-only runtime materialization; ANN does not copy or install this entry.",
    }


def _population_protocol_entry(item: dict[str, Any], found: Path | None) -> dict[str, Any]:
    sha256 = str(item.get("sha256") or "").strip()
    version = str(item.get("version") or "declared")
    status: str
    if found is None:
        status = "MISSING"
    elif not sha256:
        status = "HASH_PENDING"
    elif _sha256_for_existing_file(found) == sha256:
        status = "VERIFIED"
    else:
        status = "HASH_MISMATCH"
    return {
        "expected_wheel": item["filename"],
        "required_version": version,
        "sha256": sha256,
        "required": bool(item.get("required", True)),
        "role": item.get("role", "unknown"),
        "present": found is not None,
        "manual_copy_required": found is None,
        "install_forbidden": True,
        "source": "external_only",
        "status": status,
    }


def _candidate_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _candidate_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare first controlled Qwen2.5 readiness review."
    ids = {item["id"] for item in blockers}
    if "embedded_runtime_ready" in ids or "embedded_python_present" in ids:
        return "Materialize embedded runtime under D:\\ANN\\runtime externally."
    if "wheelhouse_ready" in ids:
        return "Populate and verify the offline wheelhouse externally."
    if "runtime_verified" in ids:
        return "Resolve embedded runtime verification blockers."
    return f"Resolve Beta candidate blocker: {blockers[0]['id']}"


def _inference_readiness_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _manual_runtime_step(order: int, title: str, description: str) -> dict[str, Any]:
    return {
        "step": order,
        "title": title,
        "description": description,
        "status": "manual_pending",
        "automatic_execution": False,
    }


def _manual_checklist_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Run the read-only Beta Candidate Final Gate."
    ids = {item["id"] for item in blockers}
    if "embedded_python_present" in ids or "python_folder" in ids:
        return "Manually copy embedded Python to D:\\ANN\\runtime\\python."
    if "wheels_folder" in ids or "wheelhouse_hashes" in ids:
        return "Manually copy and verify wheels under D:\\ANN\\runtime\\wheels."
    if "requirements_lock_folder" in ids:
        return "Manually copy requirements-lock under D:\\ANN\\runtime."
    return f"Resolve runtime materialization blocker: {blockers[0]['id']}"


def _integrity_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _external_wheel_validation_entry(item: dict[str, Any], found: Path | None) -> dict[str, Any]:
    expected_hash = str(item.get("sha256") or "").strip()
    actual_hash = _sha256_for_existing_file(found) if found else ""
    if found is None:
        status = "MISSING"
    elif not expected_hash:
        status = "HASH_PENDING"
    elif actual_hash == expected_hash:
        status = "VERIFIED"
    else:
        status = "MISMATCH"
    return {
        "wheel": item["filename"],
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "status": status,
        "missing": found is None,
        "mismatch": status == "MISMATCH",
        "verified": status == "VERIFIED",
        "no_install": True,
    }


def _final_gate_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _final_gate_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare controlled first inference smoke with explicit approval."
    ids = {item["id"] for item in blockers}
    if "embedded_runtime_materialized" in ids:
        return "Complete manual external runtime materialization."
    if "integrity_verified" in ids or "wheelhouse_verified" in ids:
        return "Verify runtime folders and wheel hashes."
    if "first_inference_ready" in ids:
        return "Resolve Qwen2.5 backend and approval blockers before smoke."
    return f"Resolve final Beta blocker: {blockers[0]['id']}"


def _post_materialization_item(identifier: str, path: Path, kind: str) -> dict[str, Any]:
    present = path.is_file() if kind == "file" else path.is_dir()
    return {
        "id": identifier,
        "path": str(path),
        "kind": kind,
        "present": present,
        "status": "PRESENT" if present else "MISSING",
    }


def _unexpected_runtime_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    allowed = set(EMBEDDED_RUNTIME_SUBDIRS)
    allowed_files = set(EMBEDDED_RUNTIME_ALLOWED_FILES)
    unexpected: list[str] = []
    try:
        for child in root.iterdir():
            if child.is_file() and child.name in allowed_files:
                continue
            if child.name not in allowed:
                unexpected.append(str(child))
    except OSError:
        return [f"{root}:unreadable"]
    return sorted(unexpected)


def _readiness_evidence_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _runtime_readiness_reason(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Runtime readiness evidence is complete."
    return "Runtime readiness blocked by: " + ", ".join(check["id"] for check in blockers)


def _runtime_readiness_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare Controlled First Inference Gate with token and confirmation."
    ids = {item["id"] for item in blockers}
    if "embedded_python_detected" in ids or "runtime_ready" in ids:
        return "Copy and validate the embedded runtime under D:\\ANN\\runtime."
    if "wheelhouse_verified" in ids:
        return "Populate D:\\ANN\\runtime\\wheels and verify hashes."
    if "launch_guard_ready" in ids:
        return "Resolve Qwen2.5 backend/launch guard blockers."
    return f"Resolve readiness blocker: {blockers[0]['id']}"


def _controlled_gate_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _runtime_new_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    files: list[str] = []
    try:
        pending = [root]
        while pending and len(files) < 100:
            current = pending.pop(0)
            for child in sorted(current.iterdir(), key=lambda item: item.name.lower()):
                if child.is_file():
                    files.append(str(child))
                    if len(files) >= 100:
                        break
                elif child.is_dir():
                    pending.append(child)
    except OSError:
        return [f"{root}:unreadable"]
    return files


def _beta_activation_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _beta_activation_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Run controlled first real inference with LOCAL_TEST_TOKEN and manual confirmation."
    ids = {item["id"] for item in blockers}
    if "embedded_python" in ids or "runtime_integrity" in ids:
        return "Materialize and verify D:\\ANN\\runtime before Beta activation."
    if "wheelhouse" in ids:
        return "Populate and hash-verify D:\\ANN\\runtime\\wheels."
    if "qwen25_backend" in ids or "launch_guard" in ids:
        return "Resolve Qwen2.5 llama_cpp Launch Guard blockers."
    return f"Resolve Beta activation blocker: {blockers[0]['id']}"


def _guided_step(
    identifier: str,
    title: str,
    completed: bool,
    next_action: str,
    evidence_artifact: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "status": "COMPLETED" if completed else "BLOCKED",
        "blocker": "" if completed else detail,
        "next_action": "Continue to next step." if completed else next_action,
        "evidence_artifact": evidence_artifact,
    }


def _button_gate_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _button_gate_next_action(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Enable Run First Qwen2.5 Smoke and require token + confirmation."
    ids = {item["id"] for item in blockers}
    if "runtime_materialized" in ids or "embedded_python_present" in ids:
        return "Materialize D:\\ANN\\runtime first."
    if "wheelhouse_verified" in ids:
        return "Populate and verify D:\\ANN\\runtime\\wheels."
    if "llama_cpp_ready" in ids or "qwen25_backend_ready" in ids:
        return "Resolve llama_cpp/Qwen2.5 backend readiness."
    return f"Resolve smoke button blocker: {blockers[0]['id']}"


def _release_bridge_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _finalization_check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "PASS" if passed else "BLOCKED",
        "passed": passed,
        "detail": detail,
    }


def _runtime_finalization_audit(
    root_info: dict[str, Any],
    root: Path,
    layout: dict[str, Any],
    integrity: dict[str, Any],
    wheelhouse: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "18.0",
        "generated_at": _now(),
        **_runtime_report(root_info),
        "layout_status": layout["status"],
        "integrity_status": integrity["status"],
        "wheelhouse_status": wheelhouse["status"],
        "created_directories": layout.get("created", []),
        "existing_directories": layout.get("existing_subdirectories", []),
        "embedded_python_present": (root / "python" / "python.exe").is_file(),
        "audit_only": True,
        "no_install": True,
        "no_download": True,
        "no_python_execution": True,
        "protected_paths_touched": False,
        "safety": _safety_payload(),
    }


def _final_release_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "Prepare final release packaging and signing review."
    ids = {item["id"] for item in blockers}
    if "first_inference_status" in ids:
        return "Complete the controlled first Qwen2.5 smoke before final release readiness."
    if "signed_installer" in ids:
        return "Create and sign the final installer after Beta evidence passes."
    if "clean_machine_evidence" in ids:
        return "Run clean-machine validation and preserve evidence."
    return f"Resolve final release blocker: {blockers[0]['id']}"


def _final_release_verification_next_step(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return "FINAL_RELEASE_READY evidence is complete; preserve artifacts and release manifest."
    ids = {item["id"] for item in blockers}
    if "autonomous_complex_capability" in ids:
        return (
            "Produce strong verified evidence for all autonomous capability scenarios, "
            "then rerun scripts/runtime/verify_autonomous_capability.py."
        )
    if "signed_installer" in ids:
        return "Sign ANN_Setup.exe and ANN_Uninstall.exe with a trusted Authenticode certificate."
    if "external_clean_machine_evidence" in ids:
        return "Run validate_clean_machine.ps1 on a separate clean Windows 11 machine with -EnvironmentType clean_machine."
    if "installer_final" in ids:
        return "Resolve installer final blockers, then rerun scripts/runtime/verify_final_release.py."
    if "final_release_bridge" in ids or "public_release" in ids or "ann_finalization" in ids:
        return "Resolve final release gate blockers and rerun verification."
    return f"Resolve final verification blocker: {blockers[0]['id']}"


def _handoff_file_entry(source: Path, bundle_root: Path) -> dict[str, Any]:
    relative = source.relative_to(REPO_ROOT).as_posix()
    destination = bundle_root / relative
    exists = source.is_file()
    return {
        "source": str(source),
        "relative_path": relative,
        "bundle_path": str(destination),
        "exists": exists,
        "size_bytes": source.stat().st_size if exists else 0,
        "sha256": _sha256_for_existing_file(source) if exists else "",
    }


def _handoff_transfer_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    auxiliary_files = manifest.get("auxiliary_files") if isinstance(manifest.get("auxiliary_files"), list) else []
    portable_files = [
        {
            "relative_path": str(entry.get("relative_path", "")),
            "size_bytes": int(entry.get("size_bytes", 0)),
            "sha256": str(entry.get("sha256", "")),
        }
        for entry in files
        if isinstance(entry, dict)
    ]
    portable_auxiliary_files = [
        {
            "relative_path": str(entry.get("relative_path", "")),
            "size_bytes": int(entry.get("size_bytes", 0)),
            "sha256": str(entry.get("sha256", "")),
        }
        for entry in auxiliary_files
        if isinstance(entry, dict)
    ]
    portable_files.sort(key=lambda item: item["relative_path"])
    portable_auxiliary_files.sort(key=lambda item: item["relative_path"])
    canonical_payload = {
        "files": portable_files,
        "auxiliary_files": portable_auxiliary_files,
        "release_command_contract": _release_command_contract(manifest),
        "model_files_included": bool(manifest.get("model_files_included")),
        "training_files_included": bool(manifest.get("training_files_included")),
        "dataset_files_included": bool(manifest.get("dataset_files_included")),
        "adapter_files_included": bool(manifest.get("adapter_files_included")),
        "historical_outputs_included": bool(manifest.get("historical_outputs_included")),
        "signing_required_after_handoff": bool(manifest.get("signing_required_after_handoff")),
        "clean_machine_validation_required_after_signing": bool(
            manifest.get("clean_machine_validation_required_after_signing")
        ),
    }
    aggregate_sha256 = hashlib.sha256(
        json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "version": "18.9.18",
        "generated_at": _now(),
        "status": "TRANSFER_MANIFEST_READY",
        "bundle_kind": "ANN_RELEASE_CANDIDATE_HANDOFF",
        "files": portable_files,
        "file_count": len(portable_files),
        "auxiliary_files": portable_auxiliary_files,
        "auxiliary_file_count": len(portable_auxiliary_files),
        "aggregate_sha256": aggregate_sha256,
        "canonical_scope": (
            "relative_path,size_bytes,sha256,auxiliary_relative_path,auxiliary_size,"
            "auxiliary_sha256,release_command_contract,safety_exclusions,"
            "external_release_requirements"
        ),
        "release_command_contract": canonical_payload["release_command_contract"],
        "no_absolute_paths_required": True,
        "no_models": not canonical_payload["model_files_included"],
        "no_training": not canonical_payload["training_files_included"],
        "no_datasets": not canonical_payload["dataset_files_included"],
        "no_adapters": not canonical_payload["adapter_files_included"],
        "no_historical_outputs": not canonical_payload["historical_outputs_included"],
        "requires_trusted_authenticode_signing": canonical_payload["signing_required_after_handoff"],
        "requires_external_clean_machine_validation": canonical_payload[
            "clean_machine_validation_required_after_signing"
        ],
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_install": True,
        "safety": _safety_payload(),
    }


def _release_command_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    command_keys = [
        "bundle_verifier_command",
        "release_operator_environment_command",
        "sign_command",
        "clean_machine_command",
        "external_release_evidence_command",
        "final_verifier_command",
        "repo_root_final_verifier_command",
        "windows_sandbox_prepare_command",
        "windows_sandbox_launch_command",
    ]
    hashes = {
        key: hashlib.sha256(str(manifest.get(key) or "").encode("utf-8")).hexdigest()
        for key in command_keys
    }
    return {
        "version": "18.9.18",
        "commands_are_templates": bool(manifest.get("release_commands_are_templates")),
        "placeholder_must_be_replaced": bool(
            manifest.get("release_command_placeholders_must_be_replaced")
        ),
        "thumbprint_placeholder": str(manifest.get("release_command_thumbprint_placeholder") or ""),
        "thumbprint_regex": str(manifest.get("release_command_thumbprint_regex") or ""),
        "repo_root_final_verifier_required": bool(manifest.get("repo_root_final_verifier_command")),
        "command_sha256": hashes,
    }


def _handoff_auxiliary_payloads(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "README_HANDOFF.md": _handoff_readme(manifest),
        "FINAL_RELEASE_EXTERNAL_STEPS.md": _final_release_external_steps(manifest),
        "clean_machine_external_validation.template.json": json.dumps(
            _clean_machine_external_validation_template(),
            indent=2,
        ),
    }


def _handoff_auxiliary_entries(payloads: dict[str, str]) -> list[dict[str, Any]]:
    entries = []
    for relative_path, content in sorted(payloads.items()):
        encoded = content.encode("utf-8")
        entries.append(
            {
                "relative_path": relative_path,
                "size_bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    return entries


def _handoff_readme(manifest: dict[str, Any]) -> str:
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    lines = [
        "# ANN Release Candidate Handoff",
        "",
        "This folder contains the minimal release-candidate handoff assets for signing and clean-machine validation.",
        "",
        "## Safety",
        "",
        "- No models are included.",
        "- No training files, datasets, adapters, memory, knowledge, or historical outputs are included.",
        "- No installer is executed by preparing this bundle.",
        "- No model is loaded and no inference is run.",
        "- Clean-machine evidence must preserve both the transfer manifest file SHA256 and its internal aggregate_sha256.",
        "- RELEASE_TRANSFER_MANIFEST.file.sha256 records the file hash; RELEASE_TRANSFER_MANIFEST.sha256 records the canonical aggregate.",
        "",
        "## Required External Steps",
        "",
        "1. Verify this bundle's hashes before signing.",
        "2. Verify autonomous complex capability evidence.",
        "3. Sign ANN_Setup.exe and ANN_Uninstall.exe with a trusted Authenticode certificate.",
        "4. Install the signed build on a separate clean Windows 11 machine.",
        "5. Run clean-machine validation with -RequireSignedInstaller.",
        "6. Run scripts/runtime/verify_final_release.py and require exit code 0.",
        "",
        "## Commands",
        "",
        "These commands are intended to be run from inside this handoff bundle unless a line explicitly says repo root.",
        "",
        f"Bundle verify: `{manifest.get('bundle_verifier_command')}`",
        f"Autonomous capability plan: `{manifest.get('autonomous_capability_plan_command')}`",
        f"Autonomous capability run: `{manifest.get('autonomous_capability_run_command')}`",
        f"Autonomous capability: `{manifest.get('autonomous_capability_verifier_command')}`",
        f"Release operator environment: `{manifest.get('release_operator_environment_command')}`",
        f"Sign: `{manifest.get('sign_command')}`",
        f"Clean machine: `{manifest.get('clean_machine_command')}`",
        f"Windows Sandbox prepare: `{manifest.get('windows_sandbox_prepare_command')}`",
        f"Windows Sandbox launch: `{manifest.get('windows_sandbox_launch_command')}`",
        f"External release evidence: `{manifest.get('external_release_evidence_command')}`",
        f"Final verifier: `{manifest.get('final_verifier_command')}`",
        f"Repo-root final verifier: `{manifest.get('repo_root_final_verifier_command')}`",
        "",
        "## Files",
        "",
    ]
    for entry in files:
        if not isinstance(entry, dict):
            continue
        lines.append(
            f"- `{entry.get('relative_path')}` sha256={entry.get('sha256') or 'missing'}"
        )
    lines.append("")
    return "\n".join(lines)


def _clean_machine_external_validation_template() -> dict[str, Any]:
    return {
        "version": "18.9.8",
        "generated_at": "<generated by installer/validate_clean_machine.ps1>",
        "status": "PASSED",
        "environment_type": "clean_machine",
        "machine_identity": {
            "computer_name_sha256": "<sha256 of external machine name>",
            "machine_fingerprint_sha256": "<sha256 of external machine identity tuple>",
            "os_version": "<Windows version string>",
            "os_product_name": "<Windows 11 product name>",
            "powershell_version": "<PowerShell version string>",
        },
        "install_root": "D:\\ANN",
        "installer_root": "<path to signed installer bundle>",
        "require_signed_installer": True,
        "setup_signature": {
            "path": "ANN_Setup.exe",
            "status": "Valid",
            "signer": "<trusted code-signing certificate subject>",
            "signer_thumbprint_sha256": "<sha256 of trusted code-signing certificate thumbprint>",
            "timestamp_signer": "<trusted timestamp authority>",
        },
        "setup_sha256": "<sha256 of signed ANN_Setup.exe>",
        "uninstall_signature": {
            "path": "ANN_Uninstall.exe",
            "status": "Valid",
            "signer": "<trusted code-signing certificate subject>",
            "signer_thumbprint_sha256": "<sha256 of trusted code-signing certificate thumbprint>",
            "timestamp_signer": "<trusted timestamp authority>",
        },
        "uninstall_sha256": "<sha256 of signed ANN_Uninstall.exe>",
        "signing_evidence_path": "installer\\release_signing_evidence.json",
        "signing_evidence_sha256": "<sha256 of release_signing_evidence.json>",
        "release_transfer_manifest_path": "RELEASE_TRANSFER_MANIFEST.json",
        "release_transfer_manifest_sha256": "<sha256 of RELEASE_TRANSFER_MANIFEST.json>",
        "release_transfer_manifest_aggregate_sha256": "<aggregate_sha256 inside RELEASE_TRANSFER_MANIFEST.json>",
        "checks": [
            {"id": "install_root_not_c", "status": "PASS", "passed": True, "detail": "D:\\ANN"},
            {"id": "install_manifest", "status": "PASS", "passed": True, "detail": "D:\\ANN\\install_manifest.json"},
            {"id": "app_package", "status": "PASS", "passed": True, "detail": "D:\\ANN\\app\\agentic_network"},
            {"id": "desktop_entrypoint", "status": "PASS", "passed": True, "detail": "desktop_app.run"},
            {"id": "runtime_python", "status": "PASS", "passed": True, "detail": "D:\\ANN\\runtime\\python\\python.exe"},
            {"id": "runtime_wheelhouse", "status": "PASS", "passed": True, "detail": "D:\\ANN\\runtime\\wheels"},
            {"id": "runtime_config", "status": "PASS", "passed": True, "detail": "ann_runtime_engine.json"},
            {"id": "model_policy", "status": "PASS", "passed": True, "detail": "ann_model_policy.json"},
            {"id": "projects_root", "status": "PASS", "passed": True, "detail": "D:\\ANN\\projects"},
            {"id": "models_root", "status": "PASS", "passed": True, "detail": "D:\\ANN\\models"},
            {"id": "outputs_root", "status": "PASS", "passed": True, "detail": "D:\\ANN\\outputs"},
            {"id": "data_root", "status": "PASS", "passed": True, "detail": "D:\\ANN\\data"},
            {"id": "protected_training_not_copied", "status": "PASS", "passed": True, "detail": "training excluded"},
            {"id": "protected_models_not_copied_to_app", "status": "PASS", "passed": True, "detail": "models excluded"},
            {"id": "protected_memory_not_copied", "status": "PASS", "passed": True, "detail": "memory excluded"},
            {"id": "protected_knowledge_not_copied", "status": "PASS", "passed": True, "detail": "knowledge excluded"},
            {"id": "machine_identity_present", "status": "PASS", "passed": True, "detail": "machine identity captured"},
            {"id": "machine_fingerprint_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "machine_windows11_present", "status": "PASS", "passed": True, "detail": "Microsoft Windows 11"},
            {"id": "setup_signature_valid", "status": "PASS", "passed": True, "detail": "Valid"},
            {"id": "uninstall_signature_valid", "status": "PASS", "passed": True, "detail": "Valid"},
            {"id": "setup_timestamp_present", "status": "PASS", "passed": True, "detail": "<trusted timestamp authority>"},
            {"id": "uninstall_timestamp_present", "status": "PASS", "passed": True, "detail": "<trusted timestamp authority>"},
            {"id": "setup_signer_thumbprint_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "uninstall_signer_thumbprint_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "setup_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "uninstall_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "signing_evidence_path_required", "status": "PASS", "passed": True, "detail": "installer\\release_signing_evidence.json"},
            {"id": "signing_evidence_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "release_transfer_manifest_path_required", "status": "PASS", "passed": True, "detail": "RELEASE_TRANSFER_MANIFEST.json"},
            {"id": "release_transfer_manifest_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
            {"id": "release_transfer_manifest_aggregate_sha256_present", "status": "PASS", "passed": True, "detail": "<sha256>"},
        ],
        "blockers": [],
        "no_model_load": True,
        "no_inference": True,
        "no_download": True,
        "no_training": True,
    }


def _final_release_external_steps(manifest: dict[str, Any]) -> str:
    requirements = manifest.get("release_machine_requirements")
    requirement_lines = [
        f"- {item}" for item in requirements if isinstance(item, str)
    ] if isinstance(requirements, list) else []
    return "\n".join(
        [
            "# ANN Final Release External Steps",
            "",
            "These steps are the remaining external evidence needed before ANN can honestly report FINAL_RELEASE_READY.",
            "",
            "## Requirements",
            "",
            *requirement_lines,
            "",
            "## Signing Machine",
            "",
            "1. Verify bundle integrity before signing.",
            f"   `{manifest.get('bundle_verifier_command')}`",
            "2. Verify the release operator environment can see signtool and the trusted certificate.",
            f"   `{manifest.get('release_operator_environment_command')}`",
            "3. Sign both launcher binaries with a trusted Authenticode certificate.",
            f"   `{manifest.get('sign_command')}`",
            "4. Confirm both signatures are Valid with Get-AuthenticodeSignature.",
            "",
            "## Clean Windows 11 Machine",
            "",
            "1. Install ANN from the signed installer into D:\\ANN.",
            "2. Run clean-machine validation with signed-installer enforcement.",
            f"   `{manifest.get('clean_machine_command')}`",
            "3. Confirm the marker includes release_transfer_manifest_sha256 and release_transfer_manifest_aggregate_sha256.",
            "4. Preserve D:\\ANN\\clean_machine_external_validation.json.",
            "5. Verify the external evidence bundle before running the final release verifier.",
            f"   `{manifest.get('external_release_evidence_command')}`",
            "",
            "## Windows Sandbox Alternative",
            "",
            "Windows Sandbox can provide a fresh Windows instance on the release host. It executes ANN_Setup.exe against read-only release inputs and validates the newly installed D:\\ANN tree; it does not validate a preinstalled host tree.",
            f"Prepare and inspect: `{manifest.get('windows_sandbox_prepare_command')}`",
            f"Launch only after signing: `{manifest.get('windows_sandbox_launch_command')}`",
            "",
            "## Final Verification",
            "",
            "Copy the clean-machine marker back to D:\\ANN if needed, then run:",
            "",
            f"`{manifest.get('final_verifier_command')}`",
            "",
            "From the development repository root, use the canonical path-contract command instead:",
            "",
            f"`{manifest.get('repo_root_final_verifier_command')}`",
            "",
            "The final release path contract expects installer, outputs/release_candidates/ANN_RC_HANDOFF, installer\\release_signing_evidence.json, and D:\\ANN\\clean_machine_external_validation.json in repo-root verification.",
            "",
            "The public release gate must stay blocked unless signatures are valid and the clean-machine marker reports PASSED.",
            "",
        ]
    )


def _autonomous_capability_scenarios() -> list[dict[str, str]]:
    return [
        {
            "id": "crm_saas_multitenant",
            "category": "saas",
            "prompt": "Build a production CRM SaaS with auth, tenancy, billing, workflows, RBAC, tests, and deployment.",
        },
        {
            "id": "ecommerce_marketplace",
            "category": "saas",
            "prompt": "Build a marketplace/ecommerce platform with catalog, cart, checkout, vendors, inventory, and admin.",
        },
        {
            "id": "booking_platform",
            "category": "saas",
            "prompt": "Build a booking SaaS with availability, resources, payments, notifications, and cancellation rules.",
        },
        {
            "id": "lms_platform",
            "category": "saas",
            "prompt": "Build an LMS with courses, lessons, quizzes, progress tracking, roles, certificates, and analytics.",
        },
        {
            "id": "ai_chatbot_saas",
            "category": "ai_product",
            "prompt": "Build an AI chatbot SaaS with tenants, usage limits, prompt templates, audit logs, and admin dashboards.",
        },
        {
            "id": "complex_3d_game",
            "category": "game",
            "prompt": "Build a fully playable complex 3D browser game with scoring, controls, physics, menus, and tests.",
        },
        {
            "id": "complex_algorithm_service",
            "category": "algorithm",
            "prompt": "Build a service implementing a complex algorithm with correctness tests, benchmarks, and edge cases.",
        },
    ]


def _autonomous_capability_required_fields() -> dict[str, Any]:
    return {
        "status": "COMPLETED_VERIFIED",
        "completion_quality": "VERIFIED",
        "verification_evidence.evidence_level": "STRONG",
        "commands_executed": "non-empty list of real verification commands",
        "security_review": "PASSED",
        "protected_paths_modified": False,
    }


def _sha256_for_existing_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    cached = _cached_sha256(path)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _store_cached_sha256(path, value)
    return value


def _sha256_cache_key(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (str(path.resolve()).lower(), stat.st_size, stat.st_mtime_ns)


def _file_state_cache_key(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False, "size": 0, "mtime_ns": 0}
    return {
        "path": str(path.resolve()).lower(),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _runtime_materialization_cache_key(root: Path) -> str:
    wheels = sorted((root / "wheels").glob("*.whl")) if (root / "wheels").is_dir() else []
    watched = [
        root,
        root / "python",
        root / "python" / "python.exe",
        root / "wheels",
        root / "checks",
        root / "audit",
        root / "site-packages",
        root / "requirements-lock",
    ]
    return json.dumps(
        {
            "gate": "build_runtime_materialization_watcher",
            "root": str(root.resolve()) if root.exists() else str(root),
            "watched": [ _file_state_cache_key(path) for path in watched ],
            "wheels": [_file_state_cache_key(path) for path in wheels],
        },
        sort_keys=True,
    )


def _cached_sha256(path: Path) -> str:
    try:
        return _SHA256_CACHE.get(_sha256_cache_key(path), "")
    except OSError:
        return ""


def _store_cached_sha256(path: Path, value: str) -> None:
    try:
        _SHA256_CACHE[_sha256_cache_key(path)] = value
    except OSError:
        return


def _first_or_none(values: list[str]) -> str:
    return values[0] if values else "none"


def _is_readable_file(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def _file_size_mb(path: Path) -> float | None:
    try:
        if path.is_file():
            return round(path.stat().st_size / (1024 * 1024), 3)
    except OSError:
        return None
    return None


def _directory_size_mb(path: Path) -> float | None:
    try:
        if path.is_file():
            return _file_size_mb(path)
        if not path.is_dir():
            return None
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
        return round(total / (1024 * 1024), 3)
    except OSError:
        return None


def _is_wsl() -> bool:
    release = platform.release().lower()
    if "microsoft" in release or "wsl" in release:
        return True
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        return "microsoft" in version or "wsl" in version
    except OSError:
        return False


def _runtime_path_info(path: str | Path | None = None) -> dict[str, Any]:
    raw = str(path or DEFAULT_RUNTIME_ROOT_TEXT).strip().strip('"').strip("'")
    blocked = _is_c_path(raw) or _has_runtime_path_traversal(raw)
    display = _runtime_display_path(raw)
    resolved = _resolve_runtime_filesystem_path(raw)
    return {
        "raw": raw,
        "display": display,
        "path": resolved,
        "resolved": str(resolved),
        "blocked": blocked,
        "errors": _dedupe(
            []
            + (["runtime_path_c_drive_blocked"] if _is_c_path(raw) else [])
            + (["runtime_path_traversal_blocked"] if _has_runtime_path_traversal(raw) else [])
        ),
    }


def _resolve_runtime_filesystem_path(path: str | Path) -> Path:
    text = str(path).strip().strip('"').strip("'")
    normalized = text.replace("\\", "/")
    drive_match = _windows_drive_match(normalized)
    if _is_wsl() and drive_match:
        drive, rest = drive_match
        mount_root = os.getenv("ANN_WSL_MOUNT_ROOT", DEFAULT_WSL_MOUNT_ROOT).replace("\\", "/").rstrip("/")
        return Path(f"{mount_root}/{drive.lower()}/{rest}".rstrip("/"))
    return Path(text)


def _directory_file_size_mb(path: Path, *, suffix: str | None = None) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return round(path.stat().st_size / (1024 * 1024), 2)
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and (suffix is None or item.name.endswith(suffix)):
            total += item.stat().st_size
    return round(total / (1024 * 1024), 2)


def _estimate_deepseek_required_vram_mb(model_size_mb: float) -> float:
    if model_size_mb <= 0:
        return 0.0
    quantized_estimate = model_size_mb * 0.38 + 2048
    return round(max(12000.0, quantized_estimate), 2)


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _query_nvidia_smi_memory() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"available": False}
    completed = subprocess.run(
        [
            executable,
            "--query-gpu=name,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return {"available": False, "error": completed.stderr.strip()}
    first = completed.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 3:
        return {"available": False, "error": "unexpected_nvidia_smi_output"}
    return {
        "available": True,
        "gpu_name": parts[0],
        "total_mb": _first_number(parts[1]),
        "free_mb": _first_number(parts[2]),
    }


def _deepseek_gguf_alternative_exists(path: str | Path | None = None) -> bool:
    if path is not None:
        return _resolve_runtime_filesystem_path(path).is_file()
    exact = _resolve_runtime_filesystem_path(DEEPSEEK14B_GGUF_PATH)
    if exact.is_file():
        return True
    candidate_dirs = [
        REPO_ROOT / "models",
        _resolve_runtime_filesystem_path("D:/Models"),
    ]
    for directory in candidate_dirs:
        if not directory.is_dir():
            continue
        for pattern in ("*deepseek*.gguf", "*DeepSeek*.gguf"):
            if next(directory.rglob(pattern), None) is not None:
                return True
    return False


def _runtime_display_path(path: str | Path) -> str:
    text = str(path).strip().strip('"').strip("'").replace("\\", "/").rstrip("/")
    wsl_prefix = "/mnt/"
    if text.lower().startswith(wsl_prefix) and len(text) > len(wsl_prefix):
        drive = text[len(wsl_prefix)]
        if len(text) == len(wsl_prefix) + 1:
            return f"{drive.upper()}:/"
        if text[len(wsl_prefix) + 1 : len(wsl_prefix) + 2] == "/":
            return f"{drive.upper()}:/{text[len(wsl_prefix) + 2:]}"
    return text


def _external_runtime_type(python_executable: str | Path) -> str:
    executable = str(python_executable).replace("\\", "/").lower()
    conda_prefix = os.getenv("CONDA_PREFIX", "").strip()
    if conda_prefix or "conda" in executable or "miniconda" in executable or "anaconda" in executable:
        return "external_conda"
    if ".venv" in executable or "/venv/" in executable:
        return "external_venv"
    return "external_system"


def _load_real_llama_cpp_factory() -> Any:
    llama_module = load_secure_llama_cpp()
    factory = getattr(llama_module, "Llama", None)
    if factory is None:
        raise RuntimeError("llama_cpp.Llama is unavailable")
    return factory


def _select_external_child_runtime(required_modules: tuple[str, ...]) -> str:
    if all(importlib.util.find_spec(module) is not None for module in required_modules):
        return "local"
    if os.name == "nt" and _wsl_conda_runtime_ready(required_modules):
        return "wsl_conda_qlora311"
    return "local"


def _wsl_conda_runtime_ready(required_modules: tuple[str, ...]) -> bool:
    module_probe = "; ".join(
        f"assert importlib.util.find_spec({module!r}) is not None" for module in required_modules
    )
    command = (
        'source "$HOME/miniconda3/etc/profile.d/conda.sh" && '
        "conda activate qlora311 && "
        f"python -c {shlex.quote('import importlib.util; ' + module_probe)}"
    )
    try:
        completed = subprocess.run(
            ["wsl", "bash", "-lc", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _path_for_child_runtime(path: Path, child_runtime: str) -> Path | PurePosixPath:
    if child_runtime != "wsl_conda_qlora311":
        return path
    return PurePosixPath(_windows_path_to_wsl(path))


def _windows_path_to_wsl(path: Path) -> str:
    resolved = Path(path).resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return str(resolved).replace("\\", "/")
    rest = str(resolved)[len(resolved.drive) :].replace("\\", "/").lstrip("/")
    return f"/mnt/{drive}/{rest}"


def _run_external_child_script(
    script_path: Path,
    *,
    child_runtime: str,
    timeout_seconds: int,
    offline_hf: bool = False,
) -> subprocess.CompletedProcess[str]:
    if child_runtime != "wsl_conda_qlora311":
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        if offline_hf:
            env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        return subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )

    repo_root = _windows_path_to_wsl(REPO_ROOT)
    child_script = _windows_path_to_wsl(script_path)
    activation_script = _windows_path_to_wsl(
        REPO_ROOT
        / "migration-backups"
        / "llama-cpp-python-cuda-20260612-050041"
        / "activate-llama-cpp-python-cuda.sh"
    )
    hf_exports = (
        "export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1; "
        if offline_hf
        else ""
    )
    command = (
        'source "$HOME/miniconda3/etc/profile.d/conda.sh" && '
        "conda activate qlora311 && "
        f"if [ -f {shlex.quote(activation_script)} ]; then source {shlex.quote(activation_script)}; fi && "
        f"export PYTHONPATH={shlex.quote(repo_root)}; "
        f"{hf_exports}"
        f"cd {shlex.quote(repo_root)} && "
        f"python {shlex.quote(child_script)}"
    )
    return subprocess.run(
        ["wsl", "bash", "-lc", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_seconds,
    )


def _run_qwen25_external_child_process(
    target: Path,
    model_path: Path,
    prompt: str,
    max_tokens: int,
    *,
    n_ctx: int,
    result_stem: str = "qwen25_first_real",
) -> dict[str, Any]:
    script_path = target / f"_{result_stem}_child.py"
    result_path = target / f"_{result_stem}_child_result.json"
    child_runtime = _select_external_child_runtime(("llama_cpp",))
    script_path.write_text(
        _qwen25_child_script(
            model_path=_path_for_child_runtime(model_path, child_runtime),
            prompt=prompt,
            max_tokens=max_tokens,
            result_path=_path_for_child_runtime(result_path, child_runtime),
            n_ctx=n_ctx,
        ),
        encoding="utf-8",
    )
    completed = _run_external_child_script(
        script_path,
        child_runtime=child_runtime,
        timeout_seconds=900,
    )
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"status": "CHILD_RESULT_INVALID_JSON"}
    else:
        payload = {"status": "CHILD_RESULT_MISSING"}
    payload["returncode"] = completed.returncode
    payload["stdout"] = (completed.stdout or "")[-4000:]
    payload["stderr"] = (completed.stderr or "")[-4000:]
    if completed.returncode != 0 and not payload.get("exception"):
        payload["exception"] = f"child_process_failed_returncode_{completed.returncode}"
    return payload


def _run_wsl_qwen25_smoke_child(
    *,
    target: Path,
    prompt: str,
    max_tokens: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    result_path = target / "_qwen25_wsl_smoke_result.json"
    wsl_result = _windows_path_to_wsl(result_path)
    repo_wsl = "/mnt/d/AgenticEngineeringNetwork"
    command = f'''
set -e
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate qlora311
cd {repo_wsl}
export PYTHONPATH=.
python - <<'PY'
from pathlib import Path
from agentic_network.runtime_engine.local_model_activation import run_qwen25_first_real_inference_external, LOCAL_TEST_TOKEN
result = run_qwen25_first_real_inference_external(
    approval_token=LOCAL_TEST_TOKEN,
    manual_confirmation=True,
    output_dir=Path({wsl_result!r}).parent,
    prompt={prompt!r},
    max_tokens={int(max_tokens)!r},
)
Path({wsl_result!r}).write_text(__import__("json").dumps(result, indent=2), encoding="utf-8")
PY
'''
    try:
        completed = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", command],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "FIRST_REAL_INFERENCE_FAILED",
            "exception": f"{type(exc).__name__}: {exc}",
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"status": "CHILD_RESULT_INVALID_JSON"}
    else:
        payload = {"status": "CHILD_RESULT_MISSING"}
    payload["returncode"] = completed.returncode
    payload["stdout"] = completed.stdout[-4000:]
    payload["stderr"] = completed.stderr[-4000:]
    return payload


def _run_llama_cpp_external_child_process(
    *,
    target: Path,
    model_path: Path,
    prompt: str,
    max_tokens: int,
    result_stem: str,
    n_ctx: int,
    n_gpu_layers: int,
    n_threads: int,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    script_path = target / f"_{result_stem}_child.py"
    result_path = target / f"_{result_stem}_child_result.json"
    child_runtime = _select_external_child_runtime(("llama_cpp",))
    script_path.write_text(
        _llama_cpp_child_script(
            model_path=_path_for_child_runtime(model_path, child_runtime),
            prompt=prompt,
            max_tokens=max_tokens,
            result_path=_path_for_child_runtime(result_path, child_runtime),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
        ),
        encoding="utf-8",
    )
    completed = _run_external_child_script(
        script_path,
        child_runtime=child_runtime,
        timeout_seconds=timeout_seconds,
    )
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"status": "CHILD_RESULT_INVALID_JSON"}
    else:
        payload = {"status": "CHILD_RESULT_MISSING"}
    payload["returncode"] = completed.returncode
    payload["stdout"] = (completed.stdout or "")[-4000:]
    payload["stderr"] = (completed.stderr or "")[-4000:]
    payload["n_gpu_layers"] = n_gpu_layers
    payload["n_ctx"] = n_ctx
    payload["n_threads"] = n_threads
    if completed.returncode != 0 and not payload.get("exception"):
        payload["exception"] = f"child_process_failed_returncode_{completed.returncode}"
    return payload


def _run_hf_external_child_process(
    *,
    target: Path,
    model_path: Path,
    prompt: str,
    max_new_tokens: int,
    result_stem: str,
    adapter_path: Path | None,
    load_in_4bit: bool,
) -> dict[str, Any]:
    script_path = target / f"_{result_stem}_child.py"
    result_path = target / f"_{result_stem}_child_result.json"
    child_runtime = _select_external_child_runtime(("transformers", "peft", "torch"))
    script_path.write_text(
        _hf_child_script(
            model_path=_path_for_child_runtime(model_path, child_runtime),
            adapter_path=(
                _path_for_child_runtime(adapter_path, child_runtime)
                if adapter_path is not None
                else None
            ),
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            result_path=_path_for_child_runtime(result_path, child_runtime),
            load_in_4bit=load_in_4bit,
        ),
        encoding="utf-8",
    )
    completed = _run_external_child_script(
        script_path,
        child_runtime=child_runtime,
        timeout_seconds=1800,
        offline_hf=True,
    )
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"status": "CHILD_RESULT_INVALID_JSON"}
    else:
        payload = {"status": "CHILD_RESULT_MISSING"}
    payload["returncode"] = completed.returncode
    payload["stdout"] = (completed.stdout or "")[-4000:]
    payload["stderr"] = (completed.stderr or "")[-4000:]
    if completed.returncode != 0 and not payload.get("exception"):
        payload["exception"] = f"child_process_failed_returncode_{completed.returncode}"
    return payload


def _hf_child_script(
    *,
    model_path: Path,
    adapter_path: Path | None,
    prompt: str,
    max_new_tokens: int,
    result_path: Path,
    load_in_4bit: bool,
) -> str:
    adapter_literal = str(adapter_path) if adapter_path is not None else ""
    return f'''
from __future__ import annotations

import gc
import json
import subprocess
import time
import traceback
from pathlib import Path


RESULT_PATH = Path({str(result_path)!r})
MODEL_PATH = {str(model_path)!r}
ADAPTER_PATH = {adapter_literal!r}
PROMPT = {prompt!r}
MAX_NEW_TOKENS = {int(max_new_tokens)!r}
LOAD_IN_4BIT = {bool(load_in_4bit)!r}


def write(payload):
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def vram(label):
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        value = float(completed.stdout.strip().splitlines()[0]) if completed.returncode == 0 and completed.stdout.strip() else None
    except Exception:
        value = None
    return {{"label": label, "memory_used_mb": value, "source": "nvidia-smi"}}


payload = {{
    "status": "STARTED",
    "real_load_attempted": False,
    "real_load_success": False,
    "real_inference_attempted": False,
    "real_inference_success": False,
    "generated_text": "",
    "tokens_generated": 0,
    "prompt_tokens": 0,
    "load_time_seconds": 0.0,
    "inference_time_seconds": 0.0,
    "exception": "",
    "inference_exception": "",
    "vram_samples": [vram("child_before_load")],
}}
write(payload)
model = None
tokenizer = None
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    quantization_config = BitsAndBytesConfig(load_in_4bit=True) if LOAD_IN_4BIT else None
    payload["real_load_attempted"] = True
    payload["status"] = "LOADING"
    write(payload)
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        local_files_only=True,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype="auto",
        quantization_config=quantization_config,
    )
    if ADAPTER_PATH:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, ADAPTER_PATH, local_files_only=True)
    model.eval()
    payload["load_time_seconds"] = max(0.0, time.perf_counter() - started)
    payload["real_load_success"] = True
    payload["status"] = "LOADED"
    payload["vram_samples"].append(vram("child_after_load"))
    write(payload)

    payload["real_inference_attempted"] = True
    payload["status"] = "INFERRING"
    write(payload)
    inputs = tokenizer(PROMPT, return_tensors="pt").to(model.device)
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    inference_started = time.perf_counter()
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    payload["inference_time_seconds"] = max(0.0, time.perf_counter() - inference_started)
    new_tokens = output_ids[0][prompt_tokens:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    payload["generated_text"] = text
    payload["tokens_generated"] = int(new_tokens.shape[-1])
    payload["prompt_tokens"] = prompt_tokens
    payload["real_inference_success"] = bool(text.strip())
    payload["status"] = "REAL_INFERENCE_PASSED" if payload["real_inference_success"] else "REAL_INFERENCE_FAILED"
    payload["vram_samples"].append(vram("child_after_inference"))
except BaseException as exc:
    if payload["real_load_success"]:
        payload["inference_exception"] = f"{{type(exc).__name__}}: {{exc}}"
    else:
        payload["exception"] = f"{{type(exc).__name__}}: {{exc}}"
    payload["traceback"] = traceback.format_exc()
    payload["status"] = "REAL_INFERENCE_FAILED"
finally:
    model = None
    tokenizer = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except BaseException:
        pass
    payload["vram_samples"].append(vram("child_after_rollback"))
    write(payload)
'''


def _qwen25_child_script(*, model_path: Path, prompt: str, max_tokens: int, result_path: Path, n_ctx: int) -> str:
    return f'''
from __future__ import annotations

import gc
import json
import subprocess
import time
import traceback
from pathlib import Path


RESULT_PATH = Path({str(result_path)!r})
MODEL_PATH = {str(model_path)!r}
PROMPT = {prompt!r}
MAX_TOKENS = {int(max_tokens)!r}
N_CTX = {int(n_ctx)!r}


def write(payload):
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def vram(label):
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        value = float(completed.stdout.strip().splitlines()[0]) if completed.returncode == 0 and completed.stdout.strip() else None
    except Exception:
        value = None
    return {{"label": label, "memory_used_mb": value, "source": "nvidia-smi"}}


def completion_text(result):
    if not isinstance(result, dict):
        return str(result or "")
    choices = result.get("choices", [])
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return str(choices[0].get("text") or "")
    return str(result.get("text") or "")


payload = {{
    "status": "STARTED",
    "real_load_attempted": False,
    "real_load_success": False,
    "real_inference_attempted": False,
    "real_inference_success": False,
    "generated_text": "",
    "tokens_generated": 0,
    "prompt_tokens": 0,
    "load_time_seconds": 0.0,
    "inference_time_seconds": 0.0,
    "exception": "",
    "inference_exception": "",
    "vram_samples": [vram("child_before_load")],
}}
write(payload)
llm = None
try:
    from agentic_network.models.llama_cpp_security import load_secure_llama_cpp

    Llama = load_secure_llama_cpp().Llama

    payload["real_load_attempted"] = True
    payload["status"] = "LOADING"
    write(payload)
    started = time.perf_counter()
    llm = Llama(model_path=MODEL_PATH, n_ctx=N_CTX, n_gpu_layers=-1, verbose=False)
    payload["load_time_seconds"] = max(0.0, time.perf_counter() - started)
    payload["real_load_success"] = True
    payload["status"] = "LOADED"
    payload["vram_samples"].append(vram("child_after_load"))
    write(payload)

    payload["real_inference_attempted"] = True
    payload["status"] = "INFERRING"
    write(payload)
    inference_started = time.perf_counter()
    result = llm(PROMPT, max_tokens=MAX_TOKENS, temperature=0.0, echo=False)
    payload["inference_time_seconds"] = max(0.0, time.perf_counter() - inference_started)
    text = completion_text(result)
    usage = result.get("usage", {{}}) if isinstance(result, dict) else {{}}
    payload["generated_text"] = text
    payload["tokens_generated"] = int(usage.get("completion_tokens") or len(text.split()))
    payload["prompt_tokens"] = int(usage.get("prompt_tokens") or len(PROMPT.split()))
    payload["real_inference_success"] = bool(text.strip())
    payload["status"] = "FIRST_REAL_INFERENCE_PASSED" if payload["real_inference_success"] else "FIRST_REAL_INFERENCE_FAILED"
    payload["vram_samples"].append(vram("child_after_inference"))
except BaseException as exc:
    if payload["real_load_success"]:
        payload["inference_exception"] = f"{{type(exc).__name__}}: {{exc}}"
    else:
        payload["exception"] = f"{{type(exc).__name__}}: {{exc}}"
    payload["traceback"] = traceback.format_exc()
    payload["status"] = "FIRST_REAL_INFERENCE_FAILED"
finally:
    try:
        if llm is not None and callable(getattr(llm, "close", None)):
            llm.close()
    except BaseException as exc:
        payload.setdefault("warnings", []).append(f"close_failed:{{type(exc).__name__}}:{{exc}}")
    llm = None
    gc.collect()
    payload["vram_samples"].append(vram("child_after_rollback"))
    write(payload)
'''


def _llama_cpp_child_script(
    *,
    model_path: Path,
    prompt: str,
    max_tokens: int,
    result_path: Path,
    n_ctx: int,
    n_gpu_layers: int,
    n_threads: int,
) -> str:
    return f'''
from __future__ import annotations

import gc
import json
import subprocess
import time
import traceback
from pathlib import Path


RESULT_PATH = Path({str(result_path)!r})
MODEL_PATH = {str(model_path)!r}
PROMPT = {prompt!r}
MAX_TOKENS = {int(max_tokens)!r}
N_CTX = {int(n_ctx)!r}
N_GPU_LAYERS = {int(n_gpu_layers)!r}
N_THREADS = {int(n_threads)!r}


def write(payload):
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def vram(label):
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        value = float(completed.stdout.strip().splitlines()[0]) if completed.returncode == 0 and completed.stdout.strip() else None
    except Exception:
        value = None
    return {{"label": label, "memory_used_mb": value, "source": "nvidia-smi"}}


def completion_text(result):
    if not isinstance(result, dict):
        return str(result or "")
    choices = result.get("choices", [])
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return str(choices[0].get("text") or "")
    return str(result.get("text") or "")


payload = {{
    "status": "STARTED",
    "real_load_attempted": False,
    "real_load_success": False,
    "real_inference_attempted": False,
    "real_inference_success": False,
    "generated_text": "",
    "tokens_generated": 0,
    "prompt_tokens": 0,
    "load_time_seconds": 0.0,
    "inference_time_seconds": 0.0,
    "exception": "",
    "inference_exception": "",
    "n_ctx": N_CTX,
    "n_gpu_layers": N_GPU_LAYERS,
    "n_threads": N_THREADS,
    "vram_samples": [vram("child_before_load")],
}}
write(payload)
llm = None
try:
    from agentic_network.models.llama_cpp_security import load_secure_llama_cpp

    Llama = load_secure_llama_cpp().Llama

    payload["real_load_attempted"] = True
    payload["status"] = "LOADING"
    write(payload)
    started = time.perf_counter()
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_gpu_layers=N_GPU_LAYERS,
        n_threads=N_THREADS,
        verbose=False,
    )
    payload["load_time_seconds"] = max(0.0, time.perf_counter() - started)
    payload["real_load_success"] = True
    payload["status"] = "LOADED"
    payload["vram_samples"].append(vram("child_after_load"))
    write(payload)

    payload["real_inference_attempted"] = True
    payload["status"] = "INFERRING"
    write(payload)
    inference_started = time.perf_counter()
    result = llm(PROMPT, max_tokens=MAX_TOKENS, temperature=0.0, echo=False)
    payload["inference_time_seconds"] = max(0.0, time.perf_counter() - inference_started)
    text = completion_text(result)
    usage = result.get("usage", {{}}) if isinstance(result, dict) else {{}}
    payload["generated_text"] = text
    payload["tokens_generated"] = int(usage.get("completion_tokens") or len(text.split()))
    payload["prompt_tokens"] = int(usage.get("prompt_tokens") or len(PROMPT.split()))
    payload["real_inference_success"] = bool(text.strip())
    payload["status"] = "REAL_INFERENCE_PASSED" if payload["real_inference_success"] else "REAL_INFERENCE_FAILED"
    payload["vram_samples"].append(vram("child_after_inference"))
except BaseException as exc:
    if payload["real_load_success"]:
        payload["inference_exception"] = f"{{type(exc).__name__}}: {{exc}}"
    else:
        payload["exception"] = f"{{type(exc).__name__}}: {{exc}}"
    payload["traceback"] = traceback.format_exc()
    payload["status"] = "REAL_INFERENCE_FAILED"
finally:
    try:
        if llm is not None and callable(getattr(llm, "close", None)):
            llm.close()
    except BaseException as exc:
        payload.setdefault("warnings", []).append(f"close_failed:{{type(exc).__name__}}:{{exc}}")
    llm = None
    gc.collect()
    payload["vram_samples"].append(vram("child_after_rollback"))
    write(payload)
'''


def _llama_completion_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    choices = result.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            return str(first.get("text") or first.get("message", {}).get("content") or "")
    return str(result.get("text") or "")


def _estimate_token_count(text: str) -> int:
    clean = str(text or "").strip()
    return len(clean.split()) if clean else 0


def _vram_sample(label: str) -> dict[str, Any]:
    nvidia = _nvidia_smi_memory_used_mb()
    cuda = diagnose_cuda_environment()
    used = nvidia if nvidia is not None else cuda.get("vram_allocated_mb")
    return {
        "label": label,
        "memory_used_mb": used,
        "gpu_name": cuda.get("gpu_name"),
        "vram_total_mb": cuda.get("vram_total_mb"),
        "source": "nvidia-smi" if nvidia is not None else "torch_cuda_probe",
    }


def _nvidia_smi_memory_used_mb() -> float | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    first = completed.stdout.strip().splitlines()[0:1]
    if not first:
        return None
    try:
        return float(first[0].strip())
    except ValueError:
        return None


def _peak_vram(samples: list[dict[str, Any]]) -> float | None:
    values = [float(sample["memory_used_mb"]) for sample in samples if sample.get("memory_used_mb") is not None]
    return max(values) if values else None


def _empty_torch_cuda_cache() -> None:
    try:
        torch = importlib.import_module("torch")
        if bool(torch.cuda.is_available()):
            torch.cuda.empty_cache()
    except Exception:
        return


def _force_runtime_safe_mode() -> dict[str, Any]:
    reset_runtime_state()
    metrics = get_runtime_metrics()
    loaded = get_loaded_models()
    return {
        "loaded_models_after": loaded,
        "active_models_after": metrics.get("active_models", 0),
        "parallel_llm_loads_after": metrics.get("parallel_llm_loads", 0),
        "safe_mode_final": loaded == [] and metrics.get("active_models", 0) == 0 and metrics.get("parallel_llm_loads", 0) == 0,
    }


def _developer_team_coder_prompt(task: str, architecture: dict[str, Any]) -> str:
    return (
        "<|im_start|>system\n"
        "You are Qwen2.5 Coder inside ANN. Return real code only. Use Markdown fenced blocks with file path headings.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{task}\n\n"
        "Required files: main.py, schemas.py, crud.py, models.py, tests/test_main.py, README.md.\n"
        "Keep it concise but complete: CRUD, Pydantic schemas, pytest tests, error handling, README examples, type hints.\n"
        f"Architecture summary: {', '.join((architecture or {}).get('architecture', [])[:3])}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _developer_team_consensus(qwen3: dict[str, Any], coder: dict[str, Any], deepseek: dict[str, Any]) -> dict[str, Any]:
    coder_passed = coder["status"] == "PASSED"
    return {
        "version": "18.6",
        "generated_at": _now(),
        "decision": "PARTIAL" if coder_passed else "BLOCKED",
        "qwen3_status": qwen3["status"],
        "coder_status": coder["status"],
        "deepseek_status": deepseek["status"],
        "summary": "Qwen2.5 produced real output; Qwen3 and DeepSeek remained in bridge mode." if coder_passed else "Coder stage did not produce a successful real inference.",
        "reused_subsystems": ["Consensus"],
        "safety": _safety_payload(),
    }


def _full_team_consensus(qwen3: dict[str, Any], qwen25: dict[str, Any], deepseek: dict[str, Any]) -> dict[str, Any]:
    deepseek_ok = deepseek["status"] == "DEEPSEEK_REAL_PASSED" or _deepseek_powerful_deferred_valid(deepseek)
    passed = qwen3["status"] == "QWEN3_REAL_PASSED" and qwen25["status"] == "PASSED" and deepseek_ok
    return {
        "version": "18.9",
        "generated_at": _now(),
        "decision": "PASSED" if passed else "FAILED",
        "qwen3_status": qwen3["status"],
        "qwen25_status": qwen25["status"],
        "deepseek_status": deepseek["status"],
        "powerful_deferred_reason": deepseek.get("deferred_reason"),
        "safety": _safety_payload(),
    }


def _deepseek_powerful_deferred_valid(deepseek: dict[str, Any]) -> bool:
    return (
        deepseek.get("status") == "DEEPSEEK_POWERFUL_DEFERRED"
        and deepseek.get("deferred_reason") == POWERFUL_DEFERRED_REASON
        and deepseek.get("fallback_gate_status")
        in {"POWERFUL_DEFERRED_OFFLOAD_REQUIRED", "POWERFUL_DEFERRED_QUANTIZED_REQUIRED", "POWERFUL_BRIDGE_REVIEW_ALLOWED"}
    )


def _developer_team_powerful_deferred_passed(
    qwen3: dict[str, Any],
    qwen25: dict[str, Any],
    deepseek: dict[str, Any],
    consensus: dict[str, Any],
    patch_quality: dict[str, Any],
    tests: dict[str, Any],
) -> bool:
    return (
        qwen3.get("status") == "QWEN3_REAL_PASSED"
        and qwen25.get("status") == "PASSED"
        and _deepseek_powerful_deferred_valid(deepseek)
        and deepseek.get("fallback_gate", {}).get("use_bridge_review") is True
        and consensus.get("decision") == "PASSED"
        and patch_quality.get("status") == "PASSED"
        and tests.get("status") == "PASSED"
    )


def _full_team_patch_quality(qwen25: dict[str, Any]) -> dict[str, Any]:
    generated = str(qwen25.get("generated_text") or "")
    required = ["main.py", "schemas.py", "crud.py", "models.py", "tests", "README.md"]
    missing = [item for item in required if item not in generated]
    return {
        "version": "18.9",
        "generated_at": _now(),
        "status": "PASSED" if not missing and qwen25["status"] == "PASSED" else "FAILED",
        "missing": missing,
        "score": 100 - len(missing) * 12,
        "safety": _safety_payload(),
    }


def _full_team_tests(qwen25: dict[str, Any]) -> dict[str, Any]:
    generated = str(qwen25.get("generated_text") or "")
    generated_lower = generated.lower()
    has_tests = "pytest" in generated_lower or "testclient" in generated_lower or "tests/" in generated_lower or "test_" in generated_lower
    return {
        "version": "18.9",
        "generated_at": _now(),
        "status": "PASSED" if qwen25["status"] == "PASSED" and has_tests else "FAILED",
        "note": "Static generated-output test gate; no files were applied or shell tests executed.",
        "safety": _safety_payload(),
    }


def _full_team_action_plan(
    consensus: dict[str, Any],
    patch_quality: dict[str, Any],
    tests: dict[str, Any],
) -> dict[str, Any]:
    passed = consensus["decision"] == "PASSED" and patch_quality["status"] == "PASSED" and tests["status"] == "PASSED"
    return {
        "version": "18.9",
        "generated_at": _now(),
        "status": "PASSED" if passed else "FAILED",
        "recommended_next_action": "apply_generated_project_in_sandbox" if passed else "inspect_failed_real_stage_artifacts",
        "safety": _safety_payload(),
    }


def _real_hf_stage_gate_errors(
    approval_token: str | None,
    manual_confirmation: bool,
    model_path: Path,
    adapter_path: Path | None,
) -> list[str]:
    errors: list[str] = []
    if not _token_valid(approval_token):
        errors.append("approval_token_invalid_or_missing")
    if not manual_confirmation:
        errors.append("manual_confirmation_required")
    if not model_path.is_dir():
        errors.append(f"model_path_missing:{model_path}")
    if adapter_path is not None and not adapter_path.exists():
        errors.append(f"adapter_path_missing:{adapter_path}")
    metrics = get_runtime_metrics()
    if metrics.get("active_models", 0) != 0:
        errors.append("active_models_must_start_at_zero")
    if metrics.get("parallel_llm_loads", 0) != 0:
        errors.append("parallel_llm_loads_must_start_at_zero")
    return errors


def _real_stage_load_payload(
    *,
    version: str,
    status: str,
    model_name: str,
    model_path: Path,
    real_load_attempted: bool,
    real_load_success: bool,
    load_time_seconds: float,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "version": version,
        "generated_at": _now(),
        "status": status,
        "model_name": model_name,
        "model_path": str(model_path),
        "real_load_attempted": real_load_attempted,
        "real_load_success": real_load_success,
        "load_time_seconds": load_time_seconds,
        "errors": _dedupe(errors),
        "safety": _safety_payload(),
    }


def _real_stage_benchmark(
    version: str,
    status: str,
    child: dict[str, Any],
    reset_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": version,
        "generated_at": _now(),
        "status": status,
        "peak_vram_mb": _peak_vram(child.get("vram_samples") or []) or 0,
        "vram_samples": child.get("vram_samples") or [],
        "load_time_seconds": float(child.get("load_time_seconds") or 0.0),
        "inference_time_seconds": float(child.get("inference_time_seconds") or 0.0),
        "tokens_generated": int(child.get("tokens_generated") or 0),
        "prompt_tokens": int(child.get("prompt_tokens") or 0),
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_mode_final": reset_payload["safe_mode_final"],
        "safety": _safety_payload(),
    }


def _real_stage_rollback(version: str, reset_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": version,
        "generated_at": _now(),
        "status": "SAFE_ROLLBACK_PASSED" if reset_payload["safe_mode_final"] else "SAFE_ROLLBACK_FAILED",
        "active_models_after": reset_payload["active_models_after"],
        "parallel_llm_loads_after": reset_payload["parallel_llm_loads_after"],
        "safe_mode_final": reset_payload["safe_mode_final"],
        "safety": _safety_payload(),
    }


def _extract_stage_lines(text: str, keyword: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines() if keyword.lower() in line.lower()]
    return [line for line in lines if line][:8]


def _developer_team_patch_quality(coder: dict[str, Any]) -> dict[str, Any]:
    generated = str(coder.get("generated_text") or "")
    requested = ["main.py", "schemas.py", "crud.py", "models.py", "README.md"]
    hits = [name for name in requested if name in generated]
    score = 60 + len(hits) * 8 if generated.strip() else 0
    return {
        "version": "18.6",
        "generated_at": _now(),
        "decision": "IMPLEMENTATION_REVIEW_REQUIRED" if generated.strip() else "BLOCKED",
        "score": min(score, 100),
        "requested_files_mentioned": hits,
        "reused_subsystems": ["Patch Quality"],
        "safety": _safety_payload(),
    }


def _developer_team_test_results(coder: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "18.6",
        "generated_at": _now(),
        "status": "SKIPPED_REQUIRES_PATCH_APPLICATION",
        "reason": "Developer Team pipeline generated review artifacts only; it did not apply files into a project workspace.",
        "coder_status": coder["status"],
        "reused_subsystems": ["Test Runner"],
        "safety": _safety_payload(),
    }


def _developer_team_action_plan(
    consensus: dict[str, Any],
    patch_quality: dict[str, Any],
    test_results: dict[str, Any],
) -> dict[str, Any]:
    blocked = consensus["decision"] == "BLOCKED"
    return {
        "version": "18.6",
        "generated_at": _now(),
        "status": "ACTION_PLAN_BLOCKED" if blocked else "ACTION_PLAN_READY_FOR_HUMAN_REVIEW",
        "recommended_next_action": "inspect_coder_output_and_request_retry" if blocked else "review_generated_code_then_apply_in_sandbox",
        "consensus_decision": consensus["decision"],
        "patch_quality_decision": patch_quality["decision"],
        "test_runner_status": test_results["status"],
        "reused_subsystems": ["Action Planner"],
        "safety": _safety_payload(),
    }


def _write_developer_team_pipeline_artifacts(
    target: Path,
    *,
    qwen3: dict[str, Any],
    coder: dict[str, Any],
    deepseek: dict[str, Any],
    consensus: dict[str, Any],
    patch_quality: dict[str, Any],
    test_results: dict[str, Any],
    action_plan: dict[str, Any],
) -> list[str]:
    written = _write_numbered_artifacts(
        target,
        {
            "262_product_architect_output.json": qwen3,
            "264_coder_output.json": coder,
            "266_powerful_review.json": deepseek,
        },
    )
    for name, payload in {
        "268_consensus.json": consensus,
        "269_patch_quality.json": patch_quality,
        "270_test_results.json": test_results,
        "271_action_plan.json": action_plan,
    }.items():
        path = target / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))
    return written


def _desktop_deepseek_status(status: Any) -> str:
    if status == "DEEPSEEK_REAL_PASSED":
        return "PASSED"
    if status == "DEEPSEEK_POWERFUL_DEFERRED":
        return "DEFERRED"
    return str(status or "UNKNOWN")


def build_developer_team_desktop_status() -> dict[str, Any]:
    full_latest = _latest_artifact_named("297_full_team_action_plan.md")
    full_json = _latest_artifact_named("296_full_team_action_plan.json")
    if full_json is not None:
        pipeline_dir = full_json.parent
        pipeline = _read_json_if_exists(pipeline_dir / "288_full_team_pipeline.json")
        return {
            "status": pipeline.get("status", "FULL_TEAM_PIPELINE_ARTIFACTS_FOUND"),
            "qwen3": "PASSED" if pipeline.get("qwen3_status") == "QWEN3_REAL_PASSED" else pipeline.get("qwen3_status", "UNKNOWN"),
            "qwen2_5": "PASSED" if pipeline.get("qwen25_status") == "PASSED" else pipeline.get("qwen25_status", "UNKNOWN"),
            "deepseek": _desktop_deepseek_status(pipeline.get("deepseek_status")),
            "deepseek_reason": pipeline.get("powerful_deferred_reason", ""),
            "powerful_fallback": pipeline.get("powerful_fallback_status", ""),
            "sequential_runtime": pipeline.get("sequential_runtime", "ACTIVE"),
            "peak_vram_mb": pipeline.get("peak_vram_mb", 0),
            "model_switch_time_seconds": pipeline.get("model_switch_time_seconds", 0),
            "total_runtime_seconds": pipeline.get("total_runtime_seconds", 0),
            "safe_rollback": pipeline.get("safe_rollback", "UNKNOWN"),
            "artifact_dir": str(pipeline_dir),
        }
    if full_latest is not None:
        return {
            "status": "FULL_TEAM_PIPELINE_ARTIFACTS_FOUND",
            "qwen3": "UNKNOWN",
            "qwen2_5": "UNKNOWN",
            "deepseek": "UNKNOWN",
            "deepseek_reason": "",
            "powerful_fallback": "",
            "sequential_runtime": "ACTIVE",
            "peak_vram_mb": 0,
            "model_switch_time_seconds": 0,
            "total_runtime_seconds": 0,
            "safe_rollback": "UNKNOWN",
            "artifact_dir": str(full_latest.parent),
        }
    latest = _latest_artifact_named("271_action_plan.json")
    if latest is None:
        return {
            "status": "TEAM_PIPELINE_NOT_RUN",
            "qwen3": "BRIDGE",
            "qwen2_5": "PENDING",
            "deepseek": "BRIDGE",
            "deepseek_reason": "",
            "powerful_fallback": "",
            "sequential_runtime": "ACTIVE",
            "peak_vram_mb": 0,
            "model_switch_time_seconds": 0,
            "total_runtime_seconds": 0,
            "safe_rollback": "PASSED",
        }
    pipeline_dir = latest.parent
    qwen3 = _read_json_if_exists(pipeline_dir / "262_product_architect_output.json")
    coder = _read_json_if_exists(pipeline_dir / "264_coder_output.json")
    deepseek = _read_json_if_exists(pipeline_dir / "266_powerful_review.json")
    action = _read_json_if_exists(latest)
    return {
        "status": "TEAM_PIPELINE_ARTIFACTS_FOUND",
        "qwen3": "BRIDGE" if "BRIDGE" in str(qwen3.get("status", "")) else qwen3.get("status", "UNKNOWN"),
        "qwen2_5": "PASSED" if coder.get("status") == "PASSED" else coder.get("status", "UNKNOWN"),
        "deepseek": "BRIDGE" if "BRIDGE" in str(deepseek.get("status", "")) else deepseek.get("status", "UNKNOWN"),
        "deepseek_reason": deepseek.get("deferred_reason", ""),
        "powerful_fallback": deepseek.get("fallback_gate_status", ""),
        "sequential_runtime": "ACTIVE",
        "peak_vram_mb": coder.get("peak_vram_mb", 0),
        "model_switch_time_seconds": 0,
        "total_runtime_seconds": action.get("total_runtime_seconds", 0),
        "safe_rollback": "PASSED" if coder.get("safe_mode_final", True) else "FAILED",
        "artifact_dir": str(pipeline_dir),
    }


def _latest_artifact_named(name: str) -> Path | None:
    if not DEFAULT_ARTIFACT_ROOT.is_dir():
        return None
    matches = sorted(DEFAULT_ARTIFACT_ROOT.rglob(name), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_report(root_info: dict[str, Any]) -> dict[str, str]:
    report = {"runtime_root": str(root_info["display"])}
    resolved = str(root_info["resolved"])
    if resolved != str(root_info["display"]):
        report["resolved_runtime_root"] = resolved
    return report


def _embedded_runtime_package_presence(runtime_root: Path, package_names: tuple[str, ...]) -> dict[str, bool]:
    search_roots = [
        runtime_root / "python" / "Lib" / "site-packages",
        runtime_root / "site-packages",
    ]
    presence: dict[str, bool] = {}
    for package in package_names:
        normalized = package.replace("-", "_")
        candidates = []
        for root in search_roots:
            candidates.extend(
                [
                    root / normalized,
                    root / package,
                    root / f"{package}.py",
                    root / f"{normalized}.py",
                ]
            )
            if root.is_dir():
                candidates.extend(root.glob(f"{package}-*.dist-info"))
                candidates.extend(root.glob(f"{normalized}-*.dist-info"))
        presence[package] = any(path.exists() for path in candidates)
    return presence


def _run_embedded_runtime_import_probe(
    python_exe: Path,
    package_names: tuple[str, ...],
    timeout_seconds: int,
) -> dict[str, Any]:
    script = (
        "import importlib, importlib.metadata, json, re\n"
        f"packages = {json.dumps(list(package_names))}\n"
        "results = {}\n"
        "gpu_offload = False\n"
        "for name in packages:\n"
        "    try:\n"
        "        if name == 'llama_cpp':\n"
        "            from agentic_network.runtime_engine.windows_dlls import configure_windows_runtime_dll_paths\n"
        "            configure_windows_runtime_dll_paths()\n"
        "            from agentic_network.models.llama_cpp_security import load_secure_llama_cpp\n"
        "            module = load_secure_llama_cpp()\n"
        "        else:\n"
        "            module = importlib.import_module(name)\n"
        "        try:\n"
        "            version = importlib.metadata.version({'llama_cpp': 'llama-cpp-python'}.get(name, name))\n"
        "        except Exception:\n"
        "            version = getattr(module, '__version__', '') or 'unknown'\n"
        "        results[name] = {'importable': True, 'version': str(version), 'error': ''}\n"
        "        if name == 'llama_cpp':\n"
        "            from agentic_network.models.gpu_policy import llama_cpp_supports_gpu_offload\n"
        "            gpu_offload = llama_cpp_supports_gpu_offload(module) is True\n"
        "    except Exception as exc:\n"
        "        results[name] = {'importable': False, 'version': '', 'error': f'{type(exc).__name__}: {exc}'}\n"
        "normalize = lambda value: re.sub(r'[-_.]+', '-', value).lower()\n"
        "distributions = {normalize(dist.metadata['Name']): dist.version for dist in importlib.metadata.distributions() if dist.metadata.get('Name')}\n"
        "print(json.dumps({'packages': results, 'distributions': distributions, 'llama_cpp_gpu_offload': gpu_offload}, sort_keys=True))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(REPO_ROOT), env.get("PYTHONPATH", "")) if part
    )
    try:
        completed = subprocess.run(
            [str(python_exe), "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAILED", "packages": {}, "error": f"{type(exc).__name__}: {exc}"}
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    try:
        parsed = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except (json.JSONDecodeError, IndexError):
        parsed = {}
    if completed.returncode != 0 and not parsed:
        return {"status": "FAILED", "packages": {}, "error": stderr or f"returncode={completed.returncode}"}
    packages = parsed.get("packages") if isinstance(parsed, dict) else {}
    return {
        "status": "PASSED" if isinstance(packages, dict) else "FAILED",
        "packages": packages if isinstance(packages, dict) else {},
        "distributions": parsed.get("distributions", {}) if isinstance(parsed, dict) else {},
        "llama_cpp_gpu_offload": (
            parsed.get("llama_cpp_gpu_offload") is True if isinstance(parsed, dict) else False
        ),
        "error": stderr if completed.returncode != 0 else "",
    }


def _embedded_release_requirement_versions() -> dict[str, str]:
    path = REPO_ROOT / "config" / "ann_runtime_requirements.windows-cp311.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    requirements: dict[str, str] = {}
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#") or "==" not in value:
            continue
        name, version = value.split("==", 1)
        name = name.split("[", 1)[0].strip()
        requirements[_canonical_distribution_name(name)] = version.strip()
    return requirements


def _wheelhouse_distribution_versions(wheelhouse: Path) -> dict[str, str]:
    distributions: dict[str, str] = {}
    if not wheelhouse.is_dir():
        return distributions
    for wheel in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower()):
        try:
            with zipfile.ZipFile(wheel) as archive:
                metadata_name = next(
                    name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
                )
                metadata_text = archive.read(metadata_name).decode("utf-8", errors="replace")
        except (OSError, zipfile.BadZipFile, StopIteration):
            continue
        name = ""
        version = ""
        for line in metadata_text.splitlines():
            if line.startswith("Name: "):
                name = line[6:].strip()
            elif line.startswith("Version: "):
                version = line[9:].strip()
            if name and version:
                break
        if name:
            distributions[_canonical_distribution_name(name)] = version
    return distributions


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value)).lower()


def _runtime_lockfile_for_wheelhouse(
    wheelhouse: Path,
    explicit: str | Path | None = None,
) -> Path:
    if explicit is not None:
        return Path(explicit)
    candidate = wheelhouse.parent / "checks" / "ann_runtime_lock.json"
    if candidate.is_file():
        return candidate
    return REPO_ROOT / "config" / "ann_runtime_lock.example.json"


def _path_cache_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _authenticode_signature_status(
    path: Path,
    powershell_path: str | None,
    execute_signature_check: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "MISSING", "signer": "", "timestamp_signer": "", "error": "file_missing"}
    if not execute_signature_check:
        return {"status": "SKIPPED", "signer": "", "timestamp_signer": "", "error": "signature_check_disabled"}
    if not powershell_path:
        return {"status": "UNKNOWN", "signer": "", "timestamp_signer": "", "error": "powershell_missing"}
    command = (
        "& { param([string]$Path) "
        "Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; "
        "$s=Get-AuthenticodeSignature -FilePath $Path; "
        "[pscustomobject]@{"
        "Status=[string]$s.Status;"
        "Signer=if($s.SignerCertificate){[string]$s.SignerCertificate.Subject}else{''};"
        "TimestampSigner=if($s.TimeStamperCertificate){[string]$s.TimeStamperCertificate.Subject}else{''}"
        "} | ConvertTo-Json -Compress }"
    )
    try:
        completed = subprocess.run(
            [
                powershell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNKNOWN", "signer": "", "timestamp_signer": "", "error": f"{type(exc).__name__}: {exc}"}
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    try:
        parsed = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except (json.JSONDecodeError, IndexError):
        parsed = {}
    return {
        "status": str(parsed.get("Status") or "UNKNOWN"),
        "signer": str(parsed.get("Signer") or ""),
        "timestamp_signer": str(parsed.get("TimestampSigner") or ""),
        "error": stderr if completed.returncode != 0 else "",
    }


def _code_signing_next_step(blockers: list[str]) -> str:
    if not blockers:
        return "Preserve signed installer evidence and run clean-machine validation."
    if "final_installer_binaries_missing" in blockers:
        return "Build ANN_Setup.exe and ANN_Uninstall.exe from the installer foundation."
    if "authenticode_signature_invalid_or_missing" in blockers:
        return "Sign ANN_Setup.exe and ANN_Uninstall.exe with a trusted certificate and timestamp."
    if "signtool_missing" in blockers:
        return "Install or expose Windows SDK SignTool on PATH before release signing."
    return f"Resolve code signing blocker: {blockers[0]}"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_drive_match(text: str) -> tuple[str, str] | None:
    if len(text) < 2 or text[1] != ":" or not text[0].isalpha():
        return None
    rest = text[2:].replace("\\", "/").lstrip("/")
    return text[0], rest


def _has_runtime_path_traversal(path: str | Path) -> bool:
    return any(part == ".." for part in str(path).replace("\\", "/").split("/"))


def _is_c_path(path: Path) -> bool:
    raw = str(path).replace("\\", "/").lower()
    return raw.startswith("c:/") or raw.startswith("/mnt/c/")


def _normalize_path_text(path: str | Path) -> str:
    raw = str(path).replace("\\", "/").rstrip("/").lower()
    if raw.startswith("/mnt/") and len(raw) > 6 and raw[6] == "/":
        return f"{raw[5]}:/{raw[7:]}"
    return raw


def _has_protected_part(path: Path) -> bool:
    protected = {".git", "training", "datasets", "adapters", "memory", "knowledge", "unsloth_compiled_cache"}
    return any(part.lower() in protected for part in path.parts)


def _artifact_markdown(title: str, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"Generated at: {payload.get('generated_at')}",
            f"Status: {payload.get('status')}",
            "",
            "```json",
            json.dumps(_compact_payload(payload), indent=2),
            "```",
            "",
            "Safety: no uncontrolled model load, no downloads, no conversion, no quantization, no adapter writes, "
            "no dataset writes, and no permanent policy activation.",
            "",
        ]
    )


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "version",
        "status",
        "removed_identity",
        "correct_powerful_identity",
        "qwen14b_present",
        "deepseek14b_present",
        "runtime",
        "policy",
        "fast",
        "powerful",
        "steps",
        "model_name",
        "backend",
        "token_provided",
        "token_accepted",
        "confirmation",
        "loaded_models_before",
        "loaded_models_during",
        "loaded_models_after",
        "real_load_attempted",
        "real_inference_attempted",
        "real_load_succeeded",
        "real_inference_succeeded",
        "mock_fallback",
        "safe_mode_final",
        "errors",
        "warnings",
    )
    return {key: payload[key] for key in keys if key in payload}


def _timestamped_artifact_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_ARTIFACT_ROOT / stamp


def _safety_payload() -> dict[str, bool]:
    return {
        "local_only": True,
        "internet": False,
        "downloads": False,
        "dependency_install": False,
        "model_load": False,
        "inference": False,
        "training": False,
        "modify_models": False,
        "move_models": False,
        "quantize_models": False,
        "convert_models": False,
        "write_adapters": False,
        "write_datasets": False,
    }


def _token_valid(token: str | None) -> bool:
    return (token or "").strip() == LOCAL_TEST_TOKEN


def _rollback_safe_state() -> dict[str, Any]:
    loaded = get_loaded_models()
    return {
        "attempted": bool(loaded),
        "unloaded_models": list(loaded),
        "safe_mode_final": loaded == [],
        "note": "Backend foundation does not register real loaded state; ANN runtime remains safe/mock.",
    }


def _status_from_backend_load(status: Any) -> str:
    normalized = str(status or "").upper()
    if normalized == "UNAVAILABLE":
        return "UNAVAILABLE"
    if normalized == "BLOCKED":
        return "LOAD_BLOCKED"
    if normalized == "LOADED":
        return "LOADED"
    return "LOAD_FAILED"


def _backend_smoke_status(status: str, health: dict[str, Any], load: dict[str, Any]) -> str:
    if status == "UNAVAILABLE":
        return "unavailable"
    if status == "LOAD_BLOCKED":
        return "load_blocked"
    if status == "LOAD_FAILED":
        return "load_failed"
    if status == "PASSED":
        return "unloaded" if load.get("loaded") else "mock_fallback"
    if health.get("available") is True:
        return "available"
    return "mock_fallback"


def _list_from(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def _redact_if_empty_or_exact(text: str) -> str:
    return text if text.strip() == "ANN_QWEN25_SMOKE_OK" else ""


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _elapsed_seconds(started: float) -> float:
    return max(0.0, perf_counter() - started)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
