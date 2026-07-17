import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_network.config import PipelineConfig
from agentic_network.models import qwen3
from agentic_network.models.deepseek_gguf import DeepSeekGGUFModel
from agentic_network.models.deepseek_unsloth import DeepSeekUnslothModel
from agentic_network.models.qwen3 import Qwen3GGUFModel, Qwen3HFModel
from agentic_network.models.qwen_unsloth import QwenUnslothModel


def _config(
    tmp_path: Path,
    *,
    deepseek_gguf_path: Path | None = None,
    deepseek_unsloth_model: Path | None = None,
    qwen3_gguf_path: Path | None = None,
    use_4bit: bool = True,
) -> PipelineConfig:
    return PipelineConfig(
        deepseek_gguf_path=deepseek_gguf_path,
        qwen_base_model="local-qwen-2.5-coder",
        qwen_adapter_path=tmp_path / "adapter",
        output_dir=tmp_path / "runs",
        max_new_tokens=128,
        temperature=0.2,
        top_p=0.85,
        context_length=2048,
        use_4bit=use_4bit,
        qwen3_base_model="local-qwen3-hf",
        qwen3_gguf_path=qwen3_gguf_path,
        deepseek_unsloth_model=deepseek_unsloth_model or tmp_path / "deepseek-hf",
    )


class _FakeLlama:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)

    def __call__(self, *_args: object, **_kwargs: object) -> dict[str, list[dict[str, str]]]:
        return {"choices": [{"text": "ok"}]}


class _CudaTrue:
    @staticmethod
    def is_available() -> bool:
        return True


class _CudaFalse:
    @staticmethod
    def is_available() -> bool:
        return False


class _FakeInferenceMode:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeTorchCuda:
    cuda = _CudaTrue()
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


class _FakeHFModel:
    from_pretrained_calls: list[dict[str, object]] = []
    to_calls: list[object] = []

    @classmethod
    def from_pretrained(cls, model_name: str, **kwargs: object) -> "_FakeHFModel":
        cls.from_pretrained_calls.append({"model_name": model_name, **kwargs})
        return cls()

    def to(self, device: object) -> None:
        self.to_calls.append(device)

    def eval(self) -> None:
        return None


class _FakeUnslothModel:
    to_calls: list[object] = []
    load_adapter_calls: list[dict[str, object]] = []
    set_adapter_calls: list[str] = []
    generate_calls: list[dict[str, object]] = []

    def load_adapter(self, path: str, adapter_name: str) -> None:
        self.load_adapter_calls.append({"path": path, "adapter_name": adapter_name})

    def set_adapter(self, adapter_name: str) -> None:
        self.set_adapter_calls.append(adapter_name)

    def to(self, device: object) -> None:
        self.to_calls.append(device)

    def generate(self, **kwargs: object) -> list["_FakeGeneratedSequence"]:
        self.generate_calls.append(kwargs)
        return [_FakeGeneratedSequence()]


class _FakeGeneratedSequence:
    def __getitem__(self, key: object) -> list[int]:
        if isinstance(key, slice):
            return [20, 21]
        return [10, 11, 20, 21]


class _FakeInputIds:
    shape = (1, 2)

    def to(self, device: object) -> "_FakeInputIds":
        self.device = device
        return self


class _FakeUnslothTokenizer:
    eos_token_id = 0
    apply_chat_template_calls: list[dict[str, object]] = []

    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: object) -> _FakeInputIds:
        self.apply_chat_template_calls.append({"messages": messages, **kwargs})
        return _FakeInputIds()

    def decode(self, tokens: object, skip_special_tokens: bool) -> str:
        return "<think>hidden reasoning</think>clean final"


class _FakeFastLanguageModel:
    from_pretrained_calls: list[dict[str, object]] = []
    for_inference_calls: list[object] = []

    @classmethod
    def from_pretrained(cls, **kwargs: object) -> tuple[_FakeUnslothModel, object]:
        cls.from_pretrained_calls.append(kwargs)
        return _FakeUnslothModel(), _FakeUnslothTokenizer()

    @classmethod
    def for_inference(cls, model: object) -> None:
        cls.for_inference_calls.append(model)


def test_gpu_config_defaults_to_full_gguf_offload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_N_GPU_LAYERS", raising=False)
    monkeypatch.delenv("DEEPSEEK_MAIN_GPU", raising=False)
    monkeypatch.delenv("QWEN3_N_GPU_LAYERS", raising=False)
    monkeypatch.delenv("QWEN3_MAIN_GPU", raising=False)

    config = PipelineConfig.from_env()

    assert config.deepseek_n_gpu_layers == -1
    assert config.deepseek_main_gpu == 0
    assert config.qwen3_n_gpu_layers == -1
    assert config.qwen3_main_gpu == 0


