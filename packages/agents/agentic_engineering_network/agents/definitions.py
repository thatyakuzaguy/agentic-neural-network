from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentName(StrEnum):
    PRODUCT_MANAGER = "Product Manager Agent"
    REQUIREMENTS = "Requirements Agent"
    PLANNER = "Planner Agent"
    SOLUTION_ARCHITECT = "Solution Architect Agent"
    FRONTEND_ENGINEER = "Frontend Engineer Agent"
    BACKEND_ENGINEER = "Backend Engineer Agent"
    DATABASE_ENGINEER = "Database Engineer Agent"
    DEVOPS = "DevOps Agent"
    QA = "QA Agent"
    SECURITY = "Security Agent"
    DOCUMENTATION = "Documentation Agent"
    CODE_REVIEW = "Code Review Agent"
    RELEASE = "Release Agent"
    PRODUCT_REVIEW = "Product Review Agent"
    META_REVIEW = "Meta Review Agent"


@dataclass(frozen=True)
class AgentDefinition:
    name: AgentName
    role: str
    goals: tuple[str, ...]
    tools: tuple[str, ...]
    outputs: tuple[str, ...]
    input_schema: tuple[str, ...] = ("idea", "run_id", "workspace_directory", "quality_context")
    output_schema: tuple[str, ...] = ("decision", "findings", "required_fixes", "risks", "confidence")
    validation_logic: tuple[str, ...] = ("schema completeness", "traceability to requirements", "no unsupported claims")
    quality_rubric: tuple[str, ...] = ("correctness", "maintainability", "security", "testability", "operability")
    failure_modes: tuple[str, ...] = ("ambiguous input", "missing evidence", "unsafe recommendation", "low confidence")
    retry_policy: str = "Retry once with narrower context for schema or evidence gaps; escalate repeated failures."
    escalation_rules: tuple[str, ...] = ("critical security risk", "legal/compliance claim", "unclear product category", "repeated failed validation")


