from __future__ import annotations

try:
    from unsloth import FastLanguageModel
except ImportError as exc:
    FastLanguageModel = None
    UNSLOTH_IMPORT_ERROR = exc
else:
    UNSLOTH_IMPORT_ERROR = None

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.scripts.train_unsloth_qwen3_product import (
    CHATML_END,
    DEFAULT_CONFIG_PATH,
    configure_offline_d_cache,
    format_product_agent_inference_prompt,
    load_training_config,
)


PRODUCT_AGENT_SECTIONS = (
    "REQUIREMENTS",
    "AMBIGUITIES",
    "ASSUMPTIONS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "CONFIDENCE",
)
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
SECTION_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?"
    r"(REQUIREMENTS|AMBIGUITIES|ASSUMPTIONS|ACCEPTANCE CRITERIA|RISKS|CONFIDENCE)"
    r"(?:\*\*)?\s*:?\s*(.*)$",
    re.IGNORECASE,
)
GENERIC_AMBIGUITIES = {
    "what is the definition of a tenant?",
    "what is the definition of a user?",
    "what is the definition of a customer invoice?",
}
FORBIDDEN_TERMS = {
    "tenant",
    "workspace",
    "organization",
    "support admin",
    "admin",
    "email domain",
    "database",
    "endpoint",
    "api",
}


def _normalize_bullet(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def stop_generated_text(text: str) -> str:
    cut_points = [index for marker in (CHATML_END, "</think>") if (index := text.find(marker)) >= 0]
    first_requirements = re.search(r"(?im)^\s*requirements\b", text)
    if first_requirements:
        repeated_requirements = re.search(
            r"(?im)^\s*requirements\b",
            text[first_requirements.end() :],
        )
        if repeated_requirements:
            cut_points.append(first_requirements.end() + repeated_requirements.start())
    return text[: min(cut_points)] if cut_points else text


def _normalize_section_heading(line: str) -> tuple[str, str] | None:
    match = SECTION_LINE.match(line)
    if not match:
        return None
    return match.group(1).upper(), match.group(2).strip()


def _drop_after_confidence_first_bullet(lines: list[str]) -> list[str]:
    kept: list[str] = []
    in_confidence = False
    confidence_bullet_seen = False
    for line in lines:
        heading_match = _normalize_section_heading(line)
        heading = heading_match[0] if heading_match else None
        if heading == "CONFIDENCE":
            in_confidence = True
            kept.append("CONFIDENCE")
            continue
        if in_confidence:
            heading_match = _normalize_section_heading(line)
            heading = heading_match[0] if heading_match else None
            if heading and heading != "CONFIDENCE":
                break
            if line.strip().startswith("- "):
                if confidence_bullet_seen:
                    break
                confidence_bullet_seen = True
                kept.append(line)
                continue
            if confidence_bullet_seen and line.strip():
                break
        kept.append(line)
    return kept


def clean_product_agent_response(text: str) -> str:
    text = THINK_BLOCK.sub("", text)
    text = text.replace("<think>", "").replace("</think>", "")
    text = stop_generated_text(text)

    first_section = re.search(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?requirements\b",
        text,
    )
    if first_section:
        text = text[first_section.start() :]

    cleaned_lines: list[str] = []
    current_section: str | None = None
    seen_bullets_by_section: dict[str, set[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = _normalize_section_heading(line)
        if heading_match:
            heading, remainder = heading_match
            current_section = heading
            cleaned_lines.append(heading)
            seen_bullets_by_section.setdefault(heading, set())

            if remainder:
                remainder = remainder.rstrip(".").strip() if heading == "CONFIDENCE" else remainder
                if heading == "CONFIDENCE":
                    cleaned_lines.append(remainder)
                elif remainder.startswith("- "):
                    normalized = _normalize_bullet(remainder[2:])
                    if normalized not in seen_bullets_by_section[heading]:
                        seen_bullets_by_section[heading].add(normalized)
                        cleaned_lines.append(remainder)
                else:
                    normalized = _normalize_bullet(remainder)
                    if normalized not in seen_bullets_by_section[heading]:
                        seen_bullets_by_section[heading].add(normalized)
                        cleaned_lines.append(f"- {remainder}")
            continue
        if current_section == "CONFIDENCE" and line.startswith("- "):
            cleaned_lines.append(line[2:].rstrip(".").strip())
            continue
        if current_section and line.startswith("- "):
            normalized = _normalize_bullet(line[2:])
            if normalized in seen_bullets_by_section[current_section]:
                continue
            seen_bullets_by_section[current_section].add(normalized)
        cleaned_lines.append(line)

    cleaned_lines = _drop_after_confidence_first_bullet(cleaned_lines)
    return "\n".join(cleaned_lines).strip()


def product_agent_quality_issues(response: str, *, task: str = "") -> list[str]:
    issues: list[str] = []
    lower_response = response.lower()
    if "<think>" in lower_response or "</think>" in lower_response:
        issues.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", response) or re.search(
        r"(?m)^\s*\*\*(requirements|ambiguities|assumptions|acceptance criteria|risks|confidence)\*\*",
        response,
        re.IGNORECASE,
    ):
        issues.append("markdown_headings_present")

    headings = []
    bullets_by_section: dict[str, list[str]] = {}
    current_section: str | None = None
    for line in response.splitlines():
        heading_match = _normalize_section_heading(line)
        heading = heading_match[0] if heading_match else None
        if heading:
            headings.append(heading)
            current_section = heading
            bullets_by_section.setdefault(heading, [])
            continue
        if current_section and line.strip().startswith("- "):
            bullets_by_section[current_section].append(line.strip()[2:].strip())

    heading_counts = Counter(headings)
    for section in PRODUCT_AGENT_SECTIONS:
        if heading_counts[section] != 1:
            issues.append(f"section_{section.lower().replace(' ', '_')}_count_{heading_counts[section]}")
    if heading_counts["REQUIREMENTS"] > 1:
        issues.append("repeated_section_block")

    for section, bullets in bullets_by_section.items():
        normalized = [_normalize_bullet(bullet) for bullet in bullets]
        if len(normalized) != len(set(normalized)):
            issues.append(f"repeated_bullets_{section.lower().replace(' ', '_')}")

    ambiguity_bullets = bullets_by_section.get("AMBIGUITIES", [])
    for bullet in ambiguity_bullets:
        if _normalize_bullet(bullet) in GENERIC_AMBIGUITIES:
            issues.append("generic_ambiguity")
            break

    database_phrase = "including direct access to the database"
    if database_phrase in lower_response and "database access" not in task.lower():
        issues.append("impossible_database_acceptance")
    lower_task = task.lower()

    for forbidden in FORBIDDEN_TERMS:
        if forbidden in lower_response and forbidden not in lower_task:
            issues.append(
                f"forbidden_term_{forbidden.replace(' ', '_')}"
            )
    return issues


def _load_base_and_adapter(config_path: Path) -> tuple[Any, Any, Any]:
    config = load_training_config(config_path)
    configure_offline_d_cache(config)
    if FastLanguageModel is None:
        raise RuntimeError("Unsloth is required for adapter inference.") from UNSLOTH_IMPORT_ERROR

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name_or_path,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
        local_files_only=config.local_files_only,
    )
    if hasattr(model, "load_adapter"):
        model.load_adapter(str(config.output_dir), adapter_name="product_agent")
        if hasattr(model, "set_adapter"):
            model.set_adapter("product_agent")
    else:
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model,
            str(config.output_dir),
            local_files_only=config.local_files_only,
        )
    FastLanguageModel.for_inference(model)
    return config, model, tokenizer


