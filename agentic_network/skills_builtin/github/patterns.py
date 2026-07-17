"""Deterministic technical pattern extraction for GitHub skill artifacts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PatternEvidence:
    """One deterministic pattern signal."""

    pattern_type: str
    name: str
    description: str
    file: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


DEFAULT_PATTERN_TYPES = {
    "api_design",
    "configuration",
    "documentation",
    "project_structure",
    "testing",
}


def extract_patterns_from_files(
    files: list[dict[str, object]],
    *,
    pattern_types: list[str] | None = None,
) -> dict[str, Any]:
    """Extract deterministic reusable engineering patterns from fetched files."""

    selected = set(pattern_types or sorted(DEFAULT_PATTERN_TYPES))
    patterns: list[PatternEvidence] = []
    for item in files:
        path = str(item.get("path", ""))
        content = str(item.get("content", ""))
        lowered_path = path.lower()
        lowered = content.lower()
        if "project_structure" in selected:
            patterns.extend(_project_structure_patterns(path, lowered_path, content))
        if "testing" in selected:
            patterns.extend(_testing_patterns(path, lowered_path, lowered, content))
        if "configuration" in selected:
            patterns.extend(_configuration_patterns(path, lowered_path, content))
        if "api_design" in selected:
            patterns.extend(_api_design_patterns(path, lowered_path, lowered, content))
        if "documentation" in selected:
            patterns.extend(_documentation_patterns(path, lowered_path, lowered, content))
    serialized = [pattern.to_dict() for pattern in _dedupe(patterns)]
    return {
        "patterns": serialized,
        "summary": _summary(serialized),
        "recommendations": _recommendations(serialized),
    }


def _project_structure_patterns(path: str, lowered_path: str, content: str) -> list[PatternEvidence]:
    patterns: list[PatternEvidence] = []
    if "/" in path:
        top = path.split("/", 1)[0]
        patterns.append(
            PatternEvidence(
                "project_structure",
                "top_level_package_layout",
                f"Repository uses a top-level '{top}' area.",
                path,
                top,
            )
        )
    if "src/" in lowered_path or lowered_path.startswith("src"):
        patterns.append(
            PatternEvidence("project_structure", "src_layout", "Repository uses a src-oriented layout.", path, path)
        )
    if "tests/" in lowered_path or lowered_path.startswith("tests"):
        patterns.append(
            PatternEvidence("project_structure", "tests_layout", "Repository separates tests into a tests area.", path, path)
        )
    if Path(path).name in {"pyproject.toml", "package.json"}:
        patterns.append(
            PatternEvidence(
                "project_structure",
                "root_configuration_file",
                "Repository exposes central project configuration at the root.",
                path,
                _first_line(content),
            )
        )
    return patterns


def _testing_patterns(path: str, lowered_path: str, lowered: str, content: str) -> list[PatternEvidence]:
    patterns: list[PatternEvidence] = []
    if "pytest" in lowered:
        patterns.append(PatternEvidence("testing", "pytest_usage", "Project references pytest.", path, _line_with(content, "pytest")))
    if "fixtures" in lowered or "@pytest.fixture" in lowered:
        patterns.append(
            PatternEvidence("testing", "pytest_fixtures", "Project appears to use pytest fixtures.", path, _line_with(content, "fixture"))
        )
    if "smoke" in lowered:
        patterns.append(PatternEvidence("testing", "smoke_tests", "Project references smoke testing.", path, _line_with(content, "smoke")))
    if "test" in lowered_path:
        patterns.append(PatternEvidence("testing", "test_file_naming", "File path follows test-oriented naming.", path, path))
    if re.search(r"\bpytest\b.*(-q|--cov|tests)", lowered):
        patterns.append(
            PatternEvidence("testing", "test_command_hint", "Project includes hints for pytest commands.", path, _line_with(content, "pytest"))
        )
    return patterns


def _configuration_patterns(path: str, lowered_path: str, content: str) -> list[PatternEvidence]:
    patterns: list[PatternEvidence] = []
    if lowered_path.endswith("pyproject.toml"):
        sections = re.findall(r"^\[([^\]]+)\]", content, flags=re.MULTILINE)
        patterns.append(
            PatternEvidence(
                "configuration",
                "pyproject_sections",
                "pyproject.toml contains tool and build configuration sections.",
                path,
                ", ".join(sections[:12]) or "pyproject.toml",
            )
        )
    if lowered_path.endswith("package.json"):
        patterns.append(
            PatternEvidence("configuration", "package_scripts", "package.json may define reusable scripts.", path, _line_with(content, "scripts"))
        )
    if "ruff" in content.lower():
        patterns.append(PatternEvidence("configuration", "ruff_config", "Project references Ruff linting.", path, _line_with(content, "ruff")))
    if "mypy" in content.lower():
        patterns.append(PatternEvidence("configuration", "mypy_config", "Project references mypy typing checks.", path, _line_with(content, "mypy")))
    return patterns


def _api_design_patterns(path: str, lowered_path: str, lowered: str, content: str) -> list[PatternEvidence]:
    patterns: list[PatternEvidence] = []
    if "fastapi" in lowered:
        patterns.append(PatternEvidence("api_design", "fastapi_usage", "Project references FastAPI.", path, _line_with(content, "FastAPI")))
    if "dependency" in lowered or "depends(" in lowered:
        patterns.append(
            PatternEvidence("api_design", "dependency_injection", "Project mentions dependency injection concepts.", path, _line_with(content, "depend"))
        )
    if "router" in lowered or "route" in lowered_path:
        patterns.append(PatternEvidence("api_design", "route_organization", "Project hints at route or router organization.", path, _line_with(content, "router")))
    if "schema" in lowered or "model" in lowered:
        patterns.append(
            PatternEvidence("api_design", "schema_model_boundary", "Project references schema/model organization.", path, _line_with(content, "schema"))
        )
    return patterns


def _documentation_patterns(path: str, lowered_path: str, lowered: str, content: str) -> list[PatternEvidence]:
    patterns: list[PatternEvidence] = []
    if lowered_path.endswith(("readme.md", "docs/index.md")):
        patterns.append(PatternEvidence("documentation", "readme_usage", "Repository has user-facing documentation.", path, _first_heading(content)))
    if "install" in lowered or "setup" in lowered:
        patterns.append(PatternEvidence("documentation", "setup_instructions", "Documentation includes setup/install hints.", path, _line_with(content, "install")))
    if "usage" in lowered or "example" in lowered:
        patterns.append(PatternEvidence("documentation", "usage_examples", "Documentation includes usage or examples.", path, _line_with(content, "example")))
    return patterns


def _dedupe(patterns: list[PatternEvidence]) -> list[PatternEvidence]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[PatternEvidence] = []
    for pattern in patterns:
        key = (pattern.pattern_type, pattern.name, pattern.file)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pattern)
    return unique


def _summary(patterns: list[dict[str, str]]) -> str:
    if not patterns:
        return "No reusable technical patterns were detected."
    by_type: dict[str, int] = {}
    for pattern in patterns:
        by_type[pattern["pattern_type"]] = by_type.get(pattern["pattern_type"], 0) + 1
    counts = ", ".join(f"{key}: {value}" for key, value in sorted(by_type.items()))
    return f"Detected {len(patterns)} deterministic pattern(s): {counts}."


def _recommendations(patterns: list[dict[str, str]]) -> list[str]:
    names = {pattern["name"] for pattern in patterns}
    recommendations: list[str] = []
    if "pytest_usage" in names:
        recommendations.append("Consider generating pytest-based unit and smoke tests for similar Python projects.")
    if "pyproject_sections" in names:
        recommendations.append("Reuse central pyproject-style configuration planning for linting, tests, and packaging.")
    if "fastapi_usage" in names or "dependency_injection" in names:
        recommendations.append("For API projects, model dependencies and route boundaries explicitly in the architecture plan.")
    if "readme_usage" in names:
        recommendations.append("Generate README setup and usage documentation alongside implementation.")
    return recommendations


def _line_with(content: str, needle: str) -> str:
    lowered = needle.lower()
    for line in content.splitlines():
        if lowered in line.lower():
            return line.strip()[:240]
    return _first_line(content)


def _first_heading(content: str) -> str:
    for line in content.splitlines():
        if line.strip().startswith("#"):
            return line.strip()[:240]
    return _first_line(content)


def _first_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:240]
    return ""
