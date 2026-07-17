"""Reviewer Agent runtime, parser, validation, and model adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import DeepSeekGGUFModel, clean_deepseek_output
from agentic_network.models.deepseek_unsloth import DeepSeekUnslothModel
from agentic_network.models.qwen3 import Qwen3Model

REVIEW_OUTPUT_FILE = "06_review.md"
PROMPT_PATH = Path(__file__).with_name("prompt.md")
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
APPROVAL_STATUSES = {"Approved", "Needs Fixes"}
SECTION_KEYS = {
    "CONSISTENCY CHECK": "consistency_check",
    "REQUIREMENT GAPS": "requirement_gaps",
    "ARCHITECTURE GAPS": "architecture_gaps",
    "IMPLEMENTATION RISKS": "implementation_risks",
    "TEST COVERAGE GAPS": "test_coverage_gaps",
    "SECURITY GAPS": "security_gaps",
    "RECOMMENDATIONS": "recommendations",
    "APPROVAL STATUS": "approval_status",
    "CONFIDENCE": "confidence",
}
REVIEW_LIST_KEYS = tuple(
    key for title, key in SECTION_KEYS.items() if title not in {"APPROVAL STATUS", "CONFIDENCE"}
)
REQUIRED_SECTION_TITLES = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*("
    + "|".join(re.escape(title) for title in REQUIRED_SECTION_TITLES)
    + r")\s*$",
    re.IGNORECASE,
)
NUMBERED_LIST_LINE = re.compile(r"^(\s*)\d+[\.)]\s+(.+)$")
PATCH_MARKER_LINE = re.compile(r"(?m)^\s*(?:\+\+\+|---|@@)(?:\s|$)")
THINK_BLOCK_PATTERN = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
THINK_START_PATTERN = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
THINK_TAG_PATTERN = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)
FORBIDDEN_CODE_PATTERNS = {
    "forbidden_import_statement": re.compile(
        r"(?m)^\s*(?:from\s+\S+\s+import\b|import\s+\S+)"
    ),
    "forbidden_function_definition": re.compile(r"\bdef\s+\w+\s*\("),
    "forbidden_class_definition": re.compile(r"\bclass\s+\w+"),
    "forbidden_decorator": re.compile(r"(?m)^\s*@"),
    "forbidden_return_statement": re.compile(r"\breturn\s+"),
    "forbidden_raise_statement": re.compile(r"\braise\s+"),
    "forbidden_except_block": re.compile(r"\bexcept\b"),
    "forbidden_try_block": re.compile(r"\btry\s*:"),
}
FORBIDDEN_FIX_OR_COMMAND_PATTERNS = {
    "forbidden_command_present": re.compile(
        r"(?im)^\s*(?:touch|mkdir|cat\s+>|tee\s+|echo\s+.+>|python\s+-m\s+|pytest|"
        r"git\s+apply|git\s+diff|apply_patch)\b"
    ),
    "forbidden_fix_instructions": re.compile(
        r"(?i)\b(?:apply\s+this\s+fix|use\s+this\s+patch|replace\s+.+\s+with|"
        r"change\s+the\s+code\s+to|add\s+the\s+following\s+code)\b"
    ),
}


@dataclass(frozen=True)
class ReviewerAgentResult:
    """Structured Reviewer Agent output returned to the pipeline and CLI."""

    raw_user_request: str
    product_requirements_input: str
    architecture_plan_input: str
    code_plan_input: str
    test_plan_input: str
    security_review_input: str
    review_output: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    fallback_used: bool
    artifact_path: str | None = None

    def to_stage_output(self) -> str:
        """Return the review artifact saved as the pipeline reviewer stage."""

        return self.review_output


class ReviewerAgentRuntimeModel(BaseModelClient):
    """BaseModelClient adapter for artifact-only consistency review."""

    def __init__(self, config: PipelineConfig, *, mode: str = "fast") -> None:
        self.config = config
        self.mode = _normalize_mode(mode)
        self.last_result: ReviewerAgentResult | None = None
        self._model: BaseModelClient | None = None

    @property
    def backend_name(self) -> str:
        return f"reviewer_{self.mode}"

    def generate_text(self, prompt: str) -> str:
        result = run_reviewer_agent(
            user_request=_extract_context_section(prompt, "USER REQUEST"),
            product_requirements=_extract_context_section(prompt, "PRODUCT REQUIREMENTS"),
            architecture_plan=_extract_context_section(prompt, "ARCHITECTURE"),
            code_plan=_extract_context_section(prompt, "CODE"),
            test_plan=_extract_context_section(prompt, "TESTS"),
            security_review=_extract_context_section(prompt, "SECURITY REVIEW"),
            mode=self.mode,
            response_generator=self._generate_with_model,
        )
        self.last_result = result
        return result.to_stage_output()

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        prompt = "\n".join(message.get("content", "") for message in messages)
        return self.generate_text(prompt)

    def diagnostics(self) -> dict[str, object]:
        diagnostics: dict[str, object] = {
            "backend_name": self.backend_name,
            "loaded_backend_type": "reviewer_agent_runtime",
            "reviewer_mode": self.mode,
        }
        if self._model is not None:
            diagnostics.update(self._model.diagnostics())
            diagnostics["backend_name"] = self.backend_name
        return diagnostics

    def _generate_with_model(self, *, prompt: str) -> str:
        if self._model is None:
            self._model = _model_for_reviewer_mode(self.config, self.mode)
        return self._model.generate_text(prompt)


def run_reviewer_agent(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
    test_plan: str,
    security_review: str,
    mode: str = "fast",
    output_artifact_path: Path | None = None,
    response_generator: Callable[..., str] | None = None,
) -> ReviewerAgentResult:
    """Run the Reviewer Agent and return parsed output plus validation details."""

    normalized_mode = _normalize_mode(mode)
    prompt = build_reviewer_prompt(
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
        code_plan=code_plan,
        test_plan=test_plan,
        security_review=security_review,
        mode=normalized_mode,
    )
    generator = response_generator or _unsupported_real_generator
    raw_response = generator(prompt=prompt)
    review_output, parsed_sections, warnings, validation_errors = _clean_parse_and_validate(
        raw_response=str(raw_response)
    )
    repair_attempts = 0
    while validation_errors and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS:
        repair_attempts += 1
        repair_prompt = _build_validation_repair_prompt(
            original_prompt=prompt,
            invalid_output=review_output,
            validation_errors=validation_errors,
        )
        raw_response = generator(prompt=repair_prompt)
        review_output, parsed_sections, warnings, validation_errors = _clean_parse_and_validate(
            raw_response=str(raw_response)
        )
        warnings.append("regenerated_after_validation_errors")

    fallback_used = False
    if validation_errors:
        previous_errors = list(validation_errors)
        fallback_used = True
        review_output = _safe_review()
        parsed_sections = parse_reviewer_agent_sections(review_output)
        warnings, validation_errors = validate_reviewer_agent_response(
            review_output=review_output,
            parsed_sections=parsed_sections,
        )
        warnings.append(
            "model_output_replaced_after_validation_errors:"
            + ",".join(previous_errors)
        )

    written_path: str | None = None
    if output_artifact_path is not None:
        output_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output_artifact_path.write_text(review_output.rstrip() + "\n", encoding="utf-8")
        written_path = str(output_artifact_path)
    return ReviewerAgentResult(
        raw_user_request=user_request,
        product_requirements_input=product_requirements,
        architecture_plan_input=architecture_plan,
        code_plan_input=code_plan,
        test_plan_input=test_plan,
        security_review_input=security_review,
        review_output=review_output,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        fallback_used=fallback_used,
        artifact_path=written_path,
    )


def build_reviewer_prompt(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
    test_plan: str,
    security_review: str,
    mode: str,
) -> str:
    """Build the strict Reviewer Agent prompt."""

    return "\n\n".join(
        [
            PROMPT_PATH.read_text(encoding="utf-8").strip(),
            f"REVIEW MODE\n{mode}",
            "RAW USER REQUEST",
            user_request.strip(),
            "PRODUCT AGENT REQUIREMENTS",
            product_requirements.strip(),
            "ARCHITECT AGENT PLAN",
            architecture_plan.strip(),
            "CODE AGENT PLAN",
            code_plan.strip(),
            "TEST ENGINEER PLAN",
            test_plan.strip(),
            "SECURITY AGENT REVIEW",
            security_review.strip(),
            "REVIEWER AGENT OUTPUT",
            "",
        ]
    )


def parse_reviewer_agent_sections(response: str) -> dict[str, list[str] | str]:
    """Split a Reviewer Agent response into normalized named sections."""

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
            sections[key] = "" if key in {"approval_status", "confidence"} else []
            continue
        if current_heading is None:
            continue
        key = SECTION_KEYS[current_heading]
        if key in {"approval_status", "confidence"}:
            sections[key] = _normalize_scalar_value(key, line.lstrip("*- ").strip())
        elif line.startswith(("- ", "* ")):
            values = sections.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return sections


def validate_reviewer_agent_response(
    *,
    review_output: str,
    parsed_sections: dict[str, list[str] | str],
    raw_response: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the Reviewer Agent output contract."""

    warnings: list[str] = []
    errors: list[str] = []
    raw_text = raw_response if raw_response is not None else review_output
    section_counts = _section_counts(review_output)
    for title, key in SECTION_KEYS.items():
        count = section_counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section_{key}")
        elif count > 1:
            errors.append(f"duplicate_section_{key}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section_{key}")

    approval_status = str(parsed_sections.get("approval_status", "")).strip()
    if not approval_status:
        errors.append("approval_status_missing")
    elif approval_status not in APPROVAL_STATUSES:
        errors.append("approval_status_invalid")

    confidence = str(parsed_sections.get("confidence", "")).strip()
    if not confidence:
        errors.append("confidence_missing")
    elif confidence != "High":
        warnings.append("confidence_not_high")

    validation_texts = (raw_text, review_output)
    if re.search(r"</?think\b", review_output, re.IGNORECASE):
        errors.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", review_output):
        errors.append("markdown_headings_present")
    if any("```" in text for text in validation_texts):
        errors.append("code_fence_present")
    if any(PATCH_MARKER_LINE.search(text) for text in validation_texts):
        errors.append("patch_markers_present")

    combined_validation_text = "\n".join(validation_texts)
    for error_name, pattern in FORBIDDEN_CODE_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)
    for error_name, pattern in FORBIDDEN_FIX_OR_COMMAND_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)

    for key in REVIEW_LIST_KEYS:
        value = parsed_sections.get(key)
        if not isinstance(value, list) or not value:
            errors.append(f"empty_section_{key}")

    return warnings, errors



