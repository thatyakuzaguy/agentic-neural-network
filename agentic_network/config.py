"""Configuration for the local multi-agent pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

SUPPORTED_MODEL_BACKENDS = frozenset(
    {"deepseek", "deepseek_unsloth", "qwen_v5", "qwen3", "mock"}
)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _model_backend(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in SUPPORTED_MODEL_BACKENDS:
        raise ValueError(f"Unsupported model backend for {env_name}: {value}")
    return value


def _architect_mode(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Architect Agent mode for {env_name}: {value}")
    return value


def _security_mode(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Security Agent mode for {env_name}: {value}")
    return value


def _reviewer_mode(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Reviewer Agent mode for {env_name}: {value}")
    return value


def _fixer_mode(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Fixer Agent mode for {env_name}: {value}")
    return value


def _final_reviewer_mode(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Final Reviewer Agent mode for {env_name}: {value}")
    return value


def _stage_isolation(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip().lower()
    if value not in {"subprocess", "inprocess"}:
        raise ValueError(f"Unsupported stage isolation for {env_name}: {value}")
    return value


def _gpu_layers(env_name: str, default: str, *, require_gpu: bool) -> int:
    value = int(os.getenv(env_name, default))
    if require_gpu and value == 0:
        raise ValueError(
            f"{env_name}=0 forces CPU inference. ANN_REQUIRE_GPU_FOR_LLM is enabled; "
            "use -1 for full GPU offload or a positive layer count."
        )
    return value


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime configuration read from environment variables."""

    deepseek_gguf_path: Path | None
    qwen_base_model: str
    qwen_adapter_path: Path
    output_dir: Path
    max_new_tokens: int
    temperature: float
    top_p: float
    context_length: int
    use_4bit: bool
    project_root: Path = Path("/mnt/d/AgenticEngineeringNetwork")
    product_max_new_tokens: int = 512
    product_temperature: float = 0.1
    product_top_p: float = 0.7
    product_agent_config_path: Path = Path(
        "/mnt/d/AgenticEngineeringNetwork/training/configs/"
        "qwen3_product_agent_v9_repaired_v2_bullets.yaml"
    )
    qwen3_base_model: str = "Qwen/Qwen3-8B"
    qwen3_gguf_path: Path | None = None
    deepseek_unsloth_model: Path = Path(
        "/mnt/d/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B"
    )
    deepseek_unsloth_load_in_4bit: bool = True
    deepseek_unsloth_max_seq_length: int = 2048
    deepseek_unsloth_max_new_tokens: int = 1024
    deepseek_unsloth_temperature: float = 0.2
    deepseek_unsloth_top_p: float = 0.9
    deepseek_n_gpu_layers: int = -1
    deepseek_main_gpu: int = 0
    qwen3_n_gpu_layers: int = -1
    qwen3_main_gpu: int = 0
    require_gpu_for_llm: bool = True
    product_model_backend: str = "qwen3"
    architect_model_backend: str = "qwen3"
    code_model_backend: str = "qwen_v5"
    test_model_backend: str = "qwen_v5"
    security_model_backend: str = "deepseek"
    reviewer_model_backend: str = "deepseek"
    fixer_model_backend: str = "deepseek"
    final_reviewer_model_backend: str = "deepseek"
    architect_mode: str = "fast"
    architect_fast_model: Path = Path("/mnt/d/Models/qwen3")
    architect_deep_model: Path = Path(
        "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
    )
    architect_output: str = "02_architecture_plan.md"
    security_mode: str = "fast"
    security_fast_model: Path = Path("/mnt/d/Models/qwen3")
    security_deep_model: Path = Path(
        "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
    )
    security_output: str = "05_security.md"
    reviewer_mode: str = "fast"
    reviewer_fast_model: Path = Path("/mnt/d/Models/qwen3")
    reviewer_deep_model: Path = Path(
        "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
    )
    reviewer_output: str = "06_review.md"
    fixer_mode: str = "fast"
    fixer_fast_model: Path = Path("/mnt/d/Models/qwen3")
    fixer_deep_model: Path = Path(
        "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
    )
    fixer_output: str = "07_fix_plan.md"
    final_reviewer_mode: str = "fast"
    final_reviewer_fast_model: Path = Path("/mnt/d/Models/qwen3")
    final_reviewer_deep_model: Path = Path(
        "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
    )
    final_reviewer_output: str = "08_final_review.md"
    stage_isolation: str = "subprocess"

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        deepseek_path = os.getenv("DEEPSEEK_GGUF_PATH")
        qwen3_gguf_path = os.getenv("QWEN3_GGUF_PATH")
        require_gpu_for_llm = _parse_bool(os.getenv("ANN_REQUIRE_GPU_FOR_LLM"), True)
        return cls(
            deepseek_gguf_path=Path(deepseek_path) if deepseek_path else None,
            qwen_base_model=os.getenv("QWEN_BASE_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct"),
            qwen_adapter_path=Path(
                os.getenv("QWEN_ADAPTER_PATH", "training/adapters/qwen-7b-python-expert-v5")
            ),
            qwen3_base_model=os.getenv("QWEN3_BASE_MODEL", "Qwen/Qwen3-8B"),
            qwen3_gguf_path=Path(qwen3_gguf_path) if qwen3_gguf_path else None,
            deepseek_unsloth_model=Path(
                os.getenv(
                    "DEEPSEEK_UNSLOTH_MODEL",
                    "/mnt/d/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B",
                )
            ),
            deepseek_unsloth_load_in_4bit=_parse_bool(
                os.getenv("DEEPSEEK_UNSLOTH_LOAD_IN_4BIT"), True
            ),
            deepseek_unsloth_max_seq_length=int(
                os.getenv("DEEPSEEK_UNSLOTH_MAX_SEQ_LENGTH", "2048")
            ),
            deepseek_unsloth_max_new_tokens=int(
                os.getenv("DEEPSEEK_UNSLOTH_MAX_NEW_TOKENS", "1024")
            ),
            deepseek_unsloth_temperature=float(
                os.getenv("DEEPSEEK_UNSLOTH_TEMPERATURE", "0.2")
            ),
            deepseek_unsloth_top_p=float(os.getenv("DEEPSEEK_UNSLOTH_TOP_P", "0.9")),
            deepseek_n_gpu_layers=_gpu_layers(
                "DEEPSEEK_N_GPU_LAYERS",
                "-1",
                require_gpu=require_gpu_for_llm,
            ),
            deepseek_main_gpu=int(os.getenv("DEEPSEEK_MAIN_GPU", "0")),
            qwen3_n_gpu_layers=_gpu_layers(
                "QWEN3_N_GPU_LAYERS",
                "-1",
                require_gpu=require_gpu_for_llm,
            ),
            qwen3_main_gpu=int(os.getenv("QWEN3_MAIN_GPU", "0")),
            require_gpu_for_llm=require_gpu_for_llm,
            output_dir=Path(os.getenv("OUTPUT_DIR", "outputs/runs")),
            project_root=Path(
                os.getenv("PROJECT_ROOT", "/mnt/d/AgenticEngineeringNetwork")
            ),
            max_new_tokens=int(os.getenv("MAX_NEW_TOKENS", "2048")),
            temperature=float(os.getenv("TEMPERATURE", "0.2")),
            top_p=float(os.getenv("TOP_P", "0.85")),
            context_length=int(os.getenv("CONTEXT_LENGTH", "8192")),
            use_4bit=_parse_bool(os.getenv("USE_4BIT"), True),
            product_max_new_tokens=int(os.getenv("PRODUCT_MAX_NEW_TOKENS", "512")),
            product_temperature=float(os.getenv("PRODUCT_TEMPERATURE", "0.1")),
            product_top_p=float(os.getenv("PRODUCT_TOP_P", "0.7")),
            product_agent_config_path=Path(
                os.getenv(
                    "PRODUCT_AGENT_CONFIG_PATH",
                    "/mnt/d/AgenticEngineeringNetwork/training/configs/"
                    "qwen3_product_agent_v9_repaired_v2_bullets.yaml",
                )
            ),
            product_model_backend=_model_backend("PRODUCT_MODEL_BACKEND", "qwen3"),
            architect_model_backend=_model_backend("ARCHITECT_MODEL_BACKEND", "qwen3"),
            code_model_backend=_model_backend("CODE_MODEL_BACKEND", "qwen_v5"),
            test_model_backend=_model_backend("TEST_MODEL_BACKEND", "qwen_v5"),
            security_model_backend=_model_backend("SECURITY_MODEL_BACKEND", "deepseek"),
            reviewer_model_backend=_model_backend("REVIEWER_MODEL_BACKEND", "deepseek"),
            fixer_model_backend=_model_backend("FIXER_MODEL_BACKEND", "deepseek"),
            final_reviewer_model_backend=_model_backend(
                "FINAL_REVIEWER_MODEL_BACKEND", "deepseek"
            ),
            architect_mode=_architect_mode("ANN_ARCHITECT_MODE", "fast"),
            architect_fast_model=Path(
                os.getenv(
                    "ANN_ARCHITECT_FAST_MODEL",
                    qwen3_gguf_path or "/mnt/d/Models/qwen3",
                )
            ),
            architect_deep_model=Path(
                os.getenv(
                    "ANN_ARCHITECT_DEEP_MODEL",
                    deepseek_path
                    or "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
                )
            ),
            architect_output=os.getenv("ANN_ARCHITECT_OUTPUT", "02_architecture_plan.md"),
            security_mode=_security_mode("ANN_SECURITY_MODE", "fast"),
            security_fast_model=Path(
                os.getenv(
                    "ANN_SECURITY_FAST_MODEL",
                    qwen3_gguf_path or "/mnt/d/Models/qwen3",
                )
            ),
            security_deep_model=Path(
                os.getenv(
                    "ANN_SECURITY_DEEP_MODEL",
                    deepseek_path
                    or "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
                )
            ),
            security_output=os.getenv("ANN_SECURITY_OUTPUT", "05_security.md"),
            reviewer_mode=_reviewer_mode("ANN_REVIEWER_MODE", "fast"),
            reviewer_fast_model=Path(
                os.getenv(
                    "ANN_REVIEWER_FAST_MODEL",
                    qwen3_gguf_path or "/mnt/d/Models/qwen3",
                )
            ),
            reviewer_deep_model=Path(
                os.getenv(
                    "ANN_REVIEWER_DEEP_MODEL",
                    deepseek_path
                    or "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
                )
            ),
            reviewer_output=os.getenv("ANN_REVIEWER_OUTPUT", "06_review.md"),
            fixer_mode=_fixer_mode("ANN_FIXER_MODE", "fast"),
            fixer_fast_model=Path(
                os.getenv(
                    "ANN_FIXER_FAST_MODEL",
                    qwen3_gguf_path or "/mnt/d/Models/qwen3",
                )
            ),
            fixer_deep_model=Path(
                os.getenv(
                    "ANN_FIXER_DEEP_MODEL",
                    deepseek_path
                    or "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
                )
            ),
            fixer_output=os.getenv("ANN_FIXER_OUTPUT", "07_fix_plan.md"),
            final_reviewer_mode=_final_reviewer_mode("ANN_FINAL_REVIEWER_MODE", "fast"),
            final_reviewer_fast_model=Path(
                os.getenv(
                    "ANN_FINAL_REVIEWER_FAST_MODEL",
                    qwen3_gguf_path or "/mnt/d/Models/qwen3",
                )
            ),
            final_reviewer_deep_model=Path(
                os.getenv(
                    "ANN_FINAL_REVIEWER_DEEP_MODEL",
                    deepseek_path
                    or "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
                )
            ),
            final_reviewer_output=os.getenv(
                "ANN_FINAL_REVIEWER_OUTPUT", "08_final_review.md"
            ),
            stage_isolation=_stage_isolation("ANN_STAGE_ISOLATION", "subprocess"),
        )

    def with_architect_model_paths(
        self,
        *,
        qwen3_base_model: str | None = None,
        qwen3_gguf_path: Path | None = None,
        deepseek_gguf_path: Path | None = None,
        deepseek_unsloth_model: Path | None = None,
    ) -> "PipelineConfig":
        """Return a stage-local config with Architect Agent model path overrides."""

        updates: dict[str, object] = {}
        if qwen3_base_model is not None:
            updates["qwen3_base_model"] = qwen3_base_model
        updates["qwen3_gguf_path"] = qwen3_gguf_path
        if deepseek_gguf_path is not None:
            updates["deepseek_gguf_path"] = deepseek_gguf_path
        if deepseek_unsloth_model is not None:
            updates["deepseek_unsloth_model"] = deepseek_unsloth_model
        return replace(self, **updates)
