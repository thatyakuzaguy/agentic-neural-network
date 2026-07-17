"""Architect Agent runtime, parser, validation, and model routing."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentic_network.config import PipelineConfig
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import DeepSeekGGUFModel, clean_deepseek_output
from agentic_network.models.deepseek_unsloth import DeepSeekUnslothModel
from agentic_network.models.qwen3 import Qwen3Model

ARCHITECT_OUTPUT_FILE = "02_architecture_plan.md"
PROMPT_PATH = Path(__file__).with_name("prompt.md")
ARCHITECT_MODES = frozenset({"fast", "deep", "auto"})
SECTION_KEYS = {
    "TECHNICAL SUMMARY": "technical_summary",
    "AFFECTED AREAS": "affected_areas",
    "FILES TO INSPECT": "files_to_inspect",
    "IMPLEMENTATION PLAN": "implementation_plan",
    "DATA OR STATE CHANGES": "data_or_state_changes",
    "TEST STRATEGY": "test_strategy",
    "RISKS": "risks",
    "HANDOFF TO CODE AGENT": "handoff_to_code_agent",
    "CONFIDENCE": "confidence",
}
REQUIRED_SECTION_TITLES = tuple(SECTION_KEYS)
SECTION_LINE = re.compile(
    r"^\s*("
    + "|".join(re.escape(title) for title in REQUIRED_SECTION_TITLES)
    + r")\s*$",
    re.IGNORECASE,
)
RISK_INDICATORS = (
    "auth",
    "authentication",
    "authorization",
    "billing",
    "credential",
    "encryption",
    "large refactor",
    "migration",
    "multi-file",
    "password",
    "payment",
    "permission",
    "rbac",
    "secret",
    "security",
    "tenant",
    "token",
    "unclear acceptance",
)


@dataclass(frozen=True)
class ArchitectAgentResult:
    """Structured Architect Agent output returned to the pipeline and CLI."""

    raw_user_request: str
    product_requirements_input: str
    cleaned_architecture_response: str
    parsed_sections: dict[str, list[str] | str]
    mode_used: str
    model_path_used: str
    validation_warnings: list[str]
    validation_errors: list[str]
    output_artifact_path: str | None = None

    def to_stage_output(self) -> str:
        """Return the architecture plan saved as the pipeline stage artifact."""

        return self.cleaned_architecture_response


class ArchitectAgentRuntimeModel(BaseModelClient):
    """BaseModelClient adapter that routes Architect Agent fast/deep/auto modes."""

    def __init__(self, config: PipelineConfig, repo_root: Path | None = None) -> None:
        self.config = config
        self.repo_root = repo_root
        self.last_result: ArchitectAgentResult | None = None
        self._models: dict[str, BaseModelClient] = {}

    @property
    def backend_name(self) -> str:
        if self.last_result is not None:
            return f"architect_{self.last_result.mode_used}"
        return f"architect_{self.config.architect_mode}"

    def generate_text(self, prompt: str) -> str:
        user_request = _extract_context_section(prompt, "USER REQUEST")
        product_requirements = _extract_context_section(prompt, "PRODUCT REQUIREMENTS")
        if not user_request:
            user_request = _extract_instruction_from_prompt(prompt)
        if not product_requirements:
            product_requirements = prompt
        result = run_architect_agent(
            user_request=user_request,
            product_requirements=product_requirements,
            mode=self.config.architect_mode,
            repo_root=self.repo_root,
            fast_model_path=self.config.architect_fast_model,
            deep_model_path=self.config.architect_deep_model,
            response_generator=self._generate_with_selected_model,
        )
        self.last_result = result
        return result.to_stage_output()

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        prompt = "\n".join(message.get("content", "") for message in messages)
        return self.generate_text(prompt)

    def diagnostics(self) -> dict[str, object]:
        result = self.last_result
        return {
            "backend_name": self.backend_name,
            "loaded_backend_type": "architect_runtime",
            "architect_mode": result.mode_used if result else self.config.architect_mode,
            "model_path": (
                result.model_path_used
                if result
                else str(self.config.architect_fast_model)
            ),
            "output_file": self.config.architect_output,
        }

    def _generate_with_selected_model(
        self,
        *,
        prompt: str,
        mode: str,
        model_path: Path,
    ) -> str:
        model = self._model_for_mode(mode, model_path)
        return model.generate_text(prompt)

    def _model_for_mode(self, mode: str, model_path: Path) -> BaseModelClient:
        cache_key = f"{mode}:{model_path}"
        if cache_key not in self._models:
            if mode == "deep":
                self._models[cache_key] = _deep_model(self.config, model_path)
            else:
                self._models[cache_key] = _fast_model(self.config, model_path)
        return self._models[cache_key]


def run_architect_agent(
    *,
    user_request: str,
    product_requirements: str,
    mode: str = "fast",
    repo_root: Path | None = None,
    fast_model_path: Path | None = None,
    deep_model_path: Path | None = None,
    output_artifact_path: Path | None = None,
    response_generator: Callable[..., str] | None = None,
) -> ArchitectAgentResult:
    """Run the Architect Agent and return parsed output plus validation details."""

    resolved_mode = resolve_architect_mode(mode, user_request, product_requirements)
    model_path = _model_path_for_mode(resolved_mode, fast_model_path, deep_model_path)
    prompt = build_architect_prompt(
        user_request=user_request,
        product_requirements=product_requirements,
        repo_root=repo_root,
    )
    generator = response_generator or _unsupported_real_generator
    raw_response = generator(prompt=prompt, mode=resolved_mode, model_path=model_path)
    cleaned_response = clean_architect_response(str(raw_response))
    parsed_sections = parse_architect_agent_sections(cleaned_response)
    validation_warnings, validation_errors = validate_architect_agent_response(
        cleaned_response=cleaned_response,
        parsed_sections=parsed_sections,
    )
    written_path: str | None = None
    if output_artifact_path is not None:
        output_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output_artifact_path.write_text(cleaned_response.rstrip() + "\n", encoding="utf-8")
        written_path = str(output_artifact_path)
    return ArchitectAgentResult(
        raw_user_request=user_request,
        product_requirements_input=product_requirements,
        cleaned_architecture_response=cleaned_response,
        parsed_sections=parsed_sections,
        mode_used=resolved_mode,
        model_path_used=_display_model_path(model_path),
        validation_warnings=validation_warnings,
        validation_errors=validation_errors,
        output_artifact_path=written_path,
    )


def build_architect_prompt(
    *,
    user_request: str,
    product_requirements: str,
    repo_root: Path | None = None,
) -> str:
    """Build the strict Architect Agent prompt with optional repository context."""

    repo_context = _repository_context(repo_root) if repo_root is not None else ""
    parts = [
        PROMPT_PATH.read_text(encoding="utf-8").strip(),
        "RAW USER REQUEST",
        user_request.strip(),
        "PRODUCT AGENT REQUIREMENTS",
        product_requirements.strip(),
    ]
    if repo_context:
        parts.extend(["REPOSITORY CONTEXT", repo_context])
    parts.extend(["ARCHITECT AGENT OUTPUT", ""])
    return "\n\n".join(parts)


def resolve_architect_mode(mode: str, user_request: str, product_requirements: str) -> str:
    """Resolve fast/deep/auto Architect mode."""

    normalized = mode.strip().lower()
    if normalized not in ARCHITECT_MODES:
        raise ValueError(f"Unsupported Architect Agent mode: {mode}")
    if normalized != "auto":
        return normalized
    text = f"{user_request}\n{product_requirements}".lower()
    return "deep" if any(indicator in text for indicator in RISK_INDICATORS) else "fast"


def parse_architect_agent_sections(response: str) -> dict[str, list[str] | str]:
    """Split an Architect Agent response into normalized named sections."""

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
            values = sections.setdefault(key, [])
            if isinstance(values, list):
                values.append(line[2:].strip())
    return sections


def validate_architect_agent_response(
    *,
    cleaned_response: str,
    parsed_sections: dict[str, list[str] | str],
) -> tuple[list[str], list[str]]:
    """Validate the Architect Agent output contract."""

    warnings: list[str] = []
    errors: list[str] = []
    section_counts = _section_counts(cleaned_response)
    for title, key in SECTION_KEYS.items():
        count = section_counts.get(title, 0)
        if count == 0:
            errors.append(f"missing_section_{key}")
        elif count > 1:
            errors.append(f"duplicate_section_{key}")
        elif key not in parsed_sections:
            errors.append(f"unparsed_section_{key}")

    confidence = str(parsed_sections.get("confidence", "")).strip()
    if confidence != "High":
        errors.append("confidence_not_high")

    if re.search(r"</?think\b", cleaned_response, re.IGNORECASE):
        errors.append("think_tags_present")
    if re.search(r"(?m)^\s*#{1,6}\s+", cleaned_response):
        errors.append("markdown_headings_present")
    if "```" in cleaned_response:
        errors.append("code_fence_present")

    handoff = parsed_sections.get("handoff_to_code_agent", [])
    if not isinstance(handoff, list) or not handoff:
        errors.append("handoff_to_code_agent_missing_bullet")

    files_to_inspect = parsed_sections.get("files_to_inspect", [])
    if not isinstance(files_to_inspect, list) or not files_to_inspect:
        errors.append("files_to_inspect_missing_bullet")

    for key, value in parsed_sections.items():
        if key != "confidence" and isinstance(value, list) and not value:
            warnings.append(f"empty_section_{key}")

    return warnings, errors


def clean_architect_response(response: str) -> str:
    """Clean model chatter while preserving validation-visible contract issues."""

    return clean_deepseek_output(response).strip()


def _section_counts(response: str) -> dict[str, int]:
    counts = {title: 0 for title in REQUIRED_SECTION_TITLES}
    for line in response.splitlines():
        match = SECTION_LINE.match(line.strip())
        if match:
            counts[match.group(1).upper()] += 1
    return counts


def _repository_context(repo_root: Path) -> str:
    root = repo_root.resolve()
    if not root.exists():
        return ""
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        files = [line for line in completed.stdout.splitlines() if line.strip()]
    else:
        files = [path.name for path in root.iterdir() if path.name not in {".git", "__pycache__"}]
    if not files:
        return ""
    selected = _select_relevant_files(files)
    return "\n".join(f"- {path}" for path in selected)


def _select_relevant_files(files: list[str]) -> list[str]:
    priority_fragments = (
        "README",
        ".env.example",
        "pyproject.toml",
        "agentic_network/",
        "apps/",
        "packages/",
        "tests/",
        "scripts/",
        "docs/",
    )
    selected: list[str] = []
    for path in files:
        if any(fragment in path for fragment in priority_fragments):
            selected.append(path)
        if len(selected) >= 80:
            break
    return selected or files[:80]


def _model_path_for_mode(
    mode: str,
    fast_model_path: Path | None,
    deep_model_path: Path | None,
) -> Path:
    if mode == "deep":
        return deep_model_path or Path(
            "/mnt/d/Models/deepseek/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
        )
    return fast_model_path or Path("/mnt/d/Models/qwen3")


def _display_model_path(model_path: Path) -> str:
    text = str(model_path)
    if text.startswith("\\mnt\\") or text.startswith("/mnt/"):
        return text.replace("\\", "/")
    return text


def _fast_model(config: PipelineConfig, model_path: Path) -> BaseModelClient:
    model_path = Path(model_path)
    if model_path.suffix.lower() == ".gguf":
        routed = config.with_architect_model_paths(qwen3_gguf_path=model_path)
    else:
        routed = config.with_architect_model_paths(
            qwen3_base_model=str(model_path),
            qwen3_gguf_path=None,
        )
    return Qwen3Model(routed)


def _deep_model(config: PipelineConfig, model_path: Path) -> BaseModelClient:
    model_path = Path(model_path)
    if model_path.suffix.lower() == ".gguf":
        routed = config.with_architect_model_paths(deepseek_gguf_path=model_path)
        return DeepSeekGGUFModel(routed)
    routed = config.with_architect_model_paths(deepseek_unsloth_model=model_path)
    return DeepSeekUnslothModel(routed)


def _extract_instruction_from_prompt(prompt: str) -> str:
    marker = "INPUT CONTEXT\n-------------"
    if marker not in prompt:
        return prompt.strip()
    after_marker = prompt.split(marker, 1)[1]
    if "\n\nOUTPUT\n------" in after_marker:
        after_marker = after_marker.split("\n\nOUTPUT\n------", 1)[0]
    return after_marker.strip()


def _extract_context_section(prompt: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(title)}\n=+\n(?P<body>.*?)(?=\n\n[A-Z][A-Z /-]+\n=+\n|\Z)"
    )
    match = pattern.search(prompt)
    return match.group("body").strip() if match else ""


def _unsupported_real_generator(*, prompt: str, mode: str, model_path: Path) -> str:
    raise RuntimeError(
        "No Architect Agent response generator was provided. Use ArchitectAgentRuntimeModel "
        "for real pipeline execution or pass a fake response_generator for smoke tests."
    )