def test_gpu_config_rejects_cpu_offload_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANN_REQUIRE_GPU_FOR_LLM", "true")
    monkeypatch.setenv("DEEPSEEK_N_GPU_LAYERS", "0")

    with pytest.raises(ValueError, match="forces CPU inference"):
        PipelineConfig.from_env()


def test_gpu_config_allows_cpu_offload_only_when_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANN_REQUIRE_GPU_FOR_LLM", "false")
    monkeypatch.setenv("QWEN3_N_GPU_LAYERS", "0")

    config = PipelineConfig.from_env()

    assert config.require_gpu_for_llm is False
    assert config.qwen3_n_gpu_layers == 0


def test_deepseek_unsloth_config_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DEEPSEEK_UNSLOTH_MODEL",
        "/mnt/d/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B",
    )
    monkeypatch.setenv("DEEPSEEK_UNSLOTH_LOAD_IN_4BIT", "false")
    monkeypatch.setenv("DEEPSEEK_UNSLOTH_MAX_SEQ_LENGTH", "4096")
    monkeypatch.setenv("DEEPSEEK_UNSLOTH_MAX_NEW_TOKENS", "1536")
    monkeypatch.setenv("DEEPSEEK_UNSLOTH_TEMPERATURE", "0.3")
    monkeypatch.setenv("DEEPSEEK_UNSLOTH_TOP_P", "0.95")

    config = PipelineConfig.from_env()

    assert config.deepseek_unsloth_model == Path(
        "/mnt/d/Models/deepseek_hf/DeepSeek-R1-Distill-Qwen-14B"
    )
    assert config.deepseek_unsloth_load_in_4bit is False
    assert config.deepseek_unsloth_max_seq_length == 4096
    assert config.deepseek_unsloth_max_new_tokens == 1536
    assert config.deepseek_unsloth_temperature == 0.3
    assert config.deepseek_unsloth_top_p == 0.95


def test_deepseek_llama_receives_gpu_offload_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "deepseek.gguf"
    model_path.write_bytes(b"gguf")
    _FakeLlama.calls.clear()
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=_FakeLlama))

    model = DeepSeekGGUFModel(_config(tmp_path, deepseek_gguf_path=model_path))

    assert _FakeLlama.calls[0]["n_gpu_layers"] == -1
    assert _FakeLlama.calls[0]["main_gpu"] == 0
    assert model.diagnostics()["device_mode"] == "gpu_all_possible_layers"


def test_deepseek_gguf_rejects_cpu_layer_configuration(tmp_path: Path) -> None:
    model_path = tmp_path / "deepseek.gguf"
    model_path.write_bytes(b"gguf")
    config = replace(
        _config(tmp_path, deepseek_gguf_path=model_path),
        deepseek_n_gpu_layers=0,
    )

    with pytest.raises(RuntimeError, match="forces CPU inference"):
        DeepSeekGGUFModel(config)


def test_qwen3_gguf_llama_receives_gpu_offload_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "qwen3.gguf"
    model_path.write_bytes(b"gguf")
    _FakeLlama.calls.clear()
    Qwen3GGUFModel._cache.clear()
    monkeypatch.setattr(qwen3, "_load_llama_class", lambda: _FakeLlama)

    model = Qwen3GGUFModel(_config(tmp_path, qwen3_gguf_path=model_path))

    assert _FakeLlama.calls[0]["n_gpu_layers"] == -1
    assert _FakeLlama.calls[0]["main_gpu"] == 0
    assert model.diagnostics()["device_mode"] == "gpu_all_possible_layers"


def test_qwen3_gguf_rejects_cpu_layer_configuration(tmp_path: Path) -> None:
    model_path = tmp_path / "qwen3.gguf"
    model_path.write_bytes(b"gguf")
    config = replace(_config(tmp_path, qwen3_gguf_path=model_path), qwen3_n_gpu_layers=0)

    with pytest.raises(RuntimeError, match="forces CPU inference"):
        Qwen3GGUFModel(config)


def test_qwen3_hf_uses_cuda_device_map_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Qwen3HFModel._cache.clear()
    _FakeTokenizer.from_pretrained_calls.clear()
    _FakeHFModel.from_pretrained_calls.clear()
    _FakeHFModel.to_calls.clear()
    monkeypatch.setattr(
        qwen3,
        "_load_transformers_classes",
        lambda: (_FakeTorchCuda, _FakeHFModel, _FakeTokenizer, _FakeBitsAndBytesConfig),
    )

    model = Qwen3HFModel(_config(tmp_path))

    assert _FakeTokenizer.from_pretrained_calls[0]["local_files_only"] is True
    assert _FakeHFModel.from_pretrained_calls[0]["local_files_only"] is True
    assert _FakeHFModel.from_pretrained_calls[0]["device_map"] == "auto"
    assert _FakeHFModel.to_calls == []
    assert model.diagnostics()["device_mode"] == "cuda_device_map_auto"


