from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class EngineeringTask:
    title: str
    owner: str
    description: str
    dependencies: tuple[str, ...] = ()
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING


def decompose_idea(idea: str) -> tuple[EngineeringTask, ...]:
    normalized = idea.strip() or "Untitled software system"
    return (
        EngineeringTask("Product brief", "Product Manager Agent", f"Define MVP and risks for {normalized}.", task_id="product_brief"),
        EngineeringTask(
            "Requirements specification",
            "Requirements Agent",
            "Create functional and non-functional requirements.",
            dependencies=("product_brief",),
            task_id="requirements_specification",
        ),
        EngineeringTask(
            "Product review gate",
            "Product Review Agent",
            "Block weak product plans and request refinement when needed.",
            dependencies=("requirements_specification",),
            task_id="product_review_gate",
        ),
        EngineeringTask(
            "Architecture design",
            "Solution Architect Agent",
            "Design domain boundaries, database, API contract, frontend surfaces, and deployment topology.",
            dependencies=("product_review_gate",),
            task_id="architecture_design",
        ),
        EngineeringTask(
            "Implementation plan",
            "Planner Agent",
            "Create a dependency-aware engineering task graph.",
            dependencies=("architecture_design",),
            task_id="implementation_plan",
        ),
        EngineeringTask(
            "Database generation",
            "Database Engineer Agent",
            "Generate PostgreSQL schema, migrations, SQLAlchemy models, and seed data.",
            dependencies=("implementation_plan",),
            task_id="database_generation",
        ),
        EngineeringTask(
            "Backend generation",
            "Backend Engineer Agent",
            "Generate FastAPI services, auth, data access, API routes, OpenAPI contract, and backend tests.",
            dependencies=("database_generation",),
            task_id="backend_generation",
        ),
        EngineeringTask(
            "Frontend generation",
            "Frontend Engineer Agent",
            "Generate Next.js UI and tests against the approved API contract or mock contract.",
            dependencies=("backend_generation",),
            task_id="frontend_generation",
        ),
        EngineeringTask(
            "DevOps packaging",
            "DevOps Agent",
            "Generate Docker and PowerShell lifecycle automation.",
            dependencies=("backend_generation", "frontend_generation"),
            task_id="devops_packaging",
        ),
        EngineeringTask(
            "QA verification",
            "QA Agent",
            "Run unit, integration, and E2E quality gates.",
            dependencies=("backend_generation", "frontend_generation", "devops_packaging"),
            task_id="qa_verification",
        ),
        EngineeringTask(
            "Security review",
            "Security Agent",
            "Review code, dependencies, endpoints, authentication, secrets, and tenant boundaries.",
            dependencies=("backend_generation", "database_generation"),
            task_id="security_review",
        ),
        EngineeringTask(
            "Documentation",
            "Documentation Agent",
            "Generate user, developer, architecture, troubleshooting, and deployment documentation.",
            dependencies=("architecture_design", "backend_generation", "frontend_generation"),
            task_id="documentation",
        ),
        EngineeringTask(
            "Code review",
            "Code Review Agent",
            "Review diffs, API/frontend alignment, maintainability, and test coverage.",
            dependencies=("qa_verification", "security_review", "documentation"),
            task_id="code_review",
        ),
        EngineeringTask(
            "Meta review",
            "Meta Review Agent",
            "Review all agent outputs, gates, scores, and release blockers.",
            dependencies=("code_review",),
            task_id="meta_review",
        ),
        EngineeringTask(
            "Release package",
            "Release Agent",
            "Prepare deployment bundle, release notes, rollback notes, and final verification.",
            dependencies=("meta_review",),
            task_id="release_package",
        ),
    )
