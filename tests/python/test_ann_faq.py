from __future__ import annotations

from pathlib import Path


def test_ann_faq_contains_required_questions() -> None:
    text = Path("D:/AgenticEngineeringNetwork/README_FAQ.md").read_text(encoding="utf-8")

    for question in (
        "What is ANN?",
        "Does ANN need internet?",
        "Does ANN modify models?",
        "Does ANN train models?",
        "Does ANN use Ollama?",
        "What is FAST?",
        "What is POWERFUL?",
        "Why is Qwen3 blocked?",
        "Why is DeepSeek blocked?",
        "What is Safe Mode?",
        "Can ANN execute dangerous commands?",
        "Can ANN modify .git?",
        "Can ANN access C:?",
        "What is Sequential Runtime?",
    ):
        assert question in text
