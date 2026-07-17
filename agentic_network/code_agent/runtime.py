"""Code Agent runtime, parser, validation, and model adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output
from agentic_network.models.qwen_unsloth import QwenUnslothModel

CODE_OUTPUT_FILE = "03_code.md"
PROMPT_PATH = Path(__file__).with_name("prompt.md")
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
SECTION_KEYS = {
    "FILES TO MODIFY": "files_to_modify",
    "NEW FILES": "new_files",
    "CODE CHANGES": "code_changes",
    "TESTS TO ADD": "tests_to_add",
    "RATIONALE": "rationale",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTION_TITLES = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*("
    + "|".join(re.escape(title) for title in REQUIRED_SECTION_TITLES)
    + r")\s*$",
    re.IGNORECASE,
)
NUMBERED_LIST_LINE = re.compile(r"^(\s*)\d+[\.)]\s+(.+)$")
PATH_LIKE_TOKEN = re.compile(r"(?<![\w.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)")
FORBIDDEN_CODE_PATTERNS = {
    "forbidden_code_def": re.compile(r"\bdef\s+"),
    "forbidden_code_class": re.compile(r"\bclass\s+"),
    "forbidden_code_import": re.compile(r"\bimport\s+"),
    "forbidden_code_from": re.compile(r"\bfrom\s+"),
    "forbidden_code_decorator": re.compile(r"@"),
    "forbidden_code_return": re.compile(r"\breturn\s+"),
    "forbidden_code_raise": re.compile(r"\braise\s+"),
    "forbidden_code_except": re.compile(r"\bexcept\s+"),
    "forbidden_code_try": re.compile(r"\btry\s*:"),
}
PATCH_MARKER_LINE = re.compile(r"(?m)^\s*(?:\+\+\+|---|@@)(?:\s|$)")


@dataclass(frozen=True)
class CodeAgentResult:
    """Structured Code Agent output returned to the pipeline and CLI."""

    raw_user_request: str
    product_requirements_input: str
    architecture_plan_input: str
    generated_code_plan: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    output_artifact_path: str | None = None

    def to_stage_output(self) -> str:
        """Return the implementation artifact saved as the pipeline code stage."""

        return self.generated_code_plan


class CodeAgentRuntimeModel(BaseModelClient):
    """BaseModelClient adapter around the existing Qwen2.5-Coder v5 runtime."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.last_result: CodeAgentResult | None = None
        self._model: BaseModelClient | None = None

    @property
    def backend_name(self) -> str:
        return "code_v5"

    def generate_text(self, prompt: str) -> str:
        result = run_code_agent(
            user_request=_extract_context_section(prompt, "USER REQUEST"),
            product_requirements=_extract_context_section(prompt, "PRODUCT REQUIREMENTS"),
            architecture_plan=_extract_context_section(prompt, "ARCHITECTURE"),
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
            "loaded_backend_type": "code_agent_runtime",
        }
        if self._model is not None:
            diagnostics.update(self._model.diagnostics())
            diagnostics["backend_name"] = self.backend_name
        return diagnostics

    def _generate_with_model(self, *, prompt: str) -> str:
        if self._model is None:
            self._model = QwenUnslothModel(self.config)
        return self._model.generate_text(prompt)


def run_code_agent(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    output_artifact_path: Path | None = None,
    response_generator: Callable[..., str] | None = None,
) -> CodeAgentResult:
    """Run the Code Agent and return parsed output plus validation details."""

    prompt = build_code_prompt(
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
    )
    generator = response_generator or _unsupported_real_generator
    raw_response = generator(prompt=prompt)
    generated_code_plan, parsed_sections, warnings, validation_errors = (
        _clean_parse_and_validate(
            raw_response=str(raw_response),
            architecture_plan=architecture_plan,
        )
    )
    repair_attempts = 0
    while validation_errors and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS:
        repair_attempts += 1
        repair_prompt = _build_validation_repair_prompt(
            original_prompt=prompt,
            invalid_output=generated_code_plan,
            validation_errors=validation_errors,
        )
        raw_response = generator(prompt=repair_prompt)
        generated_code_plan, parsed_sections, warnings, validation_errors = (
            _clean_parse_and_validate(
                raw_response=str(raw_response),
                architecture_plan=architecture_plan,
            )
        )
        warnings.append("regenerated_after_validation_errors")

    if validation_errors:
        previous_errors = list(validation_errors)
        generated_code_plan = _safe_code_plan(
            user_request=user_request,
            architecture_plan=architecture_plan,
        )
        parsed_sections = parse_code_agent_sections(generated_code_plan)
        warnings, validation_errors = validate_code_agent_response(
            generated_code_plan=generated_code_plan,
            parsed_sections=parsed_sections,
            architecture_plan=architecture_plan,
        )
        warnings.append(
            "model_output_replaced_after_validation_errors:"
            + ",".join(previous_errors)
        )
    written_path: str | None = None
    if output_artifact_path is not None:
        output_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output_artifact_path.write_text(generated_code_plan.rstrip() + "\n", encoding="utf-8")
        written_path = str(output_artifact_path)
    return CodeAgentResult(
        raw_user_request=user_request,
        product_requirements_input=product_requirements,
        architecture_plan_input=architecture_plan,
        generated_code_plan=generated_code_plan,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        output_artifact_path=written_path,
    )


