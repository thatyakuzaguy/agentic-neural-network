from pathlib import Path

import pytest

from agentic_network.config import PipelineConfig
from agentic_network.models import qwen3
from agentic_network.models.qwen3 import (
    QWEN3_GGUF_STOP_SEQUENCES,
    Qwen3GGUFModel,
    Qwen3HFModel,
    Qwen3Model,
    clean_qwen3_product_output,
)
from agentic_network.pipeline.runner import PipelineRunner


def _config(tmp_path: Path, *, qwen3_gguf_path: Path | None = None) -> PipelineConfig:
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
        qwen3_base_model="local-qwen3-hf",
        qwen3_gguf_path=qwen3_gguf_path,
    )


class _FakeLlama:
    calls: list[dict[str, object]] = []
    generate_calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)

    def __call__(self, prompt: str, **kwargs: object) -> dict[str, list[dict[str, str]]]:
        self.last_prompt = prompt
        self.last_generate_kwargs = kwargs
        self.generate_calls.append({"prompt": prompt, **kwargs})
        return {
            "choices": [
                {
                    "text": (
                        "REQUIREMENTS\n- Build it.\n\n"
                        "AMBIGUITIES\n- None.\n\n"
                        "ASSUMPTIONS\n- Local run.\n\n"
                        "ACCEPTANCE CRITERIA\n- Output exists.\n\n"
                        "RISKS\n- None.\n\n"
                        "CONFIDENCE\n- High"
                    )
                }
            ]
        }


class _FakeCuda:
    @staticmethod
    def is_available() -> bool:
        return True


class _FakeInferenceMode:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeTorch:
    cuda = _FakeCuda()
    float32 = "float32"
    float16 = "float16"

    @staticmethod
    def device(name: str) -> str:
        return name

    @staticmethod
    def inference_mode() -> _FakeInferenceMode:
        return _FakeInferenceMode()


class _FakeBitsAndBytesConfig:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeTokenizer:
    from_pretrained_calls: list[dict[str, object]] = []
    eos_token_id = 0

    @classmethod
    def from_pretrained(cls, model_name: str, **kwargs: object) -> "_FakeTokenizer":
        cls.from_pretrained_calls.append({"model_name": model_name, **kwargs})
        return cls()


class _FakeModel:
    from_pretrained_calls: list[dict[str, object]] = []

    @classmethod
    def from_pretrained(cls, model_name: str, **kwargs: object) -> "_FakeModel":
        cls.from_pretrained_calls.append({"model_name": model_name, **kwargs})
        return cls()

    def eval(self) -> None:
        return None


class _RuntimeErrorModel:
    def __init__(self, _config: PipelineConfig) -> None:
        self.backend_name = "qwen3"

    def generate_text(self, _prompt: str) -> str:
        raise RuntimeError()

    def generate_chat(self, _messages: list[dict[str, str]]) -> str:
        raise RuntimeError()


def test_qwen3_uses_gguf_backend_when_path_is_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gguf_path = tmp_path / "Qwen3-8B-Q4_K_M.gguf"
    gguf_path.write_bytes(b"local gguf placeholder")
    Qwen3GGUFModel._cache.clear()
    _FakeLlama.calls.clear()
    _FakeLlama.generate_calls.clear()
    monkeypatch.setattr(qwen3, "_load_llama_class", lambda: _FakeLlama)

    model = Qwen3Model(_config(tmp_path, qwen3_gguf_path=gguf_path))

    assert model.runtime == "gguf"
    assert _FakeLlama.calls[0]["model_path"] == str(gguf_path)
    assert _FakeLlama.calls[0]["n_ctx"] == 2048
    assert _FakeLlama.calls[0]["n_gpu_layers"] == -1
    assert _FakeLlama.calls[0]["main_gpu"] == 0
    assert "REQUIREMENTS" in model.generate_text("product prompt")
    assert _FakeLlama.generate_calls[0]["stop"] == list(QWEN3_GGUF_STOP_SEQUENCES)


