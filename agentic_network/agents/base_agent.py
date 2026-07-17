"""Base agent implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentic_network.models.base import BaseModelClient

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


@dataclass
class BaseAgent:
    """A named agent with a model and strict system prompt."""

    name: str
    model: BaseModelClient
    system_prompt: str
    output_cleaner: Callable[[str], str] | None = None

    def run(self, input_text: str) -> str:
        print(f"Starting {self.name}...")
        prompt = self.format_prompt(input_text)
        output = self.model.generate_text(prompt)
        if self.output_cleaner is not None:
            output = self.output_cleaner(output)
        print(f"Finished {self.name}.")
        return output.strip()

    def format_prompt(self, input_text: str) -> str:
        return (
            f"{self.system_prompt}\n\n"
            "INPUT CONTEXT\n"
            "-------------\n"
            f"{input_text.strip()}\n\n"
            "OUTPUT\n"
            "------\n"
        )