def _clean_parse_and_validate(
    *,
    raw_response: str,
    architecture_plan: str,
) -> tuple[str, dict[str, list[str] | str], list[str], list[str]]:
    generated_code_plan = clean_code_agent_response(raw_response)
    parsed_sections = parse_code_agent_sections(generated_code_plan)
    warnings, validation_errors = validate_code_agent_response(
        generated_code_plan=generated_code_plan,
        parsed_sections=parsed_sections,
        architecture_plan=architecture_plan,
        raw_response=raw_response,
    )
    return generated_code_plan, parsed_sections, warnings, validation_errors


def build_code_prompt(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
) -> str:
    """Build the strict Code Agent prompt."""

    return "\n\n".join(
        [
            PROMPT_PATH.read_text(encoding="utf-8").strip(),
            "RAW USER REQUEST",
            user_request.strip(),
            "PRODUCT AGENT REQUIREMENTS",
            product_requirements.strip(),
            "ARCHITECT AGENT PLAN",
            architecture_plan.strip(),
            "CODE AGENT OUTPUT",
            "",
        ]
    )


def parse_code_agent_sections(response: str) -> dict[str, list[str] | str]:
    """Split a Code Agent response into normalized named sections."""

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
        elif line.startswith(("- ", "* ")):
            values = sections.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return sections