def test_qwen3_falls_back_to_hf_backend_when_gguf_path_is_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Qwen3HFModel._cache.clear()
    _FakeTokenizer.from_pretrained_calls.clear()
    _FakeModel.from_pretrained_calls.clear()
    monkeypatch.setattr(
        qwen3,
        "_load_transformers_classes",
        lambda: (_FakeTorch, _FakeModel, _FakeTokenizer, _FakeBitsAndBytesConfig),
    )

    model = Qwen3Model(_config(tmp_path, qwen3_gguf_path=None))

    assert model.runtime == "hf"
    assert _FakeTokenizer.from_pretrained_calls == [
        {"model_name": "local-qwen3-hf", "local_files_only": True}
    ]
    assert _FakeModel.from_pretrained_calls[0]["model_name"] == "local-qwen3-hf"
    assert _FakeModel.from_pretrained_calls[0]["local_files_only"] is True


def test_missing_qwen3_gguf_path_gives_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-qwen3.gguf"

    with pytest.raises(
        RuntimeError,
        match="Qwen3 GGUF file does not exist: .*missing-qwen3\\.gguf",
    ):
        Qwen3Model(_config(tmp_path, qwen3_gguf_path=missing_path))


def test_pipeline_error_artifact_includes_exception_class_and_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "agentic_network.pipeline.runner.ProductAgentRuntimeModel",
        _RuntimeErrorModel,
    )
    runner = PipelineRunner(_config(tmp_path), mock=False)

    with pytest.raises(RuntimeError):
        runner.run("Create a product plan", stages=["product"])

    error_files = list((tmp_path / "runs").glob("*/error.md"))
    assert len(error_files) == 1
    assert "RuntimeError: <no message>" in error_files[0].read_text(encoding="utf-8")


def test_qwen3_cleaner_removes_repeated_requirements_blocks() -> None:
    output = clean_qwen3_product_output(
        "REQUIREMENTS\n- First requirement.\n\n"
        "AMBIGUITIES\n- First ambiguity.\n\n"
        "ASSUMPTIONS\n- First assumption.\n\n"
        "ACCEPTANCE CRITERIA\n- First criterion.\n\n"
        "RISKS\n- First risk.\n\n"
        "CONFIDENCE\n- High\n\n"
        "REQUIREMENTS\n- Repeated requirement.\n\n"
        "AMBIGUITIES\n- Repeated ambiguity.\n"
    )

    assert output.count("REQUIREMENTS") == 1
    assert "First requirement" in output
    assert "Repeated requirement" not in output


def test_qwen3_cleaner_removes_reasoning_text() -> None:
    output = clean_qwen3_product_output(
        "Okay, let me analyze the request first.\n"
        "Wait, I should consider edge cases.\n"
        "I think the answer should be structured.\n"
        "REQUIREMENTS\n- Build a small API.\n\n"
        "AMBIGUITIES\n- Authentication is unspecified.\n\n"
        "ASSUMPTIONS\n- Use local defaults.\n\n"
        "ACCEPTANCE CRITERIA\n- API responds successfully.\n\n"
        "RISKS\n- Scope creep.\n\n"
        "CONFIDENCE\n- Medium\n"
    )

    assert "Okay, let me" not in output
    assert "Wait," not in output
    assert "I think" not in output
    assert "REQUIREMENTS" in output


def test_product_prompt_contains_anti_repetition_rules() -> None:
    prompt = Path("agentic_network/prompts/product.md").read_text(encoding="utf-8")

    assert "Do not include reasoning" in prompt
    assert "Do not include markdown code fences" in prompt
    assert "Do not repeat sections" in prompt


def test_product_prompt_forbids_inventing_fields() -> None:
    prompt = Path("agentic_network/prompts/product.md").read_text(encoding="utf-8")

    assert "Do not invent API fields" in prompt
    assert "status values" in prompt
    assert "response shapes" in prompt
    assert "Never introduce new response fields in ASSUMPTIONS" in prompt


def test_product_prompt_says_unrequested_fields_go_to_ambiguities() -> None:
    prompt = Path("agentic_network/prompts/product.md").read_text(encoding="utf-8")

    assert "If something was not explicitly requested" in prompt
    assert "put it under AMBIGUITIES, not ASSUMPTIONS" in prompt
    assert "Never turn an ambiguity into a requirement" in prompt


def test_product_prompt_includes_bullet_limits() -> None:
    prompt = Path("agentic_network/prompts/product.md").read_text(encoding="utf-8")

    assert "REQUIREMENTS: max 7 bullets" in prompt
    assert "AMBIGUITIES: max 5 bullets" in prompt
    assert "ASSUMPTIONS: max 5 bullets" in prompt
    assert "ACCEPTANCE CRITERIA: max 7 bullets" in prompt
    assert "RISKS: max 5 bullets" in prompt