def test_qwen3_hf_rejects_cpu_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Qwen3HFModel._cache.clear()
    fake_torch = SimpleNamespace(cuda=_CudaFalse())
    monkeypatch.setattr(
        qwen3,
        "_load_transformers_classes",
        lambda: (fake_torch, _FakeHFModel, _FakeTokenizer, _FakeBitsAndBytesConfig),
    )

    with pytest.raises(RuntimeError, match="requires CUDA/GPU"):
        Qwen3HFModel(_config(tmp_path))


def test_qwen_unsloth_uses_cuda_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter_path = tmp_path / "adapter"
    adapter_path.mkdir()
    QwenUnslothModel._cache.clear()
    _FakeFastLanguageModel.from_pretrained_calls.clear()
    _FakeFastLanguageModel.for_inference_calls.clear()
    _FakeUnslothModel.to_calls.clear()
    fake_torch = SimpleNamespace(
        cuda=_CudaTrue(),
        device=lambda name: name,
        inference_mode=lambda: _FakeInferenceMode(),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "unsloth",
        SimpleNamespace(FastLanguageModel=_FakeFastLanguageModel),
    )

    model = QwenUnslothModel(_config(tmp_path))

    assert _FakeFastLanguageModel.from_pretrained_calls[0]["local_files_only"] is True
    assert _FakeUnslothModel.to_calls == ["cuda"]
    assert model.diagnostics()["device_mode"] == "cuda"


def test_qwen_unsloth_rejects_cpu_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter_path = tmp_path / "adapter"
    adapter_path.mkdir()
    QwenUnslothModel._cache.clear()
    _FakeFastLanguageModel.from_pretrained_calls.clear()
    fake_torch = SimpleNamespace(cuda=_CudaFalse())
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "unsloth",
        SimpleNamespace(FastLanguageModel=_FakeFastLanguageModel),
    )

    with pytest.raises(RuntimeError, match="requires CUDA/GPU"):
        QwenUnslothModel(_config(tmp_path))
    assert _FakeFastLanguageModel.from_pretrained_calls == []


def test_deepseek_unsloth_uses_local_files_only_and_cleans_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "deepseek-hf"
    model_path.mkdir()
    DeepSeekUnslothModel._cache.clear()
    _FakeFastLanguageModel.from_pretrained_calls.clear()
    _FakeFastLanguageModel.for_inference_calls.clear()
    _FakeUnslothModel.to_calls.clear()
    _FakeUnslothModel.generate_calls.clear()
    fake_torch = SimpleNamespace(
        cuda=_CudaTrue(),
        device=lambda name: name,
        inference_mode=lambda: _FakeInferenceMode(),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "unsloth",
        SimpleNamespace(FastLanguageModel=_FakeFastLanguageModel),
    )

    model = DeepSeekUnslothModel(_config(tmp_path, deepseek_unsloth_model=model_path))

    output = model.generate_text("hello")

    assert _FakeFastLanguageModel.from_pretrained_calls[0]["model_name"] == str(model_path)
    assert _FakeFastLanguageModel.from_pretrained_calls[0]["local_files_only"] is True
    assert _FakeFastLanguageModel.from_pretrained_calls[0]["load_in_4bit"] is True
    assert _FakeUnslothModel.to_calls == ["cuda"]
    assert _FakeUnslothModel.generate_calls[0]["max_new_tokens"] == 1024
    assert output == "clean final"
    diagnostics = model.diagnostics()
    assert diagnostics["backend_name"] == "deepseek_unsloth"
    assert diagnostics["device"] == "cuda"
    assert diagnostics["load_in_4bit"] is True
    assert diagnostics["max_seq_length"] == 2048
    assert diagnostics["model_path"] == str(model_path)


def test_deepseek_unsloth_rejects_cpu_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "deepseek-hf"
    model_path.mkdir()
    DeepSeekUnslothModel._cache.clear()
    _FakeFastLanguageModel.from_pretrained_calls.clear()
    fake_torch = SimpleNamespace(cuda=_CudaFalse())
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "unsloth",
        SimpleNamespace(FastLanguageModel=_FakeFastLanguageModel),
    )

    with pytest.raises(RuntimeError, match="requires CUDA/GPU"):
        DeepSeekUnslothModel(_config(tmp_path, deepseek_unsloth_model=model_path))
    assert _FakeFastLanguageModel.from_pretrained_calls == []