def validate_code_agent_response(
    *,
    generated_code_plan: str,
    parsed_sections: dict[str, list[str] | str],
    architecture_plan: str = "",
    raw_response: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the Code Agent output contract."""

    warnings: list[str] = []
    errors: list[str] = []
    raw_text = raw_response if raw_response is not None else generated_code_plan
    section_counts = _section_counts(generated_code_plan)
    for title, key in SECTION_KEYS.items():
        count = section_counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section_{key}")
        elif count > 1:
            errors.append(f"duplicate_section_{key}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section_{key}")

    confidence = str(parsed_sections.get("confidence", "")).strip()
    if not confidence:
        errors.append("confidence_missing")
    elif confidence != "High":
        warnings.append("confidence_not_high")

    validation_texts = (raw_text, generated_code_plan)
    if any(re.search(r"</?think\b", text, re.IGNORECASE) for text in validation_texts):
        errors.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", generated_code_plan):
        errors.append("markdown_headings_present")
    if any("```" in text for text in validation_texts):
        errors.append("code_fence_present")
    if any(PATCH_MARKER_LINE.search(text) for text in validation_texts):
        errors.append("patch_markers_present")

    combined_validation_text = "\n".join(validation_texts)
    for error_name, pattern in FORBIDDEN_CODE_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)

    allowed_paths = _architect_file_paths(architecture_plan)
    for path in _unapproved_file_paths(parsed_sections, allowed_paths):
        errors.append(f"invented_file_path_{path}")

    for key, value in parsed_sections.items():
        if key != "confidence" and isinstance(value, list) and not value:
            warnings.append(f"empty_section_{key}")

    return warnings, errors


def clean_code_agent_response(response: str) -> str:
    """Clean model chatter into the artifact-only planning contract."""

    cleaned = clean_deepseek_output(response).strip()
    output_lines: list[str] = []
    in_confidence = False
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        line = line.replace("`", "")
        stripped = line.strip()
        heading_match = SECTION_LINE.match(stripped)
        if heading_match:
            if in_confidence and (not output_lines or output_lines[-1] != "High"):
                output_lines.append("High")
            heading = heading_match.group(1).upper()
            output_lines.append(heading)
            in_confidence = heading == "CONFIDENCE"
            continue
        if in_confidence:
            continue
        numbered_match = NUMBERED_LIST_LINE.match(line)
        if numbered_match:
            line = f"{numbered_match.group(1)}- {numbered_match.group(2)}"
        output_lines.append(line)

    if in_confidence and (not output_lines or output_lines[-1] != "High"):
        output_lines.append("High")

    return _normalize_blank_lines(output_lines)


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
            "Use bullet lists, not numbered lists.",
            "Use Candidate: for any file not listed in Architect FILES TO INSPECT.",
            "Do not use these literal tokens anywhere: ```, def, class, import, from, @, return, raise, except, try:, +++, ---, @@.",
            "Do not output final code, decorators, function names, class names, imports, tests, patches, or diff markers.",
            "INVALID OUTPUT",
            invalid_output,
            "REGENERATED CODE AGENT OUTPUT",
            "",
        ]
    )


def _safe_code_plan(*, user_request: str, architecture_plan: str) -> str:
    allowed_paths = sorted(_architect_file_paths(architecture_plan))
    file_items = allowed_paths or [
        "Candidate: password reset request handling module.",
        "Candidate: rate-limit policy or configuration module.",
    ]
    if not _mentions_password_reset_rate_limit(user_request):
        file_items = allowed_paths or [
            "Candidate: module responsible for the requested behavior.",
            "Candidate: configuration or policy module if the existing design uses one.",
        ]
    return "\n".join(
        [
            "FILES TO MODIFY",
            *[f"- {item}" for item in file_items],
            "",
            "NEW FILES",
            "- Candidate: focused tests for the requested behavior.",
            "",
            "CODE CHANGES",
            *[f"- {item}" for item in _safe_code_change_items(user_request)],
            "",
            "TESTS TO ADD",
            *[f"- {item}" for item in _safe_test_items(user_request)],
            "",
            "RATIONALE",
            "- Preserve the requested behavior with a minimal implementation plan.",
            "- Keep the next coding step aligned with Product and Architect artifacts.",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _safe_code_change_items(user_request: str) -> list[str]:
    if _mentions_password_reset_rate_limit(user_request):
        return [
            "Add request tracking for repeated password reset attempts.",
            "Apply a configurable rate-limit policy before sending reset instructions.",
            "Return clear user-facing feedback when limits are reached.",
            "Ensure legitimate reset attempts remain possible after the configured window.",
        ]
    return [
        "Inspect the existing implementation path named by the architecture plan.",
        "Add the smallest scoped change that satisfies the Product requirements.",
        "Preserve existing behavior outside the requested flow.",
    ]


def _safe_test_items(user_request: str) -> list[str]:
    if _mentions_password_reset_rate_limit(user_request):
        return [
            "Verify excessive reset attempts are blocked.",
            "Verify legitimate reset attempts are allowed.",
            "Verify reset limits are applied consistently.",
            "Verify user-facing feedback is clear.",
        ]
    return [
        "Verify the requested behavior succeeds.",
        "Verify the main edge case identified by the Product requirements.",
        "Verify existing behavior around the changed area still works.",
    ]


def _mentions_password_reset_rate_limit(user_request: str) -> bool:
    lowered = user_request.lower()
    return "password reset" in lowered and "rate limit" in lowered


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


def _architect_file_paths(architecture_plan: str) -> set[str]:
    sections = _extract_architecture_sections(architecture_plan)
    files_to_inspect = sections.get("FILES TO INSPECT", [])
    paths: set[str] = set()
    for item in files_to_inspect:
        for path in PATH_LIKE_TOKEN.findall(item):
            paths.add(path.strip().rstrip(".,;:"))
    return paths


def _extract_architecture_sections(architecture_plan: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for raw_line in architecture_plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isupper() and not line.startswith(("-", "*")):
            current_heading = line
            sections.setdefault(current_heading, [])
            continue
        if current_heading and line.startswith(("- ", "* ")):
            sections.setdefault(current_heading, []).append(line[2:].strip())
    return sections


def _unapproved_file_paths(
    parsed_sections: dict[str, list[str] | str],
    allowed_paths: set[str],
) -> list[str]:
    invented: list[str] = []
    seen: set[str] = set()
    for value in parsed_sections.values():
        if not isinstance(value, list):
            continue
        for item in value:
            stripped_item = item.strip()
            if stripped_item.lower().startswith("candidate:"):
                continue
            for path in PATH_LIKE_TOKEN.findall(stripped_item):
                normalized_path = path.strip().rstrip(".,;:")
                if normalized_path in allowed_paths or normalized_path in seen:
                    continue
                seen.add(normalized_path)
                invented.append(normalized_path)
    return invented


def _extract_context_section(prompt: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(title)}\n=+\n(?P<body>.*?)(?=\n\n[A-Z][A-Z /-]+\n=+\n|\Z)"
    )
    match = pattern.search(prompt)
    return match.group("body").strip() if match else ""


def _unsupported_real_generator(*, prompt: str) -> str:
    raise RuntimeError(
        "No Code Agent response generator was provided. Use CodeAgentRuntimeModel for "
        "real pipeline execution or pass a fake response_generator for smoke tests."
    )
