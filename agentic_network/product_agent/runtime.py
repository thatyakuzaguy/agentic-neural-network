"""Stable Qwen3 Product Agent adapter runtime.

This module intentionally reuses the existing training smoke-test inference functions. It does
not train, download, modify datasets, or modify adapters.
"""

from __future__ import annotations

import re
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from training.scripts.test_qwen3_product_adapter import (
    clean_product_agent_response,
    generate_product_agent_response,
    load_training_config,
)

PRODUCT_AGENT_CONFIG_PATH = Path(
    "/mnt/d/AgenticEngineeringNetwork/training/configs/"
    "qwen3_product_agent_v9_repaired_v2_bullets.yaml"
)
BENCHMARK_PATH = Path(
    "/mnt/d/AgenticEngineeringNetwork/training/eval/"
    "product_agent_v9_repaired_v2_bullets_report.txt"
)
FORBIDDEN_TERMS = (
    "tenant",
    "tenants",
    "workspace",
    "workspaces",
    "organization",
    "organizations",
    "admin",
    "admins",
    "email domain",
    "http status",
    "status code",
    "endpoint",
    "endpoints",
    "api",
    "database",
    "architecture",
)
SECTION_KEYS = {
    "REQUIREMENTS": "requirements",
    "AMBIGUITIES": "ambiguities",
    "ASSUMPTIONS": "assumptions",
    "ACCEPTANCE CRITERIA": "acceptance_criteria",
    "RISKS": "risks",
    "CONFIDENCE": "confidence",
}
SECTION_LINE = re.compile(
    r"^\s*(REQUIREMENTS|AMBIGUITIES|ASSUMPTIONS|ACCEPTANCE CRITERIA|RISKS|CONFIDENCE)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductAgentResult:
    """Structured Product Agent output returned to the pipeline and CLI."""

    raw_instruction: str
    cleaned_response: str
    parsed_sections: dict[str, list[str] | str]
    quality_warnings: list[str]
    adapter_path: str
    config_path: str

    def to_stage_output(self) -> str:
        """Return markdown saved as the pipeline product-stage artifact."""

        if not self.quality_warnings:
            return self.cleaned_response
        warnings = "\n".join(f"- {warning}" for warning in self.quality_warnings)
        return f"{self.cleaned_response}\n\nVALIDATION ERRORS\n{warnings}"


class ProductAgentRuntimeModel(BaseModelClient):
    """BaseModelClient adapter around the stable Qwen3 Product Agent LoRA."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.config_path = _local_path(config.product_agent_config_path)
        self.last_result: ProductAgentResult | None = None

    def run_product_instruction(self, instruction: str) -> str:
        result = run_product_agent(
            instruction,
            config_path=self.config_path,
            max_new_tokens=self.config.product_max_new_tokens,
        )
        self.last_result = result
        return result.to_stage_output()

    def generate_text(self, prompt: str) -> str:
        return self.run_product_instruction(_extract_instruction_from_prompt(prompt))

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        user_messages = [message["content"] for message in messages if message.get("role") == "user"]
        return self.run_product_instruction(user_messages[-1] if user_messages else "")

    def diagnostics(self) -> dict[str, object]:
        config = load_training_config(self.config_path)
        return {
            "backend_name": "qwen3_product_agent",
            "loaded_backend_type": "qwen3_product_adapter",
            "model_path": config.model_name_or_path,
            "adapter_path": str(config.output_dir),
            "config_path": str(self.config_path),
            "max_seq_length": config.max_seq_length,
            "load_in_4bit": config.load_in_4bit,
        }


def run_product_agent(
    instruction: str,
    *,
    config_path: Path = PRODUCT_AGENT_CONFIG_PATH,
    max_new_tokens: int = 512,
    response_generator: Callable[..., str] | None = None,
) -> ProductAgentResult:
    """Run the stable Product Agent and return parsed output plus validation warnings."""

    config_path = _local_path(config_path)
    config = load_training_config(config_path)
    generator = response_generator or generate_product_agent_response
    raw_response = generator(
        instruction=instruction,
        config_path=config_path,
        max_new_tokens=max_new_tokens,
    )
    cleaned_response = clean_product_agent_response(str(raw_response))
    parsed_sections = parse_product_agent_sections(cleaned_response)
    quality_warnings = validate_product_agent_response(
        instruction=instruction,
        cleaned_response=cleaned_response,
        parsed_sections=parsed_sections,
    )
    return ProductAgentResult(
        raw_instruction=instruction,
        cleaned_response=cleaned_response,
        parsed_sections=parsed_sections,
        quality_warnings=quality_warnings,
        adapter_path=str(config.output_dir),
        config_path=str(config_path),
    )


def parse_product_agent_sections(response: str) -> dict[str, list[str] | str]:
    """Split the Product Agent response into normalized named sections."""

    sections: dict[str, list[str] | str] = {}
    current_heading: str | None = None
    for raw_line in response.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = SECTION_LINE.match(line)
        if heading_match:
            current_heading = heading_match.group(1).upper()
            key = SECTION_KEYS[current_heading]
            sections[key] = "" if current_heading == "CONFIDENCE" else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if current_heading == "CONFIDENCE":
            sections[key] = line.lstrip("- ").strip()
        elif line.startswith("- "):
            value = line[2:].strip()
            values = sections.setdefault(key, [])
            if isinstance(values, list):
                values.append(value)
    return sections


def validate_product_agent_response(
    *,
    instruction: str,
    cleaned_response: str,
    parsed_sections: dict[str, list[str] | str],
) -> list[str]:
    """Validate Product Agent contract without hiding failures."""

    warnings: list[str] = []
    for title, key in SECTION_KEYS.items():
        if key not in parsed_sections:
            warnings.append(f"missing_section_{title.lower().replace(' ', '_')}")

    confidence = str(parsed_sections.get("confidence", "")).strip()
    if confidence != "High":
        warnings.append("confidence_not_high")

    lower_response = cleaned_response.lower()
    lower_instruction = instruction.lower()
    if "<think>" in lower_response or "</think>" in lower_response:
        warnings.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", cleaned_response):
        warnings.append("markdown_headings_present")
    if "```" in cleaned_response:
        warnings.append("code_fence_present")

    for forbidden in FORBIDDEN_TERMS:
        if forbidden in lower_response and forbidden not in lower_instruction:
            warnings.append(f"forbidden_term_{forbidden.replace(' ', '_')}")

    return warnings


def _extract_instruction_from_prompt(prompt: str) -> str:
    marker = "INPUT CONTEXT\n-------------"
    if marker not in prompt:
        return prompt.strip()
    after_marker = prompt.split(marker, 1)[1]
    if "\n\nOUTPUT\n------" in after_marker:
        after_marker = after_marker.split("\n\nOUTPUT\n------", 1)[0]
    return after_marker.strip()


def _local_path(path: Path) -> Path:
    """Map /mnt/d and /mnt/e paths to Windows drive paths when running on Windows."""

    if os.name != "nt":
        return path
    text = str(path).replace("\\", "/")
    match = re.match(r"^/mnt/([de])/(.*)$", text, re.IGNORECASE)
    if not match:
        return path
    drive = match.group(1).upper()
    suffix = match.group(2).replace("/", "\\")
    return Path(f"{drive}:\\{suffix}")
