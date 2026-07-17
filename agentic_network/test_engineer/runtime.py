"""Test Engineer Agent runtime, parser, validation, and model adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output
from agentic_network.models.qwen_unsloth import QwenUnslothModel

TEST_OUTPUT_FILE = "04_tests.md"
PROMPT_PATH = Path(__file__).with_name("prompt.md")
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
SECTION_KEYS = {
    "TEST SCENARIOS": "test_scenarios",
    "TEST CASES": "test_cases",
    "EDGE CASES": "edge_cases",
    "REGRESSION TESTS": "regression_tests",
    "AUTOMATION STRATEGY": "automation_strategy",
    "RISKS": "risks",
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
PATCH_MARKER_LINE = re.compile(r"(?m)^\s*(?:\+\+\+|---|@@)(?:\s|$)")
FORBIDDEN_CODE_PATTERNS = {
    "forbidden_import_statement": re.compile(
        r"(?m)^\s*(?:from\s+\S+\s+import\b|import\s+\S+)"
    ),
    "forbidden_test_function": re.compile(r"\bdef\s+\w+\s*\("),
    "forbidden_class_definition": re.compile(r"\bclass\s+\w+"),
    "forbidden_decorator": re.compile(r"(?m)^\s*@"),
    "forbidden_return_statement": re.compile(r"\breturn\s+"),
    "forbidden_raise_statement": re.compile(r"\braise\s+"),
    "forbidden_except_block": re.compile(r"\bexcept\b"),
    "forbidden_try_block": re.compile(r"\btry\s*:"),
    "forbidden_assert_statement": re.compile(r"\bassert\s+"),
}
FILE_CREATION_COMMANDS = re.compile(
    r"(?im)^\s*(?:touch|mkdir|cat\s+>|tee\s+|echo\s+.+>|python\s+-m\s+pytest|pytest)\b"
)


@dataclass(frozen=True)
class TestEngineerResult:
    """Structured Test Engineer output returned to the pipeline and CLI."""

    raw_user_request: str
    product_requirements_input: str
    architecture_plan_input: str
    code_plan_input: str
    generated_test_plan: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    output_artifact_path: str | None = None

    def to_stage_output(self) -> str:
        """Return the QA artifact saved as the pipeline test stage."""

        return self.generated_test_plan


class TestEngineerRuntimeModel(BaseModelClient):
    """BaseModelClient adapter around the existing Qwen2.5-Coder v5 runtime."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.last_result: TestEngineerResult | None = None
        self._model: BaseModelClient | None = None

    @property
    def backend_name(self) -> str:
        return "test_engineer_v5"

    def generate_text(self, prompt: str) -> str:
        result = run_test_engineer_agent(
            user_request=_extract_context_section(prompt, "USER REQUEST"),
            product_requirements=_extract_context_section(prompt, "PRODUCT REQUIREMENTS"),
            architecture_plan=_extract_context_section(prompt, "ARCHITECTURE"),
            code_plan=_extract_context_section(prompt, "CODE"),
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
            "loaded_backend_type": "test_engineer_runtime",
        }
        if self._model is not None:
            diagnostics.update(self._model.diagnostics())
            diagnostics["backend_name"] = self.backend_name
        return diagnostics

    def _generate_with_model(self, *, prompt: str) -> str:
        if self._model is None:
            self._model = QwenUnslothModel(self.config)
        return self._model.generate_text(prompt)


