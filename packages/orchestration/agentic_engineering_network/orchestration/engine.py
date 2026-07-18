from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from agentic_engineering_network.agents.definitions import AgentDefinition, get_agent_registry
from agentic_engineering_network.agents.runtime import AgentRunResult, AgentRuntime
from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.orchestration.artifact_router import build_project_artifacts
from agentic_engineering_network.orchestration.tasks import EngineeringTask, decompose_idea
from agentic_engineering_network.orchestration.workspace import ProposedFile, WorkspaceManager
from agentic_engineering_network.security.approvals import ApprovalCenter, ApprovalType
from agentic_engineering_network.security.review import SecurityReviewer
from agentic_engineering_network.shared.config import Settings, resolve_workspace_directory, to_host_path
from agentic_engineering_network.shared.providers import (
    DeterministicLocalProvider,
    build_provider,
    build_provider_for_agent,
)


@dataclass(frozen=True)
class EngineeringRun:
    run_id: str
    idea: str
    workspace_directory: str
    tasks: tuple[EngineeringTask, ...]
    agent_results: tuple[AgentRunResult, ...]
    proposed_files: tuple[ProposedFile, ...]
    security_review: dict[str, Any]


class AgenticEngineeringNetwork:
    def __init__(self, settings: Settings, audit: AuditLogger, approvals: ApprovalCenter) -> None:
        self.settings = settings
        self.audit = audit
        self.approvals = approvals
        try:
            provider = build_provider(settings)
            if settings.ai_provider == "ollama":
                # Keep startup responsive when Ollama is not running.
                provider = DeterministicLocalProvider()
        except RuntimeError:
            provider = DeterministicLocalProvider()
        provider_factory = None
        if settings.ai_provider in {"llama_cpp", "local_gguf", "qwen_direct"}:
            def routed_provider_factory(agent: AgentDefinition):
                return build_provider_for_agent(settings, str(agent.name), "FAST")

            provider_factory = routed_provider_factory
        self.runtime = AgentRuntime(provider, audit, provider_factory=provider_factory)
        self.workspace = WorkspaceManager(settings.generated_projects_path, approvals)
        self.security = SecurityReviewer()

    def submit(self, idea: str, workspace_directory: str | None = None, run_id: str | None = None) -> EngineeringRun:
        run_id = run_id or str(uuid4())
        workspace_root = resolve_workspace_directory(self.settings, workspace_directory)
        display_workspace = to_host_path(self.settings, workspace_root)
        workspace = WorkspaceManager(workspace_root, self.approvals, display_root=display_workspace)
        self.audit.record(
            "run.started",
            "user",
            idea,
            {"run_id": run_id, "workspace_directory": display_workspace, "internal_workspace": str(workspace_root)},
        )
        tasks = decompose_idea(idea)
        context: dict[str, Any] = {
            "run_id": run_id,
            "task_count": len(tasks),
            "workspace_directory": display_workspace,
        }
        try:
            agent_results = tuple(
                self.runtime.run(agent, idea, context) for agent in get_agent_registry()
            )
        finally:
            self.runtime.close()
        files = self._starter_artifacts(idea, run_id)
        review = self.security.review_generated_files(files)
        proposed = tuple(
            workspace.propose_file(
                path,
                content,
                requested_by="ANN (Agentic Neural Network)",
                metadata={"run_id": run_id, "gate": "file_write"},
            )
            for path, content in files.items()
        )
        self.approvals.request(
            ApprovalType.SHELL_EXECUTION,
            "Run generated project tests in Docker sandbox",
            "Execute pytest, vitest, and Playwright inside the generated project's Docker sandbox.",
            "QA Agent",
            {"run_id": run_id, "gate": "qa", "commands": ["pytest", "npm run test", "npm run e2e"], "sandbox": "docker"},
        )
        self.approvals.request(
            ApprovalType.PACKAGE_INSTALLATION,
            "Install generated project dependencies",
            "Install npm and Python dependencies inside the Docker build context after review.",
            "DevOps Agent",
            {"run_id": run_id, "gate": "dependencies", "package_managers": ["npm", "pip"], "sandbox": "docker"},
        )
        self.approvals.request(
            ApprovalType.DEPLOYMENT,
            "Create deployment package",
            "Package the generated project and deployment manifests after QA and security approval.",
            "Release Agent",
            {"run_id": run_id, "gate": "release", "target": "local-docker", "requires": ["qa", "security", "code_review"]},
        )
        self.audit.record(
            "run.completed",
            "orchestrator",
            "Generated plan, agent decisions, approval requests, and starter artifacts.",
            {"run_id": run_id, "security": review.to_dict()},
        )
        return EngineeringRun(
            run_id=run_id,
            idea=idea,
            workspace_directory=display_workspace,
            tasks=tasks,
            agent_results=agent_results,
            proposed_files=proposed,
            security_review=review.to_dict(),
        )

    def _starter_artifacts(self, idea: str, run_id: str) -> dict[str, str]:
        return build_project_artifacts(idea, run_id)

    @staticmethod
    def serialize(run: EngineeringRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "idea": run.idea,
            "workspace_directory": run.workspace_directory,
            "tasks": [asdict(task) for task in run.tasks],
            "agent_results": [asdict(result) for result in run.agent_results],
            "proposed_files": [asdict(item) for item in run.proposed_files],
            "security_review": run.security_review,
        }
