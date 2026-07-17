from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models import qwen3
from agentic_network.models.qwen3 import Qwen3HFModel


def _config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        deepseek_gguf_path=None,
        qwen_base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        qwen_adapter_path=Path("training/adapters/qwen-7b-python-expert-v5"),
        output_dir=tmp_path / "runs",
        max_new_tokens=7,
        temperature=0.2,
        top_p=0.85,
        context_length=128,
        use_4bit=True,
        qwen3_base_model="local-qwen3-hf",
        qwen3_gguf_path=None,
    )


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


class _FakeTensor:
    def __init__(self, values: list[int]) -> None:
        self.values = values
        self.shape = (1, len(values))
        self.moved_to: object | None = None

    def to(self, device: object) -> "_FakeTensor":
        self.moved_to = device
        return self


class _FakeGeneratedRow:
    def __init__(self, values: list[int]) -> None:
        self.values = values

    def __getitem__(self, index: slice) -> list[int]:
        return self.values[index]


class _FakeBatch(dict[str, _FakeTensor]):
    def to(self, device: object) -> "_FakeBatch":
        for value in self.values():
            value.to(device)
        return self


class _FakeTokenizer:
    eos_token_id = 0
    last_instance: "_FakeTokenizer | None" = None

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.decoded_tokens: object | None = None

    @classmethod
    def from_pretrained(cls, _model_name: str, **_kwargs: object) -> "_FakeTokenizer":
        cls.last_instance = cls()
        return cls.last_instance

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        assert tokenize is False
        assert add_generation_prompt is True
        return "\n".join(message["content"] for message in messages) + "\nASSISTANT:"

    def __call__(self, prompt: str, **kwargs: object) -> _FakeBatch:
        self.calls.append({"prompt": prompt, **kwargs})
        return _FakeBatch(
            {
                "input_ids": _FakeTensor([101, 102, 103]),
                "attention_mask": _FakeTensor([1, 1, 1]),
            }
        )

    def decode(self, tokens: object, *, skip_special_tokens: bool) -> str:
        self.decoded_tokens = tokens
        assert skip_special_tokens is True
        assert tokens == [201, 202]
        return "TECHNICAL SUMMARY\n- Fake architecture output."


class _FakeModel:
    last_instance: "_FakeModel | None" = None

    def __init__(self) -> None:
        self.device = "model-device"
        self.generate_args: tuple[object, ...] | None = None
        self.generate_kwargs: dict[str, object] | None = None

    @classmethod
    def from_pretrained(cls, _model_name: str, **_kwargs: object) -> "_FakeModel":
        cls.last_instance = cls()
        return cls.last_instance

    def eval(self) -> None:
        return None

    def generate(self, *args: object, **kwargs: object) -> list[_FakeGeneratedRow]:
        self.generate_args = args
        self.generate_kwargs = kwargs
        assert args == ()
        assert isinstance(kwargs["input_ids"], _FakeTensor)
        assert isinstance(kwargs["attention_mask"], _FakeTensor)
        return [_FakeGeneratedRow([101, 102, 103, 201, 202])]


def test_qwen3_hf_generate_uses_keyword_tensors_and_decodes_new_tokens(
    monkeypatch,
    tmp_path: Path,
) -> None:
    Qwen3HFModel._cache.clear()
    monkeypatch.setattr(
        qwen3,
        "_load_transformers_classes",
        lambda: (_FakeTorch, _FakeModel, _FakeTokenizer, _FakeBitsAndBytesConfig),
    )

    model = Qwen3HFModel(_config(tmp_path))

    chat_output = model.generate_chat([{"role": "user", "content": "Plan a small change."}])
    text_output = model.generate_text("Plan another small change.")

    fake_model = _FakeModel.last_instance
    fake_tokenizer = _FakeTokenizer.last_instance
    assert fake_model is not None
    assert fake_tokenizer is not None
    assert chat_output.startswith("TECHNICAL SUMMARY")
    assert text_output.startswith("TECHNICAL SUMMARY")
    assert fake_model.generate_args == ()
    assert fake_model.generate_kwargs is not None
    assert fake_model.generate_kwargs["max_new_tokens"] == 7
    assert fake_model.generate_kwargs["eos_token_id"] == 0
    assert fake_model.generate_kwargs["pad_token_id"] == 0
    assert fake_model.generate_kwargs["input_ids"].moved_to == "model-device"
    assert fake_model.generate_kwargs["attention_mask"].moved_to == "model-device"
    assert fake_tokenizer.calls[-1]["return_tensors"] == "pt"
    assert fake_tokenizer.decoded_tokens == [201, 202]