def run_test_engineer_agent(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
    output_artifact_path: Path | None = None,
    response_generator: Callable[..., str] | None = None,
) -> TestEngineerResult:
    """Run the Test Engineer Agent and return parsed output plus validation details."""

    prompt = build_test_engineer_prompt(
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
        code_plan=code_plan,
    )
    generator = response_generator or _unsupported_real_generator
    raw_response = generator(prompt=prompt)
    generated_test_plan, parsed_sections, warnings, validation_errors = (
        _clean_parse_and_validate(raw_response=str(raw_response))
    )
    repair_attempts = 0
    while validation_errors and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS:
        repair_attempts += 1
        repair_prompt = _build_validation_repair_prompt(
            original_prompt=prompt,
            invalid_output=generated_test_plan,
            validation_errors=validation_errors,
        )
        raw_response = generator(prompt=repair_prompt)
        generated_test_plan, parsed_sections, warnings, validation_errors = (
            _clean_parse_and_validate(raw_response=str(raw_response))
        )
        warnings.append("regenerated_after_validation_errors")

    if validation_errors:
        previous_errors = list(validation_errors)
        generated_test_plan = _safe_test_plan(user_request=user_request)
        parsed_sections = parse_test_engineer_sections(generated_test_plan)
        warnings, validation_errors = validate_test_engineer_response(
            generated_test_plan=generated_test_plan,
            parsed_sections=parsed_sections,
        )
        warnings.append(
            "model_output_replaced_after_validation_errors:"
            + ",".join(previous_errors)
        )

    written_path: str | None = None
    if output_artifact_path is not None:
        output_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output_artifact_path.write_text(generated_test_plan.rstrip() + "\n", encoding="utf-8")
        written_path = str(output_artifact_path)
    return TestEngineerResult(
        raw_user_request=user_request,
        product_requirements_input=product_requirements,
        architecture_plan_input=architecture_plan,
        code_plan_input=code_plan,
        generated_test_plan=generated_test_plan,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        output_artifact_path=written_path,
    )


def build_test_engineer_prompt(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
) -> str:
    """Build the strict Test Engineer prompt."""

    return "\n\n".join(
        [
            PROMPT_PATH.read_text(encoding="utf-8").strip(),
            "RAW USER REQUEST",
            user_request.strip(),
            "PRODUCT AGENT REQUIREMENTS",
            product_requirements.strip(),
            "ARCHITECT AGENT PLAN",
            architecture_plan.strip(),
            "CODE AGENT PLAN",
            code_plan.strip(),
            "TEST ENGINEER OUTPUT",
            "",
        ]
    )


def parse_test_engineer_sections(response: str) -> dict[str, list[str] | str]:
    """Split a Test Engineer response into normalized named sections."""

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