def _strip_think_tags(text: str) -> str:
    """Remove model reasoning tags before artifact validation."""

    cleaned = THINK_BLOCK_PATTERN.sub("", text)
    while True:
        match = THINK_START_PATTERN.search(cleaned)
        if match is None:
            break
        tail = cleaned[match.end() :]
        section_offset = _first_section_offset(tail)
        if section_offset is None:
            cleaned = cleaned[: match.start()]
            break
        cleaned = cleaned[: match.start()] + tail[section_offset:]
    return THINK_TAG_PATTERN.sub("", cleaned)


def _first_section_offset(text: str) -> int | None:
    offset = 0
    for line in text.splitlines(keepends=True):
        if SECTION_LINE.match(line.strip()):
            return offset + len(line) - len(line.lstrip())
        offset += len(line)
    return None


def _has_think_tags(text: str) -> bool:
    return bool(THINK_TAG_PATTERN.search(text))


def clean_reviewer_agent_response(response: str) -> str:
    """Clean model chatter into the artifact-only review contract."""

    cleaned = _strip_think_tags(clean_deepseek_output(_strip_think_tags(response))).strip()
    output_lines: list[str] = []
    current_heading: str | None = None
    skip_scalar = False
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        line = line.replace("`", "")
        stripped = line.strip()
        heading_match = SECTION_LINE.match(stripped)
        if heading_match:
            if current_heading == "APPROVAL STATUS" and (
                _last_nonblank_line(output_lines) not in APPROVAL_STATUSES
            ):
                output_lines.append("Needs Fixes")
            if current_heading == "CONFIDENCE" and (
                _last_nonblank_line(output_lines) != "High"
            ):
                output_lines.append("High")
            current_heading = heading_match.group(1).upper()
            output_lines.append(current_heading)
            skip_scalar = current_heading in {"APPROVAL STATUS", "CONFIDENCE"}
            continue
        if skip_scalar and current_heading == "APPROVAL STATUS":
            output_lines.append(_normalize_approval_status(stripped))
            skip_scalar = False
            continue
        if skip_scalar and current_heading == "CONFIDENCE":
            output_lines.append("High")
            skip_scalar = False
            continue
        numbered_match = NUMBERED_LIST_LINE.match(line)
        if numbered_match:
            line = f"{numbered_match.group(1)}* {numbered_match.group(2)}"
        output_lines.append(line)

    if current_heading == "APPROVAL STATUS" and (
        _last_nonblank_line(output_lines) not in APPROVAL_STATUSES
    ):
        output_lines.append("Needs Fixes")
    if current_heading == "CONFIDENCE" and _last_nonblank_line(output_lines) != "High":
        output_lines.append("High")

    return _normalize_blank_lines(output_lines)


