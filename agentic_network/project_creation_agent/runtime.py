"""Deterministic Project Creation Engine foundation for ANN v8.2.

This phase produces creation plans only. It never scaffolds the target project,
executes terminal commands, applies patches, or mutates approval artifacts.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import (
    ProjectManager,
    normalize_workspace_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS_ROOT = REPO_ROOT / "outputs" / "project_creation"
PROJECT_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ProjectCreationPlan:
    """Structured project creation plan generated from a user idea."""

    status: str
    project_name: str
    project_slug: str
    project_type: str
    target_root: str
    recommended_stack: list[str]
    folders_to_create: list[str]
    files_to_create: list[dict[str, str]]
    initial_features: list[str]
    implementation_phases: list[dict[str, Any]]
    required_agents: list[str]
    safety_constraints: list[str]
    risks: list[str]
    user_questions: list[str]
    next_action: str
    skill_evidence_used: bool
    skill_evidence_summary: str
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


def plan_new_project(
    idea: str,
    target_root: str | Path,
    project_name: str | None = None,
    *,
    skill_evidence_used: bool = False,
    skill_evidence_summary: str = "",
) -> ProjectCreationPlan:
    """Create a safe project creation plan and write artifacts 40/41.

    The generated project files are only listed as a proposal. They are not
    written to target_root in v8.2.
    """

    cleaned_idea = idea.strip()
    validation = ProjectManager(
        allow_temp_paths=os.environ.get("ANN_ALLOW_TEMP_PROJECT_CREATION_TARGETS") == "1"
    ).validate_project_root(target_root)
    normalized_target = normalize_workspace_path(target_root)
    errors = list(validation.errors)
    warnings = list(validation.warnings)
    if not cleaned_idea:
        errors.append("Project idea is required.")
    status = _status_for(errors, validation.valid)
    name = _project_name(project_name, cleaned_idea)
    slug = _slugify(name)
    project_type = _project_type(cleaned_idea)
    recommended_stack = _recommended_stack(project_type)
    folders = _folders_for(project_type)
    files = _files_for(project_type)
    features = _features_for(project_type)
    phases = _implementation_phases(project_type)
    agents = [
        "Product Manager Agent",
        "Requirements Agent",
        "Planner Agent",
        "Solution Architect Agent",
        "Frontend Engineer Agent",
        "Backend Engineer Agent",
        "Database Engineer Agent",
        "QA Agent",
        "Security Agent",
        "Documentation Agent",
        "Release Agent",
    ]
    constraints = [
        "Local-only planning.",
        "No terminal execution in v8.2.",
        "No patch apply in v8.2.",
        "No generated project files are written in v8.2.",
        "No secrets in artifacts.",
        "Target root must remain outside protected ANN directories.",
    ]
    risks = [
        "The plan is a deterministic foundation and not a full implementation.",
        "Domain-specific business rules require later clarification.",
        "External services must be configured manually in future phases.",
    ]
    questions = _questions_for(project_type, cleaned_idea)
    next_action = "review_project_creation_plan" if status == "VALID" else "fix_project_creation_inputs"
    plan = ProjectCreationPlan(
        status=status,
        project_name=name,
        project_slug=slug,
        project_type=project_type,
        target_root=str(normalized_target),
        recommended_stack=recommended_stack,
        folders_to_create=folders,
        files_to_create=files,
        initial_features=features,
        implementation_phases=phases,
        required_agents=agents,
        safety_constraints=constraints,
        risks=risks,
        user_questions=questions,
        next_action=next_action,
        skill_evidence_used=skill_evidence_used,
        skill_evidence_summary=skill_evidence_summary,
        artifacts=[],
        validation_errors=errors,
        validation_warnings=warnings,
    )
    artifacts = _write_artifacts(cleaned_idea, plan)
    return ProjectCreationPlan(**{**plan.to_dict(), "artifacts": artifacts})


def _write_artifacts(idea: str, plan: ProjectCreationPlan) -> list[str]:
    artifact_dir = _artifact_dir(plan.project_slug)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    brief_md = artifact_dir / "40_project_creation_brief.md"
    brief_json = artifact_dir / "40_project_creation_brief.json"
    structure_md = artifact_dir / "41_project_structure_plan.md"
    structure_json = artifact_dir / "41_project_structure_plan.json"

    brief_payload = {
        "status": plan.status,
        "idea": idea,
        "project_name": plan.project_name,
        "project_slug": plan.project_slug,
        "project_type": plan.project_type,
        "target_root": plan.target_root,
        "initial_features": plan.initial_features,
        "recommended_stack": plan.recommended_stack,
        "safety_constraints": plan.safety_constraints,
        "risks": plan.risks,
        "user_questions": plan.user_questions,
        "next_action": plan.next_action,
        "validation_errors": plan.validation_errors,
        "validation_warnings": plan.validation_warnings,
    }
    structure_payload = plan.to_dict()

    brief_json.write_text(json.dumps(brief_payload, indent=2), encoding="utf-8")
    structure_json.write_text(json.dumps(structure_payload, indent=2), encoding="utf-8")
    brief_md.write_text(_brief_markdown(brief_payload), encoding="utf-8")
    structure_md.write_text(_structure_markdown(plan), encoding="utf-8")
    return [str(path) for path in (brief_md, brief_json, structure_md, structure_json)]


def _artifact_dir(slug: str) -> Path:
    root = Path(os.environ.get("ANN_PROJECT_CREATION_ARTIFACTS_ROOT", DEFAULT_ARTIFACTS_ROOT)).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return root / f"{timestamp}_{slug}"


def _status_for(errors: list[str], target_valid: bool) -> str:
    if any("blocked" in error.lower() or "protected" in error.lower() for error in errors):
        return "BLOCKED"
    if not target_valid:
        return "BLOCKED"
    if errors:
        return "INVALID"
    return "VALID"


def _project_name(project_name: str | None, idea: str) -> str:
    if project_name and project_name.strip():
        return project_name.strip()
    words = re.findall(r"[A-Za-z0-9]+", idea)
    if not words:
        return "Untitled ANN Project"
    stop_words = {"build", "create", "make", "a", "an", "the", "for", "local", "me"}
    selected = [word for word in words if word.lower() not in stop_words][:5]
    return " ".join(selected or words[:4]).title()


def _slugify(value: str) -> str:
    slug = PROJECT_SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "untitled-ann-project"


def _project_type(idea: str) -> str:
    lowered = idea.lower()
    if "crm" in lowered:
        return "crm_saas"
    if "ecommerce" in lowered or "e-commerce" in lowered or "shop" in lowered:
        return "ecommerce_saas"
    if "booking" in lowered or "appointment" in lowered:
        return "booking_saas"
    if "lms" in lowered or "course" in lowered:
        return "lms_saas"
    if "marketplace" in lowered:
        return "marketplace_saas"
    if "game" in lowered or "videojuego" in lowered:
        return "interactive_game"
    if "api" in lowered:
        return "api_service"
    return "custom_software"


def _recommended_stack(project_type: str) -> list[str]:
    if project_type == "interactive_game":
        return ["TypeScript", "Vite", "React", "Three.js", "Vitest", "Playwright"]
    return [
        "Next.js",
        "React",
        "TypeScript",
        "Tailwind CSS",
        "FastAPI",
        "SQLAlchemy",
        "PostgreSQL",
        "pytest",
        "Vitest",
        "Playwright",
        "Docker",
    ]


def _folders_for(project_type: str) -> list[str]:
    if project_type == "interactive_game":
        return ["apps/game/src", "apps/game/tests", "docs", "scripts", "assets"]
    return [
        "apps/web/src",
        "apps/api/app",
        "packages/shared",
        "packages/database",
        "docs",
        "tests/python",
        "tests/e2e",
        "docker",
        "scripts",
    ]


def _files_for(project_type: str) -> list[dict[str, str]]:
    if project_type == "interactive_game":
        return [
            {"path": "apps/game/package.json", "purpose": "Game frontend package manifest"},
            {"path": "apps/game/src/main.tsx", "purpose": "Game bootstrap"},
            {"path": "apps/game/src/game.ts", "purpose": "Core game loop"},
            {"path": "README.md", "purpose": "Project setup and run guide"},
        ]
    return [
        {"path": "apps/web/package.json", "purpose": "Frontend package manifest"},
        {"path": "apps/web/src/app/page.tsx", "purpose": "Main product UI"},
        {"path": "apps/api/app/main.py", "purpose": "FastAPI application entrypoint"},
        {"path": "packages/database/schema.sql", "purpose": "Initial database model proposal"},
        {"path": "docker-compose.yml", "purpose": "Local service orchestration"},
        {"path": ".env.example", "purpose": "Non-secret environment template"},
        {"path": "README.md", "purpose": "Project setup and run guide"},
    ]


def _features_for(project_type: str) -> list[str]:
    features_by_type = {
        "crm_saas": ["accounts", "contacts", "deals", "pipeline dashboard", "activity timeline"],
        "ecommerce_saas": ["catalog", "cart", "checkout flow", "orders", "admin inventory"],
        "booking_saas": ["availability", "booking calendar", "customers", "notifications"],
        "lms_saas": ["courses", "lessons", "enrollments", "progress tracking"],
        "marketplace_saas": ["seller profiles", "listings", "orders", "reviews"],
        "interactive_game": ["game loop", "score system", "input controls", "pause/restart"],
        "api_service": ["versioned API", "validation", "health checks", "tests"],
    }
    return features_by_type.get(project_type, ["domain model", "core workflows", "dashboard", "tests"])


def _implementation_phases(project_type: str) -> list[dict[str, Any]]:
    return [
        {"order": 1, "name": "Requirements", "goal": "Validate scope and user stories."},
        {"order": 2, "name": "Architecture", "goal": f"Design {project_type} modules and boundaries."},
        {"order": 3, "name": "Scaffold", "goal": "Create approved folders and starter files."},
        {"order": 4, "name": "Implementation", "goal": "Build product workflows and APIs."},
        {"order": 5, "name": "Verification", "goal": "Run tests, review, and harden."},
    ]


def _questions_for(project_type: str, idea: str) -> list[str]:
    questions = ["Who is the primary user?", "What is the first workflow that must work end to end?"]
    if project_type.endswith("_saas"):
        questions.extend(["Is multi-tenancy required in the MVP?", "What billing model should be planned?"])
    if "integration" in idea.lower():
        questions.append("Which external integrations are mandatory for the first version?")
    return questions


def _brief_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Project Creation Brief",
        "",
        f"Status: {payload['status']}",
        f"Project: {payload['project_name']}",
        f"Type: {payload['project_type']}",
        f"Target Root: {payload['target_root']}",
        f"Next Action: {payload['next_action']}",
        "",
        "## Initial Features",
        *[f"- {item}" for item in payload["initial_features"]],
        "",
        "## Recommended Stack",
        *[f"- {item}" for item in payload["recommended_stack"]],
        "",
        "## Safety Constraints",
        *[f"- {item}" for item in payload["safety_constraints"]],
    ]
    return "\n".join(lines) + "\n"


def _structure_markdown(plan: ProjectCreationPlan) -> str:
    lines = [
        "# Project Structure Plan",
        "",
        f"Status: {plan.status}",
        f"Project Slug: {plan.project_slug}",
        "",
        "## Folders To Create",
        *[f"- {item}" for item in plan.folders_to_create],
        "",
        "## Files To Create",
        *[f"- {item['path']}: {item['purpose']}" for item in plan.files_to_create],
        "",
        "## Implementation Phases",
        *[f"- {phase['order']}. {phase['name']}: {phase['goal']}" for phase in plan.implementation_phases],
        "",
        "## Required Agents",
        *[f"- {agent}" for agent in plan.required_agents],
    ]
    return "\n".join(lines) + "\n"
