"""Security Agent runtime, parser, validation, and model adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import DeepSeekGGUFModel, clean_deepseek_output
from agentic_network.models.deepseek_unsloth import DeepSeekUnslothModel
from agentic_network.models.qwen3 import Qwen3Model

SECURITY_OUTPUT_FILE = "05_security.md"
PROMPT_PATH = Path(__file__).with_name("prompt.md")
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
SECTION_KEYS = {
    "SECURITY FINDINGS": "security_findings",
    "THREATS": "threats",
    "ABUSE SCENARIOS": "abuse_scenarios",
    "SECURITY TESTS": "security_tests",
    "MITIGATIONS": "mitigations",
    "RESIDUAL RISKS": "residual_risks",
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
    "forbidden_function_definition": re.compile(r"\bdef\s+\w+\s*\("),
    "forbidden_class_definition": re.compile(r"\bclass\s+\w+"),
    "forbidden_decorator": re.compile(r"(?m)^\s*@"),
    "forbidden_return_statement": re.compile(r"\breturn\s+"),
    "forbidden_raise_statement": re.compile(r"\braise\s+"),
    "forbidden_except_block": re.compile(r"\bexcept\b"),
    "forbidden_try_block": re.compile(r"\btry\s*:"),
}
FORBIDDEN_COMMANDS = re.compile(
    r"(?im)^\s*(?:touch|mkdir|cat\s+>|tee\s+|echo\s+.+>|python\s+-m\s+|pytest|"
    r"nmap|sqlmap|nikto|zap|hydra|john|hashcat|metasploit|msfconsole|curl\s+|wget\s+)\b"
)
EXPLOIT_PAYLOAD_PATTERNS = {
    "exploit_payload_script_tag": re.compile(r"(?i)<\s*script\b"),
    "exploit_payload_javascript_uri": re.compile(r"(?i)javascript\s*:"),
    "exploit_payload_sql_union": re.compile(r"(?i)\bunion\s+select\b"),
    "exploit_payload_sql_tautology": re.compile(r"(?i)\bor\s+1\s*=\s*1\b"),
    "exploit_payload_path_traversal": re.compile(r"\.\./"),
    "exploit_payload_reverse_shell": re.compile(r"(?i)\b(?:bash\s+-i|nc\s+-e|/dev/tcp)\b"),
}
STEP_BY_STEP_ATTACK = re.compile(
    r"(?i)\b(?:step\s+\d+|first\s*,?\s+.*\bthen\b|then\s+(?:send|run|execute)|"
    r"use\s+(?:sqlmap|nmap|hydra|metasploit|msfconsole)\b)"
)
INVENTED_CVE = re.compile(r"\bCVE-\d{4}-\d{4,}\b")


@dataclass(frozen=True)
class SecurityAgentResult:
    """Structured Security Agent output returned to the pipeline and CLI."""

    raw_user_request: str
    product_requirements_input: str
    architecture_plan_input: str
    code_plan_input: str
    test_plan_input: str
    generated_security_review: str
    parsed_sections: dict[str, list[str] | str]
    warnings: list[str]
    validation_errors: list[str]
    fallback_used: bool
    output_artifact_path: str | None = None

    def to_stage_output(self) -> str:
        """Return the security artifact saved as the pipeline security stage."""

        return self.generated_security_review


class SecurityAgentRuntimeModel(BaseModelClient):
    """BaseModelClient adapter for artifact-only security review generation."""

    def __init__(self, config: PipelineConfig, *, mode: str = "fast") -> None:
        self.config = config
        self.mode = _normalize_mode(mode)
        self.last_result: SecurityAgentResult | None = None
        self._model: BaseModelClient | None = None

    @property
    def backend_name(self) -> str:
        return f"security_{self.mode}"

    def generate_text(self, prompt: str) -> str:
        result = run_security_agent(
            user_request=_extract_context_section(prompt, "USER REQUEST"),
            product_requirements=_extract_context_section(prompt, "PRODUCT REQUIREMENTS"),
            architecture_plan=_extract_context_section(prompt, "ARCHITECTURE"),
            code_plan=_extract_context_section(prompt, "CODE"),
            test_plan=_extract_context_section(prompt, "TESTS"),
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
            "loaded_backend_type": "security_agent_runtime",
            "security_mode": self.mode,
        }
        if self._model is not None:
            diagnostics.update(self._model.diagnostics())
            diagnostics["backend_name"] = self.backend_name
        return diagnostics

    def _generate_with_model(self, *, prompt: str) -> str:
        if self._model is None:
            self._model = _model_for_security_mode(self.config, self.mode)
        return self._model.generate_text(prompt)


def run_security_agent(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
    test_plan: str,
    mode: str = "fast",
    output_artifact_path: Path | None = None,
    response_generator: Callable[..., str] | None = None,
) -> SecurityAgentResult:
    """Run the Security Agent and return parsed output plus validation details."""

    normalized_mode = _normalize_mode(mode)
    prompt = build_security_prompt(
        user_request=user_request,
        product_requirements=product_requirements,
        architecture_plan=architecture_plan,
        code_plan=code_plan,
        test_plan=test_plan,
        mode=normalized_mode,
    )
    generator = response_generator or _unsupported_real_generator
    raw_response = generator(prompt=prompt)
    generated_review, parsed_sections, warnings, validation_errors = _clean_parse_and_validate(
        raw_response=str(raw_response)
    )
    repair_attempts = 0
    while validation_errors and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS:
        repair_attempts += 1
        repair_prompt = _build_validation_repair_prompt(
            original_prompt=prompt,
            invalid_output=generated_review,
            validation_errors=validation_errors,
        )
        raw_response = generator(prompt=repair_prompt)
        generated_review, parsed_sections, warnings, validation_errors = (
            _clean_parse_and_validate(raw_response=str(raw_response))
        )
        warnings.append("regenerated_after_validation_errors")

    fallback_used = False
    if validation_errors:
        previous_errors = list(validation_errors)
        fallback_used = True
        generated_review = _safe_security_review(user_request=user_request)
        parsed_sections = parse_security_agent_sections(generated_review)
        warnings, validation_errors = validate_security_agent_response(
            generated_security_review=generated_review,
            parsed_sections=parsed_sections,
        )
        warnings.append(
            "model_output_replaced_after_validation_errors:"
            + ",".join(previous_errors)
        )

    written_path: str | None = None
    if output_artifact_path is not None:
        output_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output_artifact_path.write_text(generated_review.rstrip() + "\n", encoding="utf-8")
        written_path = str(output_artifact_path)
    return SecurityAgentResult(
        raw_user_request=user_request,
        product_requirements_input=product_requirements,
        architecture_plan_input=architecture_plan,
        code_plan_input=code_plan,
        test_plan_input=test_plan,
        generated_security_review=generated_review,
        parsed_sections=parsed_sections,
        warnings=warnings,
        validation_errors=validation_errors,
        fallback_used=fallback_used,
        output_artifact_path=written_path,
    )


def build_security_prompt(
    *,
    user_request: str,
    product_requirements: str,
    architecture_plan: str,
    code_plan: str,
    test_plan: str,
    mode: str,
) -> str:
    """Build the strict Security Agent prompt."""

    return "\n\n".join(
        [
            PROMPT_PATH.read_text(encoding="utf-8").strip(),
            f"SECURITY REVIEW MODE\n{mode}",
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
            "SECURITY AGENT OUTPUT",
            "",
        ]
    )


def parse_security_agent_sections(response: str) -> dict[str, list[str] | str]:
    """Split a Security Agent response into normalized named sections."""

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


def validate_security_agent_response(
    *,
    generated_security_review: str,
    parsed_sections: dict[str, list[str] | str],
    raw_response: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the Security Agent output contract."""

    warnings: list[str] = []
    errors: list[str] = []
    raw_text = raw_response if raw_response is not None else generated_security_review
    section_counts = _section_counts(generated_security_review)
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

    validation_texts = (raw_text, generated_security_review)
    if any(re.search(r"</?think\b", text, re.IGNORECASE) for text in validation_texts):
        errors.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", generated_security_review):
        errors.append("markdown_headings_present")
    if any("```" in text for text in validation_texts):
        errors.append("code_fence_present")
    if any(PATCH_MARKER_LINE.search(text) for text in validation_texts):
        errors.append("patch_markers_present")
    if any(FORBIDDEN_COMMANDS.search(text) for text in validation_texts):
        errors.append("forbidden_security_or_file_command_present")
    if any(STEP_BY_STEP_ATTACK.search(text) for text in validation_texts):
        errors.append("step_by_step_attack_instructions_present")
    if any(INVENTED_CVE.search(text) for text in validation_texts):
        errors.append("invented_cve_id_present")

    combined_validation_text = "\n".join(validation_texts)
    for error_name, pattern in FORBIDDEN_CODE_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)
    for error_name, pattern in EXPLOIT_PAYLOAD_PATTERNS.items():
        if pattern.search(combined_validation_text):
            errors.append(error_name)

    for key, value in parsed_sections.items():
        if key == "confidence":
            continue
        if not isinstance(value, list) or not value:
            errors.append(f"empty_section_{key}")

    return warnings, errors