def _clean_parse_and_validate(
    *,
    raw_response: str,
) -> tuple[str, dict[str, list[str] | str], list[str], list[str]]:
    raw_had_think_tags = _has_think_tags(raw_response)
    review_output = clean_reviewer_agent_response(raw_response)
    parsed_sections = parse_reviewer_agent_sections(review_output)
    validation_raw_response = _strip_think_tags(raw_response)
    warnings, validation_errors = validate_reviewer_agent_response(
        review_output=review_output,
        parsed_sections=parsed_sections,
        raw_response=validation_raw_response,
    )
    if raw_had_think_tags and not _has_think_tags(review_output):
        warnings.append("think_tags_removed")
    return review_output, parsed_sections, warnings, validation_errors


def _build_validation_repair_prompt(
    *,
    original_prompt: str,
    invalid_output: str,
    validation_errors: list[str],
) -> str:
    return "\n\n".join(
        [
            original_prompt.strip(),
            "VALIDATION FAILURE",
            "The previous output was invalid and must be regenerated from scratch.",
            "Validation errors: " + ", ".join(validation_errors),
            "Do not repeat the invalid output.",
            "Use only the required sections.",
            "Use bullet lists with asterisks.",
            "Do not output commands, code, patches, diffs, or fixes.",
            "Use APPROVAL STATUS as either Approved or Needs Fixes.",
            "INVALID OUTPUT",
            invalid_output,
            "REGENERATED REVIEWER AGENT OUTPUT",
            "",
        ]
    )