def generate_product_agent_response(
    *,
    instruction: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
    max_new_tokens: int = 512,
) -> str:
    _, model, tokenizer = _load_base_and_adapter(config_path)
    prompt = format_product_agent_inference_prompt(instruction)
    inputs = tokenizer(prompt, return_tensors="pt")
    if hasattr(model, "device"):
        inputs = {key: value.to(model.device) for key, value in inputs.items()}

    eos_token_id = tokenizer.convert_tokens_to_ids(CHATML_END)
    if eos_token_id == getattr(tokenizer, "unk_token_id", None):
        eos_token_id = getattr(tokenizer, "eos_token_id", None)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        temperature=0.0,
        eos_token_id=eos_token_id,
        pad_token_id=getattr(tokenizer, "eos_token_id", None),
    )
    prompt_length = inputs["input_ids"].shape[-1]
    assistant_ids = output_ids[0][prompt_length:]
    raw_response = tokenizer.decode(assistant_ids, skip_special_tokens=False)
    cleaned = clean_product_agent_response(raw_response)
    issues = product_agent_quality_issues(cleaned, task=instruction)
    if issues:
        print(f"Quality warnings: {', '.join(issues)}", file=sys.stderr)
    return cleaned


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Qwen3 Product Agent adapter inference.")
    parser.add_argument("instruction")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        generate_product_agent_response(
            instruction=args.instruction,
            config_path=args.config,
            max_new_tokens=args.max_new_tokens,
        )
    )


if __name__ == "__main__":
    main()