AGENT_REGISTRY: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        AgentName.PRODUCT_MANAGER,
        "Turns a software idea into a product brief, success metrics, scope, and release risks.",
        ("Clarify customer value", "Define MVP boundaries", "Prioritize outcomes", "Prepare product evidence packet"),
        ("product_intelligence_engine", "requirements_intake", "market_risk_matrix", "scope_guardrails"),
        ("product_brief.md", "success_metrics.json", "product_evidence_packet.json"),
    ),
    AgentDefinition(
        AgentName.REQUIREMENTS,
        "Extracts functional, non-functional, compliance, and acceptance requirements.",
        ("Create testable requirements", "Identify unknowns", "Trace requirements to tasks"),
        ("requirements_parser", "acceptance_criteria_builder"),
        ("requirements.md", "acceptance_criteria.json"),
    ),
    AgentDefinition(
        AgentName.PLANNER,
        "Decomposes the project into ordered tasks with dependencies and approval gates.",
        ("Build task DAG", "Estimate risk", "Schedule agent work"),
        ("task_graph", "timeline_builder", "approval_center"),
        ("plan.json", "timeline.md"),
    ),
    AgentDefinition(
        AgentName.SOLUTION_ARCHITECT,
        "Designs the system architecture, module boundaries, APIs, and data flows.",
        ("Choose architecture", "Define contracts", "Minimize coupling", "Document uncertainty and alternatives"),
        ("architecture_intelligence_engine", "architecture_modeler", "api_contract_designer"),
        ("architecture.md", "api_contract.yaml", "architecture_decision_packet.json"),
    ),
    AgentDefinition(
        AgentName.FRONTEND_ENGINEER,
        "Generates Next.js, React, TypeScript, Tailwind, Zustand, and React Query code.",
        ("Build accessible UI", "Wire data flows", "Create frontend tests"),
        ("file_manager", "diff_manager", "component_generator"),
        ("apps/web", "frontend_tests"),
    ),
    AgentDefinition(
        AgentName.BACKEND_ENGINEER,
        "Generates FastAPI services, typed schemas, API endpoints, and integration tests.",
        ("Build APIs", "Validate inputs", "Keep business logic modular"),
        ("file_manager", "api_generator", "test_runner"),
        ("apps/api", "backend_tests"),
    ),
    AgentDefinition(
        AgentName.DATABASE_ENGINEER,
        "Designs PostgreSQL schema, SQLAlchemy models, migrations, and seed data.",
        ("Normalize core data", "Create migrations", "Protect data integrity"),
        ("schema_designer", "migration_generator"),
        ("database_schema.sql", "migrations"),
    ),
    AgentDefinition(
        AgentName.DEVOPS,
        "Builds Docker, PowerShell automation, environment verification, and deployment packages.",
        ("Package reproducibly", "Verify environment", "Automate lifecycle commands"),
        ("docker_manager", "terminal_manager", "git_manager"),
        ("docker-compose.yml", "setup.ps1", "deployment_bundle"),
    ),
    AgentDefinition(
        AgentName.QA,
        "Creates and runs unit, integration, and end-to-end test strategy.",
        ("Catch regressions", "Verify acceptance criteria", "Report quality gates"),
        ("pytest", "vitest", "playwright", "test_runner"),
        ("test_report.json", "qa_summary.md"),
    ),
    AgentDefinition(
        AgentName.SECURITY,
        "Reviews code, dependencies, APIs, authentication, secrets, and execution boundaries.",
        ("Block unsafe execution", "Detect secrets", "Review dependencies", "Prepare security decision packet"),
        ("security_intelligence_engine", "secret_scanner", "dependency_review", "audit_logs"),
        ("security_review.md", "threat_model.md", "security_decision_packet.json"),
    ),
    AgentDefinition(
        AgentName.DOCUMENTATION,
        "Generates user, developer, architecture, troubleshooting, and deployment docs.",
        ("Explain setup", "Document decisions", "Keep docs traceable"),
        ("doc_generator", "diagram_builder"),
        ("README.md", "AGENTS.md", "ARCHITECTURE.md"),
    ),
    AgentDefinition(
        AgentName.CODE_REVIEW,
        "Reviews diffs for correctness, maintainability, test coverage, and architectural fit.",
        ("Find defects", "Enforce standards", "Verify test coverage"),
        ("diff_viewer", "static_review", "quality_gate"),
        ("review.md", "review_findings.json"),
    ),
    AgentDefinition(
        AgentName.RELEASE,
        "Assembles release notes, deployment package, rollback notes, and final verification.",
        ("Package release", "Summarize changes", "Prepare rollback", "Block release on unresolved critical risks"),
        ("release_intelligence_engine", "git_manager", "deployment_packager", "changelog_generator"),
        ("release_notes.md", "CHANGELOG.md", "release_decision_packet.json"),
    ),
    AgentDefinition(
        AgentName.PRODUCT_REVIEW,
        "Blocks weak product plans and requires refinement when the buyer, problem, value proposition, or pricing is unclear.",
        ("Validate product strategy", "Block vague product scopes", "Require measurable outcomes"),
        ("product_intelligence_engine", "product_discovery", "risk_matrix", "go_to_market_checklist", "senior_gate"),
        ("product_review.json", "required_refinements.md"),
        validation_logic=("problem statement exists", "ICP exists", "pricing model exists", "launch risks are explicit"),
        quality_rubric=("market clarity", "buyer specificity", "scope discipline", "pricing realism", "activation path"),
        failure_modes=("generic SaaS idea", "missing ICP", "unclear willingness to pay", "unsupported market claim"),
    ),
    AgentDefinition(
        AgentName.META_REVIEW,
        "Reviews all agent outputs against senior gates, scorecards, evidence, and release-readiness policy.",
        ("Find cross-agent contradictions", "Verify gates", "Escalate unresolved risks"),
        ("approval_packets", "senior_scorecard", "gate_results", "evidence_map", "release_policy"),
        ("meta_review.json", "senior_review_summary.md"),
        validation_logic=("all gates present", "scores have findings", "release blockers are explicit", "human review notes exist"),
        quality_rubric=("cross-functional consistency", "risk visibility", "evidence quality", "release discipline"),
        failure_modes=("missing gate", "contradictory agent output", "unreviewed critical risk", "false production claim"),
    ),
)


def get_agent_registry() -> tuple[AgentDefinition, ...]:
    return AGENT_REGISTRY