def clean_security_agent_response(response: str) -> str:
    """Clean model chatter into the artifact-only security review contract."""

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
    generated_review = clean_security_agent_response(raw_response)
    parsed_sections = parse_security_agent_sections(generated_review)
    warnings, validation_errors = validate_security_agent_response(
        generated_security_review=generated_review,
        parsed_sections=parsed_sections,
        raw_response=raw_response,
    )
    return generated_review, parsed_sections, warnings, validation_errors


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
            "Do not output commands, code, imports, payloads, scanners, CVE IDs, attack procedures, patches, or diff markers.",
            "Keep abuse scenarios high-level and defensive.",
            "INVALID OUTPUT",
            invalid_output,
            "REGENERATED SECURITY AGENT OUTPUT",
            "",
        ]
    )


def _safe_security_review(*, user_request: str) -> str:
    if _mentions_password_reset_rate_limit(user_request):
        return _password_reset_security_review()
    return "\n".join(
        [
            "SECURITY FINDINGS",
            "- The planned change should preserve existing authorization and input validation behavior.",
            "- Security impact depends on how the implementation stores and observes request state.",
            "",
            "THREATS",
            "- Attackers may attempt to abuse the new behavior at high volume.",
            "- Weak validation may allow unexpected inputs to reach sensitive flows.",
            "",
            "ABUSE SCENARIOS",
            "- A malicious actor repeatedly exercises the new flow to disrupt normal users.",
            "- A user probes feedback differences to infer sensitive state.",
            "",
            "SECURITY TESTS",
            "- Verify the new behavior fails safely when limits or validation conditions are reached.",
            "- Verify user-facing feedback does not disclose sensitive internal state.",
            "",
            "MITIGATIONS",
            "- Use generic user-facing feedback where sensitive state may be inferred.",
            "- Log abuse indicators without exposing private data.",
            "",
            "RESIDUAL RISKS",
            "- Missing telemetry may reduce the ability to detect abuse.",
            "- Ambiguous requirements may leave edge controls under-specified.",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _password_reset_security_review() -> str:
    return "\n".join(
        [
            "SECURITY FINDINGS",
            "- Password reset rate limiting reduces abuse risk but must avoid blocking legitimate recovery.",
            "- Reset-attempt tracking should not expose sensitive account existence information.",
            "- User-facing feedback should avoid confirming whether an account exists.",
            "",
            "THREATS",
            "- Automated reset abuse may overwhelm users or email systems.",
            "- Attackers may use reset behavior to enumerate valid accounts.",
            "- Weak tracking may allow repeated attempts from rotating identifiers.",
            "",
            "ABUSE SCENARIOS",
            "- An attacker repeatedly triggers reset messages for a target user.",
            "- An attacker probes reset feedback to infer account validity.",
            "- A malicious actor attempts to bypass limits by changing identifiers.",
            "",
            "SECURITY TESTS",
            "- Verify excessive reset attempts are limited without revealing account existence.",
            "- Verify feedback remains generic when limits are reached.",
            "- Verify reset attempts are tracked consistently across repeated requests.",
            "- Verify legitimate users can recover after the allowed waiting conditions.",
            "",
            "MITIGATIONS",
            "- Use generic feedback for reset requests and limit events.",
            "- Track repeated reset attempts using privacy-preserving identifiers.",
            "- Apply consistent limits across supported reset channels.",
            "- Log abuse indicators for monitoring without exposing sensitive data.",
            "",
            "RESIDUAL RISKS",
            "- Highly distributed abuse may still bypass simple limits.",
            "- Strict controls may impact legitimate users during account recovery.",
            "- Poor telemetry handling may introduce privacy concerns.",
            "",
            "CONFIDENCE",
            "High",
        ]
    )


def _model_for_security_mode(config: PipelineConfig, mode: str) -> BaseModelClient:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "deep":
        deep_config = _security_deep_config(config)
        if deep_config.deepseek_gguf_path is not None:
            return DeepSeekGGUFModel(deep_config)
        return DeepSeekUnslothModel(deep_config)
    return Qwen3Model(_security_fast_config(config))


def _security_fast_config(config: PipelineConfig) -> PipelineConfig:
    fast_model = config.security_fast_model
    if fast_model.suffix.lower() == ".gguf":
        return replace(config, qwen3_gguf_path=fast_model)
    return replace(config, qwen3_base_model=str(fast_model), qwen3_gguf_path=None)


def _security_deep_config(config: PipelineConfig) -> PipelineConfig:
    deep_model = config.security_deep_model
    if deep_model.suffix.lower() == ".gguf":
        return replace(config, deepseek_gguf_path=deep_model)
    return replace(config, deepseek_gguf_path=None, deepseek_unsloth_model=deep_model)


def _normalize_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in {"fast", "deep", "auto"}:
        raise ValueError(f"Unsupported Security Agent mode: {mode}")
    return "fast" if normalized == "auto" else normalized


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
        "No Security Agent response generator was provided. Use SecurityAgentRuntimeModel "
        "for real pipeline execution or pass a fake response_generator for smoke tests."
    )