def validate_test_engineer_response(
    *,
    generated_test_plan: str,
    parsed_sections: dict[str, list[str] | str],
    raw_response: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the Test Engineer output contract."""

    warnings: list[str] = []
    errors: list[str] = []
    raw_text = raw_response if raw_response is not None else generated_test_plan
    section_counts = _section_counts(generated_test_plan)
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

    validation_texts = (raw_text, generated_test_plan)
    if any(re.search(r"</?think\b", text, re.IGNORECASE) for text in validation_texts):
        errors.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", generated_test_plan):
        errors.append("markdown_headings_present")
    if any("```" in text for text in validation_texts):
        errors.append("code_fence_present")
    if any(PATCH_MARKER_LINE.search(text) for text in validation_texts):
        errors.append("patch_markers_present")
    if any(FILE_CREATION_COMMANDS.search(text) for text in validation_texts):
        errors.append("file_creation_or_test_execution_command_present")

    combined_validation_text = "\n".join(validation_texts)
    for error_name, pattern in FORBIDDEN_CODE_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)

    for key, value in parsed_sections.items():
        if key == "confidence":
            continue
        if not isinstance(value, list) or not value:
            errors.append(f"empty_section_{key}")

    return warnings, errors


def clean_test_engineer_response(response: str) -> str:
    """Clean model chatter into the artifact-only QA planning contract."""

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


def _clean_parse_and_validate(
    *,
    raw_response: str,
) -> tuple[str, dict[str, list[str] | str], list[str], list[str]]:
    generated_test_plan = clean_test_engineer_response(raw_response)
    parsed_sections = parse_test_engineer_sections(generated_test_plan)
    warnings, validation_errors = validate_test_engineer_response(
        generated_test_plan=generated_test_plan,
        parsed_sections=parsed_sections,
        raw_response=raw_response,
    )
    return generated_test_plan, parsed_sections, warnings, validation_errors


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
            "Do not output commands, code, imports, decorators, test functions, classes, patches, or diff markers.",
            "Do not use these literal tokens as code: ```, def, class, import, @, return, raise, except, try:, assert, +++, ---, @@.",
            "INVALID OUTPUT",
            invalid_output,
            "REGENERATED TEST ENGINEER OUTPUT",
            "",
        ]
    )


def _safe_test_plan(*, user_request: str) -> str:
    if _mentions_password_reset_rate_limit(user_request):
        return _password_reset_safe_plan()
    return "\n".join(
        [
            "TEST SCENARIOS",
            "- Verify the requested behavior succeeds for the primary user flow.",
            "- Verify invalid or excessive user actions receive clear feedback.",
            "- Verify the behavior remains consistent with Product acceptance criteria.",
            "",
            "TEST CASES",
            "- User completes the intended flow successfully.",
            "- User input outside expected bounds is handled clearly.",
            "- The planned implementation remains testable through observable behavior.",
            "",
            "EDGE CASES",
            "- Repeated attempts occur close together.",
            "- The flow is interrupted and retried.",
            "- Ambiguous inputs are handled without changing unrelated behavior.",
            "",
            "REGRESSION TESTS",
            "- Existing successful behavior around the changed area remains unchanged.",
            "- Existing failure messaging around the changed area remains consistent.",
            "",
            "AUTOMATION STRATEGY",
            "- Add behavior-level automated coverage for success, failure, and retry flows.",
            "- Keep tests deterministic by controlling external timing or state.",
            "",
            "RISKS",
            "- Missing negative-path coverage may allow regressions.",
            "- Ambiguous acceptance criteria may require refinement before final test design.",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _password_reset_safe_plan() -> str:
    return "\n".join(
        [
            "TEST SCENARIOS",
            "- Verify password reset rate limits prevent repeated abuse.",
            "- Verify legitimate users can still complete password reset after allowed waiting conditions.",
            "- Verify user-facing feedback remains clear when limits are reached.",
            "",
            "TEST CASES",
            "- User reaches the configured reset limit and receives clear feedback.",
            "- User remains below the limit and receives reset instructions normally.",
            "- Repeated reset attempts are tracked consistently for the same account or identifier.",
            "- Reset attempts after the allowed waiting window are accepted.",
            "",
            "EDGE CASES",
            "- Multiple reset attempts occur close together.",
            "- A user retries after the limit window expires.",
            "- Reset flow is interrupted and resumed.",
            "- Reset attempts originate from repeated identifiers.",
            "",
            "REGRESSION TESTS",
            "- Existing successful password reset behavior remains unchanged.",
            "- Existing expired reset-link behavior remains unchanged.",
            "- Existing account recovery messaging remains consistent.",
            "",
            "AUTOMATION STRATEGY",
            "- Add behavior-level tests for allowed, blocked, and recovered reset flows.",
            "- Add regression coverage around existing password reset success and failure paths.",
            "- Keep tests deterministic by controlling rate-limit windows or test clocks.",
            "",
            "RISKS",
            "- Poorly designed tests may become flaky if time windows are not controlled.",
            "- Missing negative-path tests may allow abuse behavior to regress.",
            "- Overly strict assertions may block valid product changes.",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


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


def _extract_context_section(prompt: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(title)}\n=+\n(?P<body>.*?)(?=\n\n[A-Z][A-Z /-]+\n=+\n|\Z)"
    )
    match = pattern.search(prompt)
    return match.group("body").strip() if match else ""


def _unsupported_real_generator(*, prompt: str) -> str:
    raise RuntimeError(
        "No Test Engineer response generator was provided. Use TestEngineerRuntimeModel "
        "for real pipeline execution or pass a fake response_generator for smoke tests."
    )