def _safe_review() -> str:
    return "\n".join(
        [
            "CONSISTENCY CHECK",
            "* Review could not be completed with sufficient confidence.",
            "",
            "REQUIREMENT GAPS",
            "* Manual review required.",
            "",
            "ARCHITECTURE GAPS",
            "* Manual review required.",
            "",
            "IMPLEMENTATION RISKS",
            "* Manual review required.",
            "",
            "TEST COVERAGE GAPS",
            "* Manual review required.",
            "",
            "SECURITY GAPS",
            "* Manual review required.",
            "",
            "RECOMMENDATIONS",
            "* Run reviewer again.",
            "",
            "APPROVAL STATUS",
            "Needs Fixes",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _model_for_reviewer_mode(config: PipelineConfig, mode: str) -> BaseModelClient:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "deep":
        deep_config = _reviewer_deep_config(config)
        if deep_config.deepseek_gguf_path is not None:
            return DeepSeekGGUFModel(deep_config)
        return DeepSeekUnslothModel(deep_config)
    return Qwen3Model(_reviewer_fast_config(config))


def _reviewer_fast_config(config: PipelineConfig) -> PipelineConfig:
    fast_model = config.reviewer_fast_model
    if fast_model.suffix.lower() == ".gguf":
        return replace(config, qwen3_gguf_path=fast_model)
    return replace(config, qwen3_base_model=str(fast_model), qwen3_gguf_path=None)


def _reviewer_deep_config(config: PipelineConfig) -> PipelineConfig:
    deep_model = config.reviewer_deep_model
    if deep_model.suffix.lower() == ".gguf":
        return replace(config, deepseek_gguf_path=deep_model)
    return replace(config, deepseek_gguf_path=None, deepseek_unsloth_model=deep_model)


def _normalize_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Reviewer Agent mode: {mode}")
    return "fast" if normalized == "auto" else normalized


def _normalize_scalar_value(key: str, value: str) -> str:
    if key == "approval_status":
        return _normalize_approval_status(value)
    if key == "confidence":
        return "High" if value else ""
    return value


def _normalize_approval_status(value: str) -> str:
    normalized = value.strip().lower().replace(":", "")
    if normalized in {"approved", "approve", "status approved"}:
        return "Approved"
    if normalized in {
        "needs fixes",
        "needs fix",
        "changes required",
        "requires fixes",
        "not approved",
    }:
        return "Needs Fixes"
    return value.strip() or "Needs Fixes"


def _section_counts(response: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTION_TITLES}
    for line in response.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _normalize_blank_lines(lines: list[str]) -> str:
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        stripped = line.rstrip()
        is_blank = not stripped
        if is_blank and previous_blank:
            continue
        normalized.append(stripped)
        previous_blank = is_blank
    return "\n".join(normalized).strip()


def _last_nonblank_line(lines: list[str]) -> str:
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _extract_context_section(prompt: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(title)}\n=+\n(?P<body>.*?)(?=\n\n[A-Z][A-Z /-]+\n=+\n|\Z)"
    )
    match = pattern.search(prompt)
    return match.group("body").strip() if match else ""


def _unsupported_real_generator(*, prompt: str) -> str:
    raise RuntimeError(
        "No Reviewer Agent response generator was provided. Use ReviewerAgentRuntimeModel "
        "for real pipeline execution or pass a fake response_generator for smoke tests."
    )