def test_product_prompt_requires_confidence() -> None:
    prompt = Path("agentic_network/prompts/product.md").read_text(encoding="utf-8")

    assert "CONFIDENCE" in prompt
    assert "Allowed values" in prompt or "allowed values" in prompt
    assert "High" in prompt
    assert "Medium" in prompt
    assert "Low" in prompt


def test_qwen3_cleaner_preserves_confidence() -> None:
    output = clean_qwen3_product_output(
        "REQUIREMENTS\n- Build a health endpoint.\n\n"
        "AMBIGUITIES\n- Response shape is not specified.\n\n"
        "ASSUMPTIONS\n- Use FastAPI defaults.\n\n"
        "ACCEPTANCE CRITERIA\n- Endpoint responds successfully.\n\n"
        "RISKS\n- None.\n\n"
        "CONFIDENCE\n- Medium\n"
    )

    assert "CONFIDENCE\n- Medium" in output


def test_qwen3_cleaner_caps_section_bullets() -> None:
    output = clean_qwen3_product_output(
        "REQUIREMENTS\n"
        "- R1\n- R2\n- R3\n- R4\n- R5\n- R6\n- R7\n- R8\n\n"
        "AMBIGUITIES\n"
        "- A1\n- A2\n- A3\n- A4\n- A5\n- A6\n\n"
        "ASSUMPTIONS\n"
        "- S1\n- S2\n- S3\n- S4\n- S5\n- S6\n\n"
        "ACCEPTANCE CRITERIA\n"
        "- C1\n- C2\n- C3\n- C4\n- C5\n- C6\n- C7\n- C8\n\n"
        "RISKS\n"
        "- K1\n- K2\n- K3\n- K4\n- K5\n- K6\n\n"
        "CONFIDENCE\n- High\n- Medium\n"
    )

    sections = _section_map(output)
    assert len(sections["REQUIREMENTS"]) == 7
    assert len(sections["AMBIGUITIES"]) == 5
    assert len(sections["ASSUMPTIONS"]) == 5
    assert len(sections["ACCEPTANCE CRITERIA"]) == 7
    assert len(sections["RISKS"]) == 5
    assert sections["CONFIDENCE"] == ["- High"]


def test_qwen3_cleaner_removes_duplicate_sections_without_deleting_confidence() -> None:
    output = clean_qwen3_product_output(
        "REQUIREMENTS\n- First requirement.\n\n"
        "AMBIGUITIES\n- First ambiguity.\n\n"
        "ASSUMPTIONS\n- First assumption.\n\n"
        "ACCEPTANCE CRITERIA\n- First criterion.\n\n"
        "RISKS\n- First risk.\n\n"
        "CONFIDENCE\n- High\n\n"
        "REQUIREMENTS\n- Repeated requirement.\n\n"
        "CONFIDENCE\n- Low\n"
    )

    assert output.count("REQUIREMENTS") == 1
    assert "Repeated requirement" not in output
    assert "CONFIDENCE\n- High" in output
    assert "- Low" not in output


def test_product_qwen3_uses_product_max_new_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeProductAgentRuntimeModel:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

        def run_product_instruction(self, instruction: str) -> str:
            calls.append(
                {
                    "instruction": instruction,
                    "max_new_tokens": self.config.product_max_new_tokens,
                    "temperature": self.config.product_temperature,
                    "top_p": self.config.product_top_p,
                }
            )
            return "REQUIREMENTS\n- Product plan.\n\nCONFIDENCE\nHigh"

    monkeypatch.setattr(
        "agentic_network.pipeline.runner.ProductAgentRuntimeModel",
        _FakeProductAgentRuntimeModel,
    )

    config = _config(tmp_path, qwen3_gguf_path=None)
    runner = PipelineRunner(config, mock=False)

    runner.run("Create a tiny Product Agent plan", stages=["product"])

    assert calls == [
        {
            "instruction": "Create a tiny Product Agent plan",
            "max_new_tokens": 512,
            "temperature": 0.1,
            "top_p": 0.7,
        }
    ]


def _section_map(output: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in output.splitlines():
        if line in {
            "REQUIREMENTS",
            "AMBIGUITIES",
            "ASSUMPTIONS",
            "ACCEPTANCE CRITERIA",
            "RISKS",
            "CONFIDENCE",
        }:
            current = line
            sections[current] = []
        elif current and line.startswith("- "):
            sections[current].append(line)
    return sections
